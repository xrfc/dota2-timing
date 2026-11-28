"""Synthetic state parity against independent frozen-source processes; no fit calls."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from action_legacy_values_runner import propensity_pipeline

from dota_items.contracts.action_outcomes import (
    DOMAINS,
    DecisionInput,
    DecisionKey,
    ObservedOutcome,
    decision_from_row,
    observation_from_row,
    task_spec,
)
from dota_items.modeling.awareness.action_evaluation import (
    compare_reference,
    evaluate_factual,
    join_observed,
    join_reference,
    summarize_reference,
)
from dota_items.modeling.awareness.action_values import (
    ActionValueState,
    estimate_actions,
    pareto,
)

RUNNER = Path(__file__).with_name("action_legacy_values_runner.py")


class SyntheticPropensity:
    def predict_proba(self, features):
        p = features[:, 1]
        return np.column_stack((1 - p, p))


class BadPropensity:
    def __init__(self, result):
        self.result = result

    def predict_proba(self, _features):
        return self.result


def oracle(payload):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1"}
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return json.loads(result.stdout)


def model_state(domain="wave"):
    arms, targets = DOMAINS[domain]
    first = {key: 10.0 for key in targets}
    first.update(hits=3.0, death=0.1, dead_seconds=2.0)
    second = {**first, "hits": 2.0, "gold": 8.0, "death": 0.2}
    if domain == "support":
        first["arrival"], second["arrival"] = 0.8, 0.7
    means = {arms[0]: first, arms[1]: second}
    strata = {}
    for index in range(5):
        strata[index] = {
            "arms": {
                arm: {
                    "supported": True,
                    "rows": 12,
                    "games": 6,
                    "arm_effective_n": 11.5,
                    "values": dict(means[arm]),
                    "effective_n": dict.fromkeys(targets, 11.5),
                }
                for arm in arms
            },
            "balance": {"before": 0.2, "after": 0.1},
        }
    return {
        "arms": arms,
        "targets": targets,
        "propensity": SyntheticPropensity(),
        "frequency": 0.5,
        "strata": strata,
        "mean": means,
        "common_range": (0.05, 0.95),
    }


def decisions(domain="wave", probabilities=(0.5,)):
    width = len(task_spec(domain).static_features)
    return [
        DecisionInput(
            DecisionKey(index + 1, "synthetic_hero", 900, domain),
            (900, p, *([1.0] * (width - 2))),
            ((), (), (1.0,) * 7),
        )
        for index, p in enumerate(probabilities)
    ]


def rows_for(items):
    result = []
    for index, item in enumerate(items):
        arms, targets = DOMAINS[item.key.domain]
        row = {
            "match": item.key.match,
            "hero": item.key.hero,
            "t": item.key.t,
            "domain": item.key.domain,
            "fold": index % 5,
            "action": arms[index % 2],
            "rank_band": "high" if index % 2 else "medium",
            "recent_damage": bool(index % 2),
            **item.to_features(),
            **{key: 5.0 for key in targets},
        }
        row.update(hits=4, death=index % 2, gold=-index, xp=None if index % 3 else 10.0)
        if "arrival" in targets:
            row["arrival"] = index % 2
        result.append(row)
    return result


def oracle_state(state):
    result = deepcopy(state)
    result["propensity"] = "synthetic" if result["propensity"] is not None else None
    return result


@pytest.mark.parametrize("domain", DOMAINS)
def test_full_domain_predictions_join_and_metrics_match_frozen_process(domain):
    payload = model_state(domain)
    items = decisions(domain, (0.0, 0.0499, 0.05, 0.2, 0.5, 0.8, 0.95, 0.95001, 1.0))
    rows = rows_for(items)
    expected = oracle(
        {"operation": "values", "state": oracle_state(payload), "rows": rows, "evaluate": True}
    )
    state = ActionValueState.from_state(payload, domain=domain)
    predictions = estimate_actions(state, items)
    assert [prediction.to_record() for prediction in predictions] == expected["predictions"]
    observations = [observation_from_row(row) for row in reversed(rows)]
    records = join_observed(predictions, observations)
    assert [{k: v for k, v in record.items() if k != "domain"} for record in records] == expected[
        "records"
    ]
    arms, targets = DOMAINS[domain]
    assert evaluate_factual(records, arms, targets) == expected["summary"]
    assert [
        p.to_record() for p in estimate_actions(state, [decision_from_row(r) for r in rows])
    ] == expected["predictions"]


@pytest.mark.parametrize(
    "kind", ("sparse", "outside", "empty_overlap", "missing", "tradeoff", "tie", "second")
)
def test_support_and_ranking_branches_have_exact_legacy_parity(kind):
    payload = model_state()
    arm, second = payload["arms"]
    stats = payload["strata"][2]["arms"]
    if kind == "sparse":
        stats[arm].update(supported=False, rows=0, games=0, arm_effective_n=0.0)
        stats[arm]["effective_n"] = dict.fromkeys(payload["targets"], 0.0)
        payload["strata"][2]["balance"] = None
    elif kind == "outside":
        payload["common_range"] = (0.6, 0.9)
    elif kind == "empty_overlap":
        payload["common_range"] = (0.7, 0.3)
    elif kind == "missing":
        stats[arm]["values"]["gold"] = None
    elif kind == "tradeoff":
        stats[arm]["values"]["death"] = 0.9
    elif kind == "tie":
        stats[second]["values"] = dict(stats[arm]["values"])
        stats[second]["values"]["gold"] += 1e-11
    elif kind == "second":
        stats[arm]["values"], stats[second]["values"] = (
            stats[second]["values"],
            stats[arm]["values"],
        )
    items = decisions()
    expected = oracle(
        {"operation": "values", "state": oracle_state(payload), "rows": rows_for(items)}
    )
    result = estimate_actions(ActionValueState.from_state(payload, domain="wave"), items)
    assert [record.to_record() for record in result] == expected["predictions"]


@pytest.mark.parametrize("frequency", (0.0, 1.0))
def test_single_action_absent_common_range_is_preserved(frequency):
    payload = model_state()
    payload.update(propensity=None, frequency=frequency, strata={})
    payload.pop("common_range")
    state = ActionValueState.from_state(payload, domain="wave")
    assert state.to_state() == payload
    expected = oracle(
        {"operation": "values", "state": oracle_state(payload), "rows": rows_for(decisions())}
    )
    assert [p.to_record() for p in estimate_actions(state, decisions())] == expected["predictions"]
    assert estimate_actions(state, []) == []


def test_common_range_tolerance_and_bin_boundaries_match():
    payload = model_state()
    payload["common_range"] = (0.2, 0.8)
    items = decisions(probabilities=(0.2 - 2e-12, 0.2 - 5e-13, 0.2, 0.8, 0.8 + 5e-13, 0.8 + 2e-12))
    expected = oracle(
        {"operation": "values", "state": oracle_state(payload), "rows": rows_for(items)}
    )
    assert [
        p.to_record()
        for p in estimate_actions(ActionValueState.from_state(payload, domain="wave"), items)
    ] == expected["predictions"]


def test_state_and_prediction_are_detached_from_input_and_export_mutation():
    payload = model_state()
    state = ActionValueState.from_state(payload, domain="wave")
    prediction = estimate_actions(state, decisions())[0]
    payload["mean"]["farm"]["gold"] = -999
    state.to_state()["mean"]["farm"]["gold"] = -888
    prediction.to_record()["values"]["farm"]["gold"] = -777
    assert prediction.mean["farm"]["gold"] == 10.0
    assert prediction.values["farm"]["gold"] == 10.0
    with pytest.raises(TypeError):
        prediction.mean["farm"]["gold"] = 1
    with pytest.raises(TypeError):
        prediction.values["farm"]["gold"] = 1
    assert estimate_actions(state, decisions())[0] == prediction


def test_future_fields_and_fold_cannot_change_prediction():
    state = ActionValueState.from_state(model_state(), domain="wave")
    row = rows_for(decisions())[0]
    first = estimate_actions(state, [decision_from_row(row)])[0]
    changed = {**row, "action": "unknown", "gold": -1e20, "death": 1, "fold": 99}
    assert estimate_actions(state, [decision_from_row(changed)])[0] == first
    with pytest.raises(ValueError):
        estimate_actions(state, [row])


@pytest.mark.parametrize(
    "mutation",
    ("extra", "missing", "arms", "targets", "counts", "shape", "backend", "frequency", "domain"),
)
def test_invalid_fitted_state_is_rejected(mutation):
    payload = model_state()
    domain = "wave"
    if mutation == "extra":
        payload["fit"] = True
    elif mutation == "missing":
        payload.pop("common_range")
    elif mutation == "arms":
        payload["arms"] = tuple(reversed(payload["arms"]))
    elif mutation == "targets":
        payload["targets"] = ("gold",)
    elif mutation == "counts":
        payload["strata"][2]["arms"]["farm"]["rows"] = 1
    elif mutation == "shape":
        payload["strata"].pop(1)
    elif mutation == "backend":
        payload["propensity"] = object()
    elif mutation == "frequency":
        payload["frequency"] = float("nan")
    elif mutation == "domain":
        domain = "support"
    with pytest.raises(ValueError):
        ActionValueState.from_state(payload, domain=domain)


@pytest.mark.parametrize("result", ([[0.5]], [[0.5, float("nan")]], [[-0.2, 1.2]]))
def test_bad_prediction_backend_output_is_rejected(result):
    payload = model_state()
    payload["propensity"] = BadPropensity(np.asarray(result))
    with pytest.raises(ValueError):
        estimate_actions(ActionValueState.from_state(payload, domain="wave"), decisions())


def test_domain_and_registered_feature_dimensions_are_checked():
    state = ActionValueState.from_state(model_state(), domain="wave")
    with pytest.raises(ValueError):
        estimate_actions(state, decisions("jungle"))
    with pytest.raises(ValueError):
        estimate_actions(state, [replace(decisions()[0], static=(1.0,))])
    with pytest.raises(ValueError, match="duplicate"):
        estimate_actions(state, decisions() * 2)


@pytest.mark.parametrize("domain", DOMAINS)
def test_actual_sklearn_pipeline_missingness_and_state_roundtrip_match_old(domain, monkeypatch):
    import scipy.optimize
    from sklearn.impute import MissingIndicator, SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    def no_fitting(*args, **kwargs):
        raise AssertionError("M1 must not fit, including synthetic fixture preparation")

    for backend in (MissingIndicator, SimpleImputer, LogisticRegression, Pipeline, StandardScaler):
        monkeypatch.setattr(backend, "fit", no_fitting)
    monkeypatch.setattr(scipy.optimize, "minimize", no_fitting)
    items = decisions(domain, (0.2, 0.5, 0.8))
    items = [
        replace(
            item,
            static=(*item.static[:1], None if index == 0 else item.static[1], *item.static[2:]),
            sequence=((), (), (1.0, 1.0, 1.0, 1.0, 1.0, None, 1.0)),
        )
        for index, item in enumerate(items)
    ]
    payload = model_state(domain)
    payload["propensity"] = propensity_pipeline(len(items[0].static) + 7)
    serialized = oracle_state(payload)
    serialized["propensity"] = "pipeline"
    expected = oracle({"operation": "values", "state": serialized, "rows": rows_for(items)})
    state = ActionValueState.from_state(payload, domain=domain)
    restored = ActionValueState.from_state(state.to_state(), domain=domain)
    actual = [p.to_record() for p in estimate_actions(restored, items)]
    assert actual == expected["predictions"]
    assert all(record["values"] is not None for record in actual)
    np.testing.assert_array_equal(
        state.to_state()["propensity"][-1].coef_, payload["propensity"][-1].coef_
    )
    payload["propensity"][-1].coef_[0, :] = 999
    exported = state.to_state()
    exported["propensity"][-1].coef_[0, :] = -999
    assert [p.to_record() for p in estimate_actions(state, items)] == actual


@pytest.mark.parametrize(
    "kind",
    (
        "duplicate_prediction",
        "duplicate_observed",
        "missing",
        "extra",
        "wrong_domain",
        "wrong_hero",
        "wrong_time",
        "wrong_match",
    ),
)
def test_key_join_rejects_identity_mismatch(kind):
    items = decisions(probabilities=(0.5, 0.6))
    preds = estimate_actions(ActionValueState.from_state(model_state(), domain="wave"), items)
    obs = [observation_from_row(row) for row in rows_for(items)]
    if kind == "duplicate_prediction":
        preds = [preds[0], preds[0]]
    elif kind == "duplicate_observed":
        obs = [obs[0], obs[0]]
    elif kind == "missing":
        obs = obs[:1]
    elif kind == "extra":
        obs.append(replace(obs[0], key=replace(obs[0].key, t=901)))
    elif kind == "wrong_domain":
        obs[0] = replace(obs[0], key=replace(obs[0].key, domain="jungle"), action="continue_jungle")
    elif kind == "wrong_hero":
        obs[0] = replace(obs[0], key=replace(obs[0].key, hero="different"))
    elif kind == "wrong_time":
        obs[0] = replace(obs[0], key=replace(obs[0].key, t=901))
    elif kind == "wrong_match":
        obs[0] = replace(obs[0], key=replace(obs[0].key, match=99))
    with pytest.raises(ValueError):
        join_observed(preds, obs)


def test_join_rejects_wrong_fold_and_incomplete_targets():
    first = decisions()[0]
    second = replace(first, key=replace(first.key, t=901))
    predictions = estimate_actions(
        ActionValueState.from_state(model_state(), domain="wave"), [first, second]
    )
    obs = [observation_from_row(row) for row in rows_for([first, second])]
    with pytest.raises(ValueError, match="fold"):
        join_observed(predictions, obs)
    with pytest.raises(ValueError, match="incomplete"):
        join_observed(predictions[:1], [replace(obs[0], values={"hits": 1})])


@pytest.mark.parametrize("behavior", (False, True))
@pytest.mark.parametrize("single", (False, True))
def test_reference_metrics_match_old_process_with_identity_join(behavior, single):
    items = decisions(probabilities=(0.5,) * 6)
    rows = rows_for(items)
    if single:
        rows = [{**row, "death": 0, "action": "farm"} for row in rows]
    predictions = {
        item.key: {"p_farm": (i + 1) / 8}
        if behavior
        else {"hits_pred": i / 2, "p_death": (i + 1) / 8}
        for i, item in enumerate(items)
    }
    observations = [observation_from_row(row) for row in reversed(rows)]
    joined = join_reference(predictions, observations, behavior=behavior)
    expected = oracle({"operation": "reference", "rows": joined, "behavior": behavior})
    assert summarize_reference(joined, behavior=behavior) == expected


def test_reference_paired_match_bootstrap_matches_frozen_process():
    items = decisions(probabilities=(0.5,) * 6)
    observations = [observation_from_row(row) for row in rows_for(items)]
    predictions = {
        item.key: {"hits_pred": i / 2, "p_death": (i + 1) / 8} for i, item in enumerate(items)
    }
    first = join_reference(predictions, observations)
    second = [{**r, "hits_pred": r["hits_pred"] + 0.25, "p_death": 0.5} for r in first]
    expected = oracle({"operation": "reference", "rows": first, "second": second})
    assert summarize_reference(first) == expected["summary"]
    assert compare_reference(first, second) == expected["paired"]
    with pytest.raises(ValueError):
        compare_reference([first[0], first[0]], second)
    with pytest.raises(ValueError):
        compare_reference(first, second[:-1])
    with pytest.raises(ValueError):
        compare_reference([], [])


def test_empty_evaluation_matches_frozen_process():
    arms, targets = DOMAINS["wave"]
    state = model_state()
    expected = oracle(
        {"operation": "values", "state": oracle_state(state), "rows": [], "evaluate": True}
    )
    assert join_observed([], []) == []
    assert evaluate_factual([], arms, targets) == expected["summary"]
    assert summarize_reference([]) == oracle({"operation": "reference", "rows": []})


def test_reference_join_rejects_bad_fields_unknown_identity_or_missing_outcomes():
    item = decisions()[0]
    observation = observation_from_row(rows_for([item])[0])
    with pytest.raises(ValueError):
        join_reference({item.key: {"hits_pred": 2, "p_death": 0.3, "death": 0}}, [observation])
    with pytest.raises(ValueError):
        join_reference({item.key: {"hits_pred": 2, "p_death": 1.3}}, [observation])
    with pytest.raises(ValueError):
        join_reference({item.key: {"hits_pred": 2, "p_death": 0.3}}, [])
    with pytest.raises(ValueError):
        join_reference(
            {item.key: {"hits_pred": 2, "p_death": 0.3}}, [replace(observation, values={})]
        )
    behavior = ObservedOutcome(item.key, 0, "farm", {})
    assert (
        join_reference({item.key: {"p_farm": 0.3}}, [behavior], behavior=True)[0]["p_farm"] == 0.3
    )


def test_reference_join_accepts_actual_numpy_predictions_from_new_models():
    from dota_items.modeling.awareness.action_models import (
        ActionMeans,
        BehaviorReference,
        predict_behavior,
        predict_outcomes,
    )

    items = decisions(probabilities=(0.5, 0.6))
    observations = [observation_from_row(row) for row in rows_for(items)]
    means = ActionMeans({"farm": (3.0, 0.2), "retreat": (2.0, 0.1)})
    hits, risks = predict_outcomes(means, items, ["farm", "retreat"])
    predictions = {
        item.key: {"hits_pred": hits[index], "p_death": risks[index]}
        for index, item in enumerate(items)
    }
    joined = join_reference(predictions, observations)
    assert all(type(row["hits_pred"]) is float for row in joined)
    assert summarize_reference(joined)["cases"] == 2
    probabilities = predict_behavior(BehaviorReference(0.4), items)
    joined_behavior = join_reference(
        {item.key: {"p_farm": probabilities[index]} for index, item in enumerate(items)},
        observations,
        behavior=True,
    )
    assert summarize_reference(joined_behavior, behavior=True)["cases"] == 2


def test_pareto_endpoint_directions_and_tolerance():
    values = {"farm": {"gold": 10, "death": 0.2}, "retreat": {"gold": 3, "death": 0.1}}
    assert pareto(values, ("gold", "death")) == "tradeoff"
    values["farm"]["gold"] = None
    assert pareto(values, ("gold", "death")) == "incomplete"
