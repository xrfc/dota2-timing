"""Pure U191 action estimates from already fitted propensity and stratum state."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from numbers import Real
from types import MappingProxyType

import numpy as np

from dota_items.contracts.action_outcomes import DOMAINS, DecisionKey, validate_decision
from dota_items.modeling.awareness.action_features import encode_decision

TRIM = 0.05
BINS = 5
MIN_EFFECTIVE = 8
MIN_ROWS = 10
MIN_GAMES = 5
OVERLAP_REASONS = (
    "extreme_propensity",
    "outside_training_common_range",
    "sparse_training_arm",
)


def _finite(value, *, lower=None, upper=None):
    if (
        not isinstance(value, Real)
        or isinstance(value, (bool, np.bool_))
        or not np.isfinite(value)
        or (lower is not None and value < lower)
        or (upper is not None and value > upper)
    ):
        raise ValueError("expected a finite value within its declared range")


def _metrics(values, targets):
    if not isinstance(values, Mapping) or set(values) != set(targets):
        raise ValueError("incorrect action target fields")
    for value in values.values():
        if value is not None:
            _finite(value)


def _arms(values, arms, targets):
    if not isinstance(values, Mapping) or set(values) != set(arms):
        raise ValueError("incorrect action fields")
    for arm in arms:
        _metrics(values[arm], targets)


def _validate_payload(payload, domain):
    if type(domain) is not str or domain not in DOMAINS:
        raise ValueError("unknown action value domain")
    required = {"arms", "targets", "propensity", "frequency", "strata", "mean"}
    if not isinstance(payload, Mapping) or not required <= set(payload) <= required | {
        "common_range"
    }:
        raise ValueError("incorrect action value state fields")
    arms, targets = DOMAINS[domain]
    if (
        not isinstance(payload["arms"], (tuple, list))
        or not isinstance(payload["targets"], (tuple, list))
        or tuple(payload["arms"]) != arms
        or tuple(payload["targets"]) != targets
    ):
        raise ValueError("state actions or targets differ from the registered task")
    _finite(payload["frequency"], lower=0, upper=1)
    _arms(payload["mean"], arms, targets)
    if not isinstance(payload["strata"], Mapping):
        raise ValueError("strata must be a mapping")
    if payload["propensity"] is None:
        if payload["frequency"] not in (0, 1) or payload["strata"] or "common_range" in payload:
            raise ValueError("single-action state must preserve its absent common range")
        return
    if not callable(getattr(payload["propensity"], "predict_proba", None)):
        raise ValueError("propensity requires an already fitted prediction backend")
    common = payload.get("common_range")
    if not isinstance(common, (tuple, list)) or len(common) != 2:
        raise ValueError("two-action state requires a two-endpoint common range")
    for bound in common:
        _finite(bound, lower=0, upper=1)
    # Lower > upper represents a fitted model with no common support; retain it.
    if set(payload["strata"]) != set(range(BINS)) or any(
        type(key) is not int for key in payload["strata"]
    ):
        raise ValueError("expected the five fitted strata")
    for stratum in payload["strata"].values():
        if not isinstance(stratum, Mapping) or set(stratum) != {"arms", "balance"}:
            raise ValueError("incorrect stratum fields")
        if not isinstance(stratum["arms"], Mapping) or set(stratum["arms"]) != set(arms):
            raise ValueError("incorrect stratum actions")
        for stats in stratum["arms"].values():
            if not isinstance(stats, Mapping) or set(stats) != {
                "supported",
                "rows",
                "games",
                "arm_effective_n",
                "values",
                "effective_n",
            }:
                raise ValueError("incorrect fitted support fields")
            if type(stats["supported"]) is not bool or any(
                type(stats[key]) is not int or stats[key] < 0 for key in ("rows", "games")
            ):
                raise ValueError("incorrect support counts")
            if stats["games"] > stats["rows"]:
                raise ValueError("support games exceed rows")
            _finite(stats["arm_effective_n"], lower=0, upper=stats["rows"] + 1e-10)
            expected = (
                stats["rows"] >= MIN_ROWS
                and stats["games"] >= MIN_GAMES
                and stats["arm_effective_n"] >= MIN_EFFECTIVE
            )
            if stats["supported"] != expected:
                raise ValueError("support flag differs from fitted support statistics")
            _metrics(stats["values"], targets)
            if not isinstance(stats["effective_n"], Mapping) or set(stats["effective_n"]) != set(
                targets
            ):
                raise ValueError("incorrect target support fields")
            for effective in stats["effective_n"].values():
                _finite(effective, lower=0, upper=stats["rows"] + 1e-10)
        balance = stratum["balance"]
        if balance is not None:
            if not isinstance(balance, Mapping) or set(balance) != {"before", "after"}:
                raise ValueError("incorrect balance fields")
            for value in balance.values():
                _finite(value, lower=0)


@dataclass(frozen=True)
class ActionValueState:
    """Detached fitted state; this is not an artifact loader or a training interface."""

    domain: str
    _payload: Mapping

    def __post_init__(self):
        _validate_payload(self._payload, self.domain)
        object.__setattr__(self, "_payload", deepcopy(dict(self._payload)))

    @classmethod
    def from_state(cls, state, *, domain):
        return cls(domain, state)

    def to_state(self):
        _validate_payload(self._payload, self.domain)
        return deepcopy(dict(self._payload))


def pareto(values, targets):
    """Keep the frozen endpoint directions, tolerances and incomplete/tie behavior."""
    first, second = values
    differences = []
    for key in targets:
        a, b = values[first][key], values[second][key]
        if a is None or b is None:
            return "incomplete"
        if not np.isclose(a, b, rtol=1e-12, atol=1e-10):
            differences.append((a < b) if key in ("death", "dead_seconds") else (a > b))
    if not differences:
        return "tie"
    if all(differences):
        return first
    return "tradeoff" if any(differences) else second


def _frozen_arms(values):
    return MappingProxyType(
        {arm: MappingProxyType(dict(metrics)) for arm, metrics in values.items()}
    )


@dataclass(frozen=True)
class ActionEstimate:
    """Identity-bound prediction and its own fitted action-mean comparator."""

    key: DecisionKey
    propensity: float
    stratum: int
    overlap_reason: str | None
    ranking: str | None
    values: Mapping | None
    mean: Mapping

    def __post_init__(self):
        if type(self.key) is not DecisionKey:
            raise ValueError("prediction requires a DecisionKey")
        arms, targets = DOMAINS[self.key.domain]
        _finite(self.propensity, lower=0, upper=1)
        if type(self.stratum) is not int or self.stratum != min(
            BINS - 1, int(self.propensity * BINS)
        ):
            raise ValueError("prediction stratum does not match propensity")
        _arms(self.mean, arms, targets)
        object.__setattr__(self, "mean", _frozen_arms(self.mean))
        if self.values is None:
            if self.ranking is not None or self.overlap_reason not in OVERLAP_REASONS:
                raise ValueError("unsupported prediction requires an exclusion reason")
        else:
            _arms(self.values, arms, targets)
            if self.overlap_reason is not None or self.ranking != pareto(self.values, targets):
                raise ValueError("supported prediction ranking is inconsistent")
            object.__setattr__(self, "values", _frozen_arms(self.values))

    def to_record(self):
        """Return detached numeric output; observed outcomes are never included."""
        return {
            "propensity": self.propensity,
            "stratum": self.stratum,
            "overlap_reason": self.overlap_reason,
            "ranking": self.ranking,
            "values": None if self.values is None else {a: dict(v) for a, v in self.values.items()},
        }


def estimate_actions(state, decisions):
    """Estimate both registered actions using only decision-time features."""
    if type(state) is not ActionValueState:
        raise ValueError("expected ActionValueState")
    _validate_payload(state._payload, state.domain)
    decisions = tuple(decisions)
    for decision in decisions:
        validate_decision(decision)
        if decision.key.domain != state.domain:
            raise ValueError("decision and fitted state have different domains")
    if len({decision.key for decision in decisions}) != len(decisions):
        raise ValueError("duplicate decision identity")
    if not decisions:
        return []
    model = state._payload
    if model["propensity"] is None:
        propensity = np.full(len(decisions), model["frequency"])
    else:
        probabilities = np.asarray(model["propensity"].predict_proba(encode_decision(decisions)))
        if probabilities.shape != (len(decisions), 2):
            raise ValueError("propensity backend returned an incorrect shape")
        propensity = probabilities[:, 1]
    results = []
    for decision, probability in zip(decisions, propensity, strict=True):
        _finite(probability, lower=0, upper=1)
        p = float(probability)
        i = min(BINS - 1, int(p * BINS))
        reason, ranking, values = None, None, None
        if not TRIM <= p <= 1 - TRIM:
            reason = "extreme_propensity"
        elif not model["common_range"][0] - 1e-12 <= p <= model["common_range"][1] + 1e-12:
            reason = "outside_training_common_range"
        elif not all(a["supported"] for a in model["strata"][i]["arms"].values()):
            reason = "sparse_training_arm"
        else:
            values = {arm: model["strata"][i]["arms"][arm]["values"] for arm in model["arms"]}
            ranking = pareto(values, model["targets"])
        results.append(ActionEstimate(decision.key, p, i, reason, ranking, values, model["mean"]))
    return results
