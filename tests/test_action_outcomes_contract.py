"""U191 semantics and decision/observation boundaries, using synthetic rows only."""

from dataclasses import FrozenInstanceError, fields

import pytest

from dota_items.contracts.action_outcomes import (
    DecisionInput,
    DecisionKey,
    ObservedOutcome,
    decision_from_row,
    observation_from_row,
    task_spec,
    validate_decision,
    validate_observed,
)


def row(domain="wave"):
    spec = task_spec(domain)
    return dict(
        match=101,
        hero="synthetic_hero",
        t=900,
        domain=domain,
        fold=1,
        action=spec.actions[0],
        static=list(range(len(spec.static_features))),
        sequence=[[None] * 7, [0.0] * 7, [1.0] * 7],
        **{target: None for target in spec.targets},
    )


@pytest.mark.parametrize(
    "domain,actions,width",
    [
        ("wave", ("farm", "retreat"), 7),
        ("jungle", ("continue_jungle", "leave_camp"), 10),
        ("support", ("approach", "stay"), 10),
    ],
)
def test_registered_semantics(domain, actions, width):
    spec = task_spec(domain)
    assert spec.actions == actions
    assert len(spec.static_features) == width
    assert len(spec.sequence_features) == 7
    assert spec.history_offsets == (-10, -5, 0)
    assert spec.action_window == (0, 6)
    assert spec.outcome_window == (6, 20)
    assert spec.interval == "(start,end]"
    assert spec.split_id == "lane-study-v1" and spec.folds == 5
    assert spec.gold_definition == "wallet_at_t_plus_20_minus_wallet_at_t_plus_6"
    assert ("arrival" in spec.targets) == (domain == "support")
    assert validate_decision(decision_from_row(row(domain)))
    assert validate_observed(observation_from_row(row(domain)))


def test_future_and_audit_fields_cannot_enter_prediction():
    source = row()
    first = decision_from_row(source)
    source.update(action="retreat", gold=10000, death=1, hits=50, fold=4, future_secret=99)
    assert decision_from_row(source) == first
    assert set(first.to_features()) == {"static", "sequence"}
    assert {f.name for f in fields(DecisionInput)} == {"key", "static", "sequence"}
    copied = first.to_features()
    copied["static"][0] = 999
    assert first.static[0] == 0


def test_input_and_observation_are_immutable():
    source = row()
    d = decision_from_row(source)
    o = observation_from_row(source)
    source["sequence"][0][0] = 77
    assert d.sequence[0][0] is None
    with pytest.raises(FrozenInstanceError):
        d.key = DecisionKey(102, "x", 901, "wave")
    with pytest.raises(TypeError):
        o.values["hits"] = 9


def test_small_legacy_container_and_ragged_family_boundary():
    key = DecisionKey(101, "x", 900, "wave")
    small = DecisionInput(key, [1, 2], [[], [], [3, 4]])
    assert small.to_features()["sequence"] == [[], [], [3, 4]]
    with pytest.raises(ValueError, match="dimensions"):
        validate_decision(small)
    full = DecisionInput(key, [None] * 7, [[], [], [1] * 7])
    assert validate_decision(full) is full
    for frames in ([[1] * 7], [[], [1] * 6, [1] * 7], [[], [], []]):
        with pytest.raises(ValueError, match="dimensions"):
            validate_decision(DecisionInput(key, [1] * 7, frames))


@pytest.mark.parametrize(
    "changes",
    [
        {"match": True},
        {"match": 0},
        {"hero": ""},
        {"t": 1.5},
        {"domain": "unknown"},
        {"static": [True] * 7},
        {"static": ["1"] * 7},
    ],
)
def test_bad_identity_and_input_types_rejected(changes):
    source = row()
    source.update(changes)
    with pytest.raises(ValueError):
        decision_from_row(source)


def test_observed_validation_does_not_certify_membership():
    source = row()
    source["gold"] = -100
    assert observation_from_row(source).values["gold"] == -100
    partial = ObservedOutcome(decision_from_row(source).key, 1, "farm", {"hits": None})
    assert validate_observed(partial, complete=False) is partial
    with pytest.raises(ValueError, match="incomplete"):
        validate_observed(partial)
    for changes in ({"fold": 5}, {"fold": True}, {"action": "unknown"}, {"gold": float("nan")}):
        with pytest.raises(ValueError):
            observation_from_row({**source, **changes})
    # Fold assignment and data provenance are the future reader's responsibility.
    assert observation_from_row({**source, "fold": 4}).fold == 4


def test_domain_mismatch_missing_targets_and_unregistered_task():
    with pytest.raises(ValueError, match="domain mismatch"):
        decision_from_row(row(), domain="jungle")
    source = row()
    del source["gold"]
    with pytest.raises(KeyError):
        observation_from_row(source)
    with pytest.raises(ValueError, match="unregistered"):
        task_spec("stay_lane")


def test_feature_column_names_match_frozen_source_inventory():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "docs/acceptance/action-m1-baseline.json"
    constants = json.loads(path.read_text())["constants_from_ast"]
    assert task_spec("wave").static_features == tuple(
        constants["scripts/lane_study_data.py"]["STATIC"]
    )
    assert task_spec("wave").sequence_features == tuple(
        constants["scripts/lane_study_data.py"]["SEQUENCE"]
    )
    for domain in ("jungle", "support"):
        assert task_spec(domain).static_features == tuple(
            constants["scripts/outcome_domains.py"]["STATIC"]
        )
        assert task_spec(domain).sequence_features == task_spec("wave").sequence_features
