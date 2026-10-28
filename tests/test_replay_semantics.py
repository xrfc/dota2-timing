"""Audit controls: detect broken provenance, clock joins and coordinate leakage."""

import copy
import json

import pytest

from dota_items.data.observer import ObserverIndex
from dota_items.data.replay_semantics import (
    TickIndex,
    check_observer_leakage,
    corroborate_deaths,
    inspect_match,
    make_clock,
    mutate_positions,
    run_audit,
    warning_audit,
)


def fixture():
    raw = dict(
        match_id=7,
        duration=3,
        game_start_tick=30,
        game_end_tick=150,
        game_clock={"game_start_tick": 30, "pauses": []},
        players=[],
        combat_log=[],
    )
    channels = dict(
        coach_state_snapshots=[],
        hero_visibility_events=[],
        entity_visibility_events=[],
        combat_log=[],
    )
    match = dict(match_id=7, duration=3, players=[], context={"channels": channels})
    for pid in range(10):
        slot = pid if pid < 5 else pid + 123
        raw["players"].append(
            dict(
                player_id=pid,
                hero_name=f"hero_{pid}",
                position_log=[[t * 30 + 30, t, pid] for t in range(4)],
            )
        )
        match["players"].append(
            dict(
                player_slot=slot,
                hero_id=pid + 1,
                position_log=[
                    dict(
                        time=t,
                        source_tick=t * 30 + 30,
                        x=t,
                        y=pid,
                        source_ref=f"players[{pid}].position_log[{t}]",
                    )
                    for t in range(4)
                ],
            )
        )
        for t in range(4):
            payload = dict(
                tick=t * 30 + 30,
                player_id=pid,
                entity_index=pid + 10,
                entity_serial=1,
                life_state=0 if t == 0 else 2,
            )
            channels["coach_state_snapshots"].append(
                dict(
                    payload=payload,
                    time=t,
                    source_tick=payload["tick"],
                    source_ref=f"coach_state_snapshots[{pid * 4 + t}]",
                )
            )
        for t, state in [(0, "visible"), (1, "hidden"), (2, "unknown")]:
            payload = dict(
                tick=t * 30 + 30,
                player_id=pid,
                entity_index=pid + 10,
                entity_serial=1,
                radiant_state=state,
                dire_state=state,
            )
            for name in ("hero_visibility_events", "entity_visibility_events"):
                channels[name].append(
                    dict(
                        payload=payload.copy(),
                        time=t,
                        source_tick=payload["tick"],
                        source_ref=f"{name}[{len(channels[name])}]",
                    )
                )
    return raw, match, {"adapter_issues": [], "issues": []}


def test_consistent_joins_and_all_cutoff_coordinate_mutations():
    raw, match, quality = fixture()
    original = copy.deepcopy(match)
    result = inspect_match(raw, match, quality)
    assert result["hero_entity_visibility"] == {"consistent": 30}
    assert len(result["life_transitions"]) == 10
    assert all(p["counts"]["position_source_mismatches"] == 0 for p in result["players"])
    audit = check_observer_leakage(match)
    assert audit["passed"] and audit["comparisons"] == 80
    assert all(r["mutated_rows"] > 0 for r in audit["checks"])
    assert match == original


def test_positive_control_visible_mutation_changes_observer():
    _, match, _ = fixture()
    changed, count = mutate_positions(
        match, lambda p, r: p["player_slot"] == 128 and r["time"] == 0
    )
    assert count == 1
    assert ObserverIndex(match).sample(0, 1) != ObserverIndex(changed).sample(0, 1)


def test_bad_identity_clock_and_position_are_reported():
    raw, match, quality = fixture()
    match["players"][0]["position_log"][0]["x"] = 123
    match["players"][0]["position_log"][0]["time"] = 1
    match["context"]["channels"]["coach_state_snapshots"][0]["payload"]["entity_serial"] = 2
    result = inspect_match(raw, match, quality)
    counts = result["players"][0]["counts"]
    assert counts["position_source_mismatches"] == 1
    assert counts["clock_mismatches"] == 1
    assert counts["state_visibility_identity_mismatches"] == 1


def test_tick_identity_reuse_and_unknown_are_not_reinterpreted():
    rows = [dict(tick=5, entity_serial=1), dict(tick=5, entity_serial=2)]
    index = TickIndex(rows)
    assert index.at(4) is None
    assert index.at(5)["entity_serial"] == 2
    _, match, _ = fixture()
    enemy = ObserverIndex(match).sample(0, 3)["enemies"][0]
    assert enemy["visibility"] == "unknown" and enemy["hidden_for_seconds"] is None


def test_warning_classification_uses_actual_clock_and_handles_pause():
    raw, _, quality = fixture()
    raw["game_clock"]["pauses"] = [dict(start_tick=60, end_tick=90)]
    clock = make_clock(raw)
    assert clock.game_seconds_at(60) == clock.game_seconds_at(89) == 1
    raw["players"][0]["times"] = [0, 31, 180]
    quality["adapter_issues"] = [f"players[0].times[{i}]: invalid clock" for i in range(3)]
    result = warning_audit(raw, quality, clock)
    assert result["counts"] == {"pre_game": 1, "in_match_unexplained": 1, "post_duration": 1}


def test_death_corroboration_does_not_force_ambiguous_match():
    raw, match, quality = fixture()
    raw["combat_log"] = [
        dict(
            tick=59,
            log_type="DEATH",
            target_name="hero_0",
            target_is_hero=True,
            target_is_illusion=False,
        )
    ] * 2
    result = corroborate_deaths(raw, inspect_match(raw, match, quality)["life_transitions"])
    assert result["ambiguous"] == 1 and result["unmatched"] == 9
    assert result["matched_once"] == 0


def test_consumed_hash_mismatch_fails_before_output(tmp_path):
    preparation = tmp_path / "prep"
    preparation.mkdir()
    (preparation / "manifest.json").write_text(json.dumps({"files": {"raw.json": "bad"}}))
    (preparation / "raw.json").write_text("{}")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="hash mismatch"):
        run_audit(preparation, tmp_path, output)
    assert not output.exists()


def test_never_overwrites_old_output(tmp_path):
    with pytest.raises(ValueError, match="already exists"):
        run_audit(tmp_path, tmp_path, tmp_path)


def test_missing_channel_rejected_and_large_jump_not_labeled_teleport():
    raw, match, quality = fixture()
    match["players"][0]["position_log"][2]["x"] = 5000
    result = inspect_match(raw, match, quality)
    assert len(result["jumps"]) == 2
    assert result["jumps"][0]["interpretation"] == "unclassified_jump_not_automatically_teleport"
    match["context"]["channels"]["hero_visibility_events"] = None
    with pytest.raises(ValueError, match="channel unavailable"):
        inspect_match(raw, match, quality)
