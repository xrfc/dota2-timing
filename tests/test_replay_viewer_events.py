"""Synthetic event provenance, hindsight exclusion and team isolation tests."""

import hashlib
import json

import pytest

from dota_items.data.replay_viewer_events import EventEvidence


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value).encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def evidence(tmp_path, future="future-secret"):
    raw_path = tmp_path / "prep/raw.json"
    raw_hash = put(raw_path, {"match_id": 1})
    audit_path = tmp_path / "audit.json"
    audit_hash = put(
        audit_path,
        {
            "match_id": 1,
            "provenance": {
                "preparation": str(raw_path.parent),
                "consumed_files": {"raw.json": raw_hash},
            },
        },
    )
    jump = {
        "player_slot": 0,
        "previous": {"source_tick": 0},
        "current": {"source_tick": 30},
        "distance_native_units": 2000,
        "category": "core_movement_event",
        "jump_ref": "jumps[0]",
        "events": [
            {
                "tick": 20,
                "scope": "core",
                "log_type": "ITEM",
                "inflictor_name": "item_blink",
                "roles": ["attacker"],
                "source_ref": "combat_log[0]",
                "core_candidate": True,
            },
            {"tick": 31, "scope": "future_context", "inflictor_name": future},
        ],
    }
    root = tmp_path / "events"
    output_hash = put(
        root / "1.json",
        {
            "match_id": 1,
            "schema_version": "replay-jump-events/1",
            "semantic_audit": str(audit_path),
            "event_types": {"ITEM": 2},
            "jumps": [jump],
        },
    )
    put(
        root / "summary.json",
        {
            "matches": [{"match_id": 1}],
            "outputs": {"1.json": output_hash},
            "inputs": {str(audit_path): audit_hash, str(raw_path): raw_hash},
        },
    )
    return EventEvidence([root], tmp_path), {"inputs_and_code": {str(raw_path): raw_hash}}


def frame(view="omniscient", tick=30):
    return {"view": view, "match_id": 1, "tick": tick, "players": [{"player_slot": 0}]}


def test_positive_event_with_role_reference_and_no_future(tmp_path):
    e, m = evidence(tmp_path)
    result = e.attach(frame(), m)
    jump = result["players"][0]["jump_evidence"][0]
    assert jump["causal_verified"] is False
    assert len(jump["events"]) == 1
    assert jump["events"][0]["inflictor_name"] == "item_blink"
    assert jump["events"][0]["roles"] == ["attacker"]
    assert jump["events"][0]["source_ref"] == "combat_log[0]"
    assert not e.attach(frame(tick=0), m)["players"][0]["jump_evidence"]


@pytest.mark.parametrize("team", ["radiant", "dire"])
def test_team_never_loads_evidence_even_if_broken(tmp_path, monkeypatch, team):
    e, m = evidence(tmp_path)

    def fail(*args):
        raise AssertionError("Team request touched evidence")

    monkeypatch.setattr(e, "load", fail)
    original = frame(team)
    assert e.attach(frame(team), m) == original


def test_future_event_perturbation_does_not_change_panel(tmp_path):
    e, m = evidence(tmp_path, "one")
    before = e.attach(frame(), m)
    e, m = evidence(tmp_path, "two")
    assert before == e.attach(frame(), m)


@pytest.mark.parametrize("name", ["events/1.json", "audit.json", "prep/raw.json"])
def test_corruption_fails_closed(tmp_path, name):
    e, m = evidence(tmp_path)
    p = tmp_path / name
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch|changed"):
        e.attach(frame(), m)


def test_timeline_source_mismatch_rejected(tmp_path):
    e, m = evidence(tmp_path)
    m["inputs_and_code"] = {"elsewhere/raw.json": "wrong"}
    with pytest.raises(ValueError, match="source mismatch"):
        e.attach(frame(), m)


def test_missing_evidence_is_not_no_events(tmp_path):
    e = EventEvidence([], tmp_path)
    assert e.attach(frame(), {})["event_evidence_status"] == "not_audited"
