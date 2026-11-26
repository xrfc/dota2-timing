"""U191 fitted reference states and pure prediction, separate from training and I/O.

The typed functions below validate wave decisions and take candidate actions
explicitly. ``predict(rows)`` is the low-level legacy numerical boundary; it does
not admit an artifact, certify a game patch, or authorize product recommendations.
State dictionaries avoid serializing these project classes. The artifact loader
and exact runtime/source compatibility registry are separate, later boundaries.
"""

from copy import deepcopy
from dataclasses import dataclass

import numpy as np
from scipy.special import expit

from dota_items.contracts.action_outcomes import validate_decision
from dota_items.modeling.awareness.action_features import (
    FeatureScale,
    _row_features,
    _sequence_design,
    _sequence_inputs,
    _state_array,
    _state_fields,
    _state_number,
)


def _backend(value, family):
    # Lazy backend validation keeps sequence-only imports free of sklearn and its
    # optimization dependencies. No estimator is constructed or fitted here.
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.utils.validation import check_is_fitted

    expected = {
        "hits": HistGradientBoostingRegressor,
        "death": HistGradientBoostingClassifier,
        "behavior": Pipeline,
    }[family]
    if type(value) is not expected:
        raise ValueError(f"unsupported {family} backend")
    if family == "behavior":
        steps = (
            ("simpleimputer", SimpleImputer),
            ("standardscaler", StandardScaler),
            ("logisticregression", LogisticRegression),
        )
        if len(value.steps) != len(steps) or any(
            name != wanted_name or type(estimator) is not wanted_type
            for (name, estimator), (wanted_name, wanted_type) in zip(
                value.steps, steps, strict=True
            )
        ):
            raise ValueError("behavior pipeline differs from the registered three-step backend")
        for _, estimator in value.steps:
            check_is_fitted(estimator)
        output_width = len(value.steps[0][1].get_feature_names_out())
        if any(estimator.n_features_in_ != output_width for _, estimator in value.steps[1:]):
            raise ValueError("behavior pipeline has inconsistent fitted widths")
    check_is_fitted(value)


@dataclass
class ActionMeans:
    means: dict

    def __post_init__(self):
        if type(self.means) is not dict or not self.means.keys() <= {"farm", "retreat"}:
            raise ValueError("means require registered wave actions")
        for value in self.means.values():
            if not isinstance(value, (tuple, list, np.ndarray)) or np.shape(value) != (2,):
                raise ValueError("action means require hits and death")
            _state_number(value[0], "mean hits", low=0)
            _state_number(value[1], "mean death", low=0, high=1)
        self.means = deepcopy(self.means)

    @classmethod
    def from_state(cls, state):
        _state_fields(state, ("means",))
        return cls(state["means"])

    def to_state(self):
        return {"means": deepcopy(self.means)}

    def predict(self, rows):
        expected = [self.means.get(row["action"], (np.nan, np.nan)) for row in rows]
        hits, death = np.asarray(expected, dtype=float).reshape(-1, 2).T
        return hits, death


@dataclass
class TreeOutcome:
    columns: np.ndarray
    hits: object
    death: object | None
    death_rate: float
    history: bool

    def __post_init__(self):
        self.columns = _state_array(self.columns, "columns", kind="b")
        if not self.columns.any() or type(self.history) is not bool:
            raise ValueError("tree requires selected columns and a boolean history flag")
        _state_number(self.death_rate, "death_rate", low=0, high=1)
        _backend(self.hits, "hits")
        if self.death is not None:
            _backend(self.death, "death")
        for backend in (self.hits, self.death):
            if backend is not None and backend.n_features_in_ != self.columns.sum():
                raise ValueError("tree backend width differs from selected columns")

    @classmethod
    def from_state(cls, state):
        _state_fields(state, ("columns", "hits", "death", "death_rate", "history"))
        return cls(**deepcopy(state))

    def to_state(self):
        return deepcopy(
            {
                "columns": self.columns,
                "hits": self.hits,
                "death": self.death,
                "death_rate": self.death_rate,
                "history": self.history,
            }
        )

    def predict(self, rows):
        if not rows:
            return np.empty(0), np.empty(0)
        x = _row_features(rows, history=self.history, action=True)[:, self.columns]
        risk = (
            np.full(len(rows), self.death_rate)
            if self.death is None
            else self.death.predict_proba(x)[:, 1]
        )
        return self.hits.predict(x).clip(min=0), risk


