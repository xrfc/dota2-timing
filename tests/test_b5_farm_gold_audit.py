"""Gold-source audit keeps ambiguous tick associations and missing counters explicit."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_b5_farm_gold.py"
spec = importlib.util.spec_from_file_location("audit_b5_farm_gold", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_window_uses_open_start_and_closed_end_and_credits_shared_gold():
    events = [
        (t, tick, hero, reason, value)
        for t, tick, hero, reason, value in [
            (919, 10, "wr", 13, 31),
            (925, 11, "wr", 13, 37),
            (925, 11, "wr", 13, 44),
            (928, 12, "wr", 13, 36),
            (933, 13, "wr", 14, 9),
            (934, 14, "wr", 14, 42),
            (927, 15, "other", 13, 15),
        ]
    ]
    bounds = {("wr", 919): [100, 30, 90, 31, 82], ("wr", 933): [217, 39, 112, 53, 208]}
    r = audit.window("wr", 913, events, bounds)
    assert (r["logged_creep"], r["counter_creep"]) == (117, 117)
    assert (r["logged_neutral"], r["counter_neutral"]) == (9, 9)
    assert r["income_counter"] == 22 and r["cash_change"] == 148
    assert len(r["gold_events"]) == 4


def test_no_events_and_missing_entity_endpoint_are_distinct():
    r = audit.window("wr", 10, [], {("wr", 30): [5, 10, None, 80, 100]})
    assert r["logged_creep"] == 0
    assert (
        r["counter_creep"]
        is r["counter_neutral"]
        is r["income_counter"]
        is r["cash_change"]
        is None
    )


def test_same_tick_corroboration_preserves_mixed_classes_and_excludes_denies():
    def death(target, illusion=False):
        return {
            "source_tick": 25,
            "payload": {
                "log_type": "DEATH",
                "attacker_name": "h",
                "attacker_is_illusion": illusion,
                "target_name": target,
            },
        }

    rows = [
        death("npc_dota_creep_goodguys_melee"),
        death("npc_dota_goodguys_siege"),
        death("npc_dota_neutral_a"),
        death("npc_dota_creep_badguys_melee"),
        {**death("npc_dota_neutral_b", True), "source_tick": 27},
    ]
    matches, n = audit.read_deaths({"context": {"channels": {"combat_log": rows}}}, {"h": (3, 1)})
    assert dict(matches) == {("h", 25): {"creep", "neutral"}}
    assert n == 0


def test_unregistered_match_and_altered_inputs_fail_before_parsing(tmp_path):
    with pytest.raises(ValueError, match="registered"):
        audit.audit(tmp_path / "1.dem", tmp_path)
    (tmp_path / "replay-provenance.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="fingerprint"):
        audit.audit(tmp_path / "9021358613.dem", tmp_path)


def test_first_frame_after_final_second_includes_boundary_kill():
    rows = {
        ("h", 16): [10] * 5,
        ("h", 17): [10] * 5,
        ("h", 30): [10] * 5,
        ("h", 31): [10, 46, 10, 10, 46],
    }
    result = audit.window("h", 10, [(30, 900, "h", 14, 36)], rows)
    assert result["logged_neutral"] == result["aligned_counter_neutral"] == 36
    assert result["counter_neutral"] == 0
