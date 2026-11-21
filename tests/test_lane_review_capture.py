import gzip
import json
from pathlib import Path

import pytest


def write_capture(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")


@pytest.fixture
def report_inputs(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import lane_decision_review as report

    mid = 9080976703
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / f"{mid}.json").write_text(json.dumps({"match_id": mid, "patch": 60}))
    point = (16384, 16384)
    seconds = list(range(890, 910)) + [1026]
    track = {t: point for t in seconds}
    events = [
        {"time": t, "payload": {"log_type": "DEATH", "target_name": unit, "attacker_name": "carry"}}
        for unit in ("npc_dota_creep_badguys_melee", "npc_dota_neutral_kobold")
        for t in (901, 906, 1026)
    ]
    combat = [
        {
            "time": t,
            "payload": {
                "log_type": "DAMAGE",
                "value": 1,
                "target_name": "ally",
                "attacker_name": "foe",
            },
        }
        for t in (899, 904, 906)
    ]
    match = {
        "last": 1026,
        "tracks": {
            "carry": {"team": 2, "pos": track},
            "ally": {"team": 2, "pos": track},
            "foe": {"team": 3, "pos": {}},
        },
        "positions": {"carry": 1},
        "combat": combat,
        "seen": {},
        "fronts": {t: {"radiant_mid": {"count": 1, "front": point}} for t in seconds},
    }
    monkeypatch.setattr(report, "match_inputs", lambda *args: dict(match))
    monkeypatch.setattr(report, "terrain_map", lambda: None)
    monkeypatch.setattr(report, "sees", lambda *args: True)
    monkeypatch.setattr(
        report,
        "vision_grid",
        lambda sources, sec: {"creep_sources": sum(kind == "creep" for kind, _ in sources)},
    )
    monkeypatch.setattr(report, "names", lambda: {})
    state = {"hero": "carry", "team": 2, "pos": point, "move_speed": 300, "unit_state_raw": 0}
    write_capture(
        tmp_path / "state-v3" / f"{mid}.jsonl.gz",
        [
            {"schema": "gem-state-capture/3", "match_id": mid},
            *({"t": t, "heroes": [state], "world": {}} for t in seconds),
        ],
    )
    normalized = {
        "match_id": mid,
        "duration": 905,
        "context": {"channels": {"combat_log": events, "wards": []}},
    }
    write_capture(tmp_path / "parsed" / f"{mid}.normalized.json.gz", [normalized])
    extras = [
        {"schema": "gem-extras-capture/1", "match_id": mid},
        {"t": 900, "creeps": [[3, *point]], "watchers": []},
        {"t": 901, "creeps": [], "watchers": []},
    ]
    write_capture(tmp_path / "extras-v1" / f"{mid}.jsonl.gz", extras)
    return report, mid, extras, normalized


@pytest.mark.parametrize("mode,t", [("lane", 901), ("wave", 900), ("jungle", 901)])
def test_report_bounds_capture_and_postgame_evidence(report_inputs, tmp_path, mode, t):
    report, mid, _, _ = report_inputs
    [(case, action, outcome)] = report.build_match(tmp_path, mid, {}, mode)
    assert case["t"] == t and "match_duration" not in case
    assert case["history"][-1]["vision"] == {"creep_sources": 0, "extras_sampled": True}
    # A gap still uses the older front approximation, explicitly marked as such.
    assert case["history"][0]["vision"] == {"creep_sources": 1, "extras_sampled": False}
    assert (outcome["last_state_second"], outcome["match_duration"]) == (1026, 905)
    assert not outcome["complete"] and action["action"] == "unknown"
    assert outcome["jungle_last_hits" if mode == "jungle" else "lane_last_hits"] == (
        1 if t == 900 else 0
    )
    assert outcome["support_followup"]["hit_offsets"] == [904 - t]
    assert outcome["observed_approach"]["observed_seconds"] == 905 - t
    assert outcome["farm_value"]["next_6s"]["observed_seconds"] == 905 - t


def test_report_validates_replay_identity_and_duration(report_inputs, tmp_path):
    report, mid, extras, normalized = report_inputs
    for bad in ({"match_id": mid + 1}, {"schema": "gem-creep-capture/1"}):
        write_capture(tmp_path / "extras-v1" / f"{mid}.jsonl.gz", [extras[0] | bad, *extras[1:]])
        with pytest.raises(ValueError, match="capture schema or match"):
            list(report.build_match(tmp_path, mid, {}))
    write_capture(tmp_path / "extras-v1" / f"{mid}.jsonl.gz", [*extras, extras[-1]])
    with pytest.raises(ValueError, match="invalid creep sample"):
        list(report.build_match(tmp_path, mid, {}))
    for bad in ({"match_id": mid - 1}, {"duration": None}):
        write_capture(tmp_path / "parsed" / f"{mid}.normalized.json.gz", [normalized | bad])
        with pytest.raises(ValueError, match="normalized"):
            list(report.build_match(tmp_path, mid, {}))


def test_wave_sampling_distinguishes_gaps_and_recorded_empty_rows(report_inputs, tmp_path):
    report, mid, extras, _ = report_inputs
    # Only second 900 is eligible before the last hit blocks the rest of the game.
    for records, sampled, missing in (
        ([extras[0]], 0, 1),
        ([extras[0], {"t": 900, "creeps": []}], 1, 0),
    ):
        write_capture(tmp_path / "extras-v1" / f"{mid}.jsonl.gz", records)
        coverage = {}
        assert list(report.build_match(tmp_path, mid, {}, "wave", wave_coverage=coverage)) == []
        assert coverage == {
            "extras_file_present": True,
            "heroes": {"carry": {"sampled_hero_seconds": sampled, "missing_hero_seconds": missing}},
        }
    (tmp_path / "extras-v1" / f"{mid}.jsonl.gz").unlink()
    assert list(report.build_match(tmp_path, mid, {}, "wave", wave_coverage=coverage)) == []
    assert coverage == {
        "extras_file_present": False,
        "heroes": {"carry": {"sampled_hero_seconds": 0, "missing_hero_seconds": 1}},
    }


def test_capture_truncation_wins_over_a_later_match_end(report_inputs, tmp_path):
    report, mid, _, normalized = report_inputs
    write_capture(
        tmp_path / "parsed" / f"{mid}.normalized.json.gz", [normalized | {"duration": 1070}]
    )
    cases = list(report.build_match(tmp_path, mid, {}, "lane"))
    end_case, action, outcome = cases[-1]
    assert end_case["t"] == outcome["last_state_second"] == 1026
    assert action["action"] == "unknown" and not outcome["complete"]
    assert outcome["farm_value"]["next_20s"]["observed_seconds"] == 0
