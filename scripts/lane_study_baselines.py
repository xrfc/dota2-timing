"""Fold-local models for recognized position-one wave actions and their observed outcomes."""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _is_farm(row):
    if row["action"] not in ("farm", "retreat"):
        raise ValueError("training and outcome prediction require a recognized wave action")
    return int(row["action"] == "farm")


def _features(rows, *, history=False, action=False):
    # This whitelist is also used at inference, when outcomes and actions may be unavailable.
    values = []
    for row in rows:
        frames = row["sequence"] if history else row["sequence"][-1:]
        vector = [*row["static"], *(value for frame in frames for value in frame)]
        if action:
            vector.append(_is_farm(row))
        values.append(vector)
    return np.asarray(values, dtype=float)


@dataclass
class ActionMeans:
    means: dict

    def predict(self, rows):
        expected = [self.means.get(row["action"], (np.nan, np.nan)) for row in rows]
        hits, death = np.asarray(expected, dtype=float).reshape(-1, 2).T
        return hits, death


@dataclass
class TreeOutcome:
    columns: np.ndarray
    hits: HistGradientBoostingRegressor
    death: HistGradientBoostingClassifier | None
    death_rate: float
    history: bool

    @classmethod
    def fit(cls, train, seed, *, history=False):
        if not train:
            raise ValueError("outcome model requires training rows")
        x = _features(train, history=history, action=True)
        columns = ~np.isnan(x).all(axis=0)
        x = x[:, columns]
        hit_counts = np.asarray([r["hits"] for r in train], dtype=float)
        deaths = np.asarray([r["death"] for r in train], dtype=int)
        params = dict(
            max_iter=100,
            max_leaf_nodes=15,
            learning_rate=0.1,
            min_samples_leaf=20,
            early_stopping=False,
            random_state=seed,
        )
        hits = HistGradientBoostingRegressor(**params).fit(x, hit_counts)
        death = None
        if np.unique(deaths).size == 2:
            death = HistGradientBoostingClassifier(**params).fit(x, deaths)
        return cls(columns, hits, death, float(deaths.mean()), history)

    def predict(self, rows):
        if not rows:
            return np.empty(0), np.empty(0)
        x = _features(rows, history=self.history, action=True)[:, self.columns]
        risk = (
            np.full(len(rows), self.death_rate)
            if self.death is None
            else self.death.predict_proba(x)[:, 1]
        )
        return self.hits.predict(x).clip(min=0), risk


def fit_outcomes(train, test, seed):
    """Fit action means and a decision-frame tree on one fold and predict the test rows."""
    tree = TreeOutcome.fit(train, seed)
    by_action = {}
    for action in ("farm", "retreat"):
        outcomes = [(r["hits"], r["death"]) for r in train if r["action"] == action]
        if outcomes:
            by_action[action] = np.mean(outcomes, axis=0)
    models = {"action_mean": ActionMeans(by_action), "last_frame_tree": tree}
    return {name: model.predict(test) for name, model in models.items()}, models


@dataclass
class BehaviorReference:
    farm_frequency: float
    pipeline: object | None = None

    def predict(self, rows):
        if self.pipeline is None or not rows:
            return np.full(len(rows), self.farm_frequency)
        return self.pipeline.predict_proba(_features(rows))[:, 1]


def fit_behavior(train, test, seed):
    """Estimate P(farm | recognized action, decision-time features) on one fold."""
    if not train:
        raise ValueError("behavior model requires training rows")
    targets = np.asarray([_is_farm(row) for row in train])
    frequency = float(targets.mean())
    models = {"frequency": BehaviorReference(frequency)}
    pipeline = None
    if np.unique(targets).size == 2:
        pipeline = make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
            StandardScaler(),
            LogisticRegression(C=1, max_iter=1000, random_state=seed),
        ).fit(_features(train), targets)
    models["logistic"] = BehaviorReference(frequency, pipeline)
    return {name: model.predict(test) for name, model in models.items()}, models