@dataclass
class BehaviorReference:
    farm_frequency: float
    pipeline: object | None = None

    def __post_init__(self):
        _state_number(self.farm_frequency, "farm_frequency", low=0, high=1)
        if self.pipeline is not None:
            _backend(self.pipeline, "behavior")

    @classmethod
    def from_state(cls, state):
        _state_fields(state, ("farm_frequency", "pipeline"))
        return cls(**deepcopy(state))

    def to_state(self):
        return {"farm_frequency": self.farm_frequency, "pipeline": deepcopy(self.pipeline)}

    def predict(self, rows):
        if self.pipeline is None or not rows:
            return np.full(len(rows), self.farm_frequency)
        return self.pipeline.predict_proba(_row_features(rows))[:, 1]


def _unpack(parameters, window_width, static_width):
    filters = 8
    split = window_width * filters
    kernels = parameters[:split].reshape(window_width, filters)
    bias = parameters[split : split + filters]
    head = parameters[split + filters :].reshape(filters + static_width + 1, 2)
    return kernels, bias, head


def _forward(parameters, static, windows):
    kernels, bias, head = _unpack(parameters, windows.shape[-1], static.shape[-1])
    activations = np.tanh(windows @ kernels + bias)
    pooled = activations.mean(axis=1)
    features = np.column_stack((pooled, static, np.ones(len(static))))
    return features @ head, activations, features


@dataclass
class SequenceOutcome:
    history: bool
    static_scale: FeatureScale
    sequence_scale: FeatureScale
    parameters: np.ndarray
    hits_mean: float
    hits_std: float
    constant_death: float | None

    def __post_init__(self):
        if type(self.history) is not bool:
            raise ValueError("history must be boolean")
        if (
            type(self.static_scale) is not FeatureScale
            or type(self.sequence_scale) is not FeatureScale
        ):
            raise ValueError("sequence model requires FeatureScale states")
        self.parameters = _state_array(self.parameters, "parameters")
        window_width = self.sequence_scale.median.size * 4
        static_width = self.static_scale.median.size * 2 + 1
        expected = window_width * 8 + 8 + (8 + static_width + 1) * 2
        if self.parameters.size != expected:
            raise ValueError("parameter shape differs from feature scales")
        _state_number(self.hits_mean, "hits_mean", low=0)
        _state_number(self.hits_std, "hits_std", low=0)
        if self.constant_death is not None:
            _state_number(self.constant_death, "constant_death", low=0, high=1)

    @classmethod
    def from_state(cls, state):
        _state_fields(
            state,
            (
                "history",
                "static_scale",
                "sequence_scale",
                "parameters",
                "hits_mean",
                "hits_std",
                "constant_death",
            ),
        )
        return cls(
            state["history"],
            FeatureScale.from_state(state["static_scale"]),
            FeatureScale.from_state(state["sequence_scale"]),
            state["parameters"],
            state["hits_mean"],
            state["hits_std"],
            state["constant_death"],
        )

    def to_state(self):
        return {
            "history": self.history,
            "static_scale": self.static_scale.to_state(),
            "sequence_scale": self.sequence_scale.to_state(),
            "parameters": self.parameters.copy(),
            "hits_mean": self.hits_mean,
            "hits_std": self.hits_std,
            "constant_death": self.constant_death,
        }

    def predict(self, rows):
        static, sequence, actions = _sequence_inputs(rows, self.history)
        static, windows = _sequence_design(
            static, sequence, actions, self.static_scale, self.sequence_scale
        )
        output, _, _ = _forward(self.parameters, static, windows)
        hits = np.maximum(0, self.hits_mean + self.hits_std * output[:, 0])
        death = (
            expit(output[:, 1])
            if self.constant_death is None
            else np.full(len(rows), self.constant_death)
        )
        return hits, death


def _wave_rows(decisions):
    rows = []
    for decision in decisions:
        validate_decision(decision)
        if decision.key.domain != "wave":
            raise ValueError("reference states only support the wave domain")
        rows.append(decision.to_features())
    return rows


def predict_outcomes(state, decisions, proposed_actions):
    """Predict explicit candidates; does not consult observed actions or outcomes."""
    if type(state) not in (ActionMeans, TreeOutcome, SequenceOutcome):
        raise ValueError("expected a wave outcome state")
    rows = _wave_rows(decisions)
    actions = tuple(proposed_actions)
    if len(actions) != len(rows):
        raise ValueError("candidate action count differs from decision count")
    return state.predict(
        [{**row, "action": action} for row, action in zip(rows, actions, strict=True)]
    )


def predict_behavior(state, decisions):
    """Predict behavior from decisions only; the API has no action-label parameter."""
    if type(state) is not BehaviorReference:
        raise ValueError("expected a behavior reference state")
    return state.predict(_wave_rows(decisions))
