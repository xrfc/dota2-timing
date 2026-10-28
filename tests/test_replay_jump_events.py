"""Boundary, illusion, ambiguity and provenance regressions for offline associations."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from dota_items.data.replay_jump_events import inspect_jumps


def fixture(events):
    state = {"life_state": 0, "tick": 100}
    jump = dict(
        player_slot=0,
        previous={"source_tick": 100},
        current={"source_tick": 130},
        previous_states=[state],
        current_states=[{**state, "tick": 130}],
        distance_native_units=1500,
    )
    raw = dict(
        match_id=1,
        players=[dict(player_id=0, hero_name="npc_dota_hero_queen_of_pain")],
        combat_log=events,
    )
    return raw, dict(match_id=1, jumps=[jump], life_transitions=[])


def event(tick=115, **kw):
    return dict(
        tick=tick,
        log_type="ABILITY",
        attacker_name="npc_dota_hero_queenofpain",
        attacker_is_hero=True,
        attacker_is_illusion=False,
        target_name="",
        target_is_hero=False,
        target_is_illusion=False,
        inflictor_name="queenofpain_blink",
        value=0,
        **kw,
    )


@pytest.mark.parametrize(
    ("tick", "category"),
    [
        (100, "previous_tick_boundary_event"),
        (101, "core_movement_event"),
        (130, "core_movement_event"),
        (131, "unresolved"),
        (99, "preceding_movement_context"),
        (39, "unresolved"),
    ],
)
def test_tick_boundaries(tick, category):
    raw, audit = fixture([event(tick)])
    assert inspect_jumps(raw, audit)["jumps"][0]["category"] == category


def test_illusion_and_missing_flags_are_not_real_hero():
    for flag in (True, None):
        e = event()
        e["attacker_is_illusion"] = flag
        raw, audit = fixture([e])
        assert inspect_jumps(raw, audit)["jumps"][0]["events"] == []


def test_same_tick_duplicates_not_collapsed_and_input_immutable():
    raw, audit = fixture([event(), event()])
    before = deepcopy((raw, audit))
    result = inspect_jumps(raw, audit)
    assert result["multiple_candidate_jumps"] == 1
    assert result["jumps"][0]["candidate_count"] == 2
    assert (raw, audit) == before
    assert result["training_admission"] is False
    assert result["jumps"][0]["causal_mechanism_confirmed"] is False


def test_glimpse_caster_not_displaced_by_own_cast():
    e = event()
    e["inflictor_name"] = "disruptor_glimpse"
    raw, audit = fixture([e])
    assert inspect_jumps(raw, audit)["jumps"][0]["category"] == "unresolved"


def test_recovery_and_buyback_player_id():
    e = event()
    e.update(log_type="BUYBACK", attacker_name="", value=0)
    raw, audit = fixture([e])
    prev = {"life_state": 2, "tick": 100}
    curr = {"life_state": 0, "tick": 130}
    audit["life_transitions"] = [
        dict(player_slot=0, kind="life_state_change", previous=prev, current=curr)
    ]
    result = inspect_jumps(raw, audit)
    assert result["jumps"][0]["category"] == "recovery_interval"
    assert result["recoveries"][0]["category"] == "buyback_near_recovery"
    raw["combat_log"][0]["value"] = 1
    assert inspect_jumps(raw, audit)["recoveries"][0]["category"] == "recovery_mechanism_unresolved"


def test_dead_endpoint_not_movement_label():
    raw, audit = fixture([event()])
    audit["jumps"][0]["previous_states"][0]["life_state"] = 2
    assert inspect_jumps(raw, audit)["jumps"][0]["category"] == "nonliving_endpoint"


def test_wrong_match_rejected():
    raw, audit = fixture([])
    raw["match_id"] = 2
    with pytest.raises(ValueError, match="identity"):
        inspect_jumps(raw, audit)


def runner():
    spec = importlib.util.spec_from_file_location(
        "jump_cli", Path("scripts/audit_replay_jump_events.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_output_rejected(tmp_path):
    with pytest.raises(ValueError, match="Output exists"):
        runner().run(tmp_path, tmp_path)


def test_hash_mismatch_rejected(tmp_path):
    import json

    source = tmp_path / "input" / "1"
    source.mkdir(parents=True)
    (source / "receipt.json").write_text(json.dumps({"audit_sha256": "wrong"}))
    (source / "audit.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        runner().run(source.parent, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_teleport_remove_does_not_certify_success():
    e = event()
    e.update(
        log_type="MODIFIER_REMOVE",
        inflictor_name="modifier_teleporting",
        target_name=e["attacker_name"],
        target_is_hero=True,
    )
    raw, audit = fixture([e])
    row = inspect_jumps(raw, audit)["jumps"][0]
    assert row["category"] == "core_movement_event"
    assert row["causal_mechanism_confirmed"] is False


def test_reincarnation_flag_and_stale_death_not_reused():
    e = event(70)
    e.update(
        log_type="DEATH", target_name=e["attacker_name"], target_is_hero=True, will_reincarnate=True
    )
    raw, audit = fixture([e])
    audit["life_transitions"] = [
        dict(
            player_slot=0,
            kind="life_state_change",
            previous={"life_state": 0, "tick": 60},
            current={"life_state": 1, "tick": 90},
        ),
        dict(
            player_slot=0,
            kind="life_state_change",
            previous={"life_state": 2, "tick": 100},
            current={"life_state": 0, "tick": 130},
        ),
    ]
    assert (
        inspect_jumps(raw, audit)["recoveries"][0]["category"]
        == "reincarnation_flag_near_prior_death"
    )
    raw["combat_log"][0]["tick"] = 1
    assert inspect_jumps(raw, audit)["recoveries"][0]["category"] == "recovery_mechanism_unresolved"


def test_shared_event_is_reported_not_deduplicated():
    raw, audit = fixture([event()])
    audit["jumps"].append(deepcopy(audit["jumps"][0]))
    result = inspect_jumps(raw, audit)
    assert result["reused_candidate_events"] == {"combat_log[0]": 2}
