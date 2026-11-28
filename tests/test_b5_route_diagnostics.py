"""Cause diagnostics must preserve labels and distinguish missing observations from death."""

import gzip
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def audit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("audit_b5_route_labels")


def frames(path):
    return {
        100 + i: dict(
            heroes=[dict(hero="hero", team=2, life_state=0, pos=p, move_speed=300)],
            world=dict(lane_fronts={"radiant_bot": dict(count=2, front=[0, 0])}),
        )
        for i, p in enumerate(path)
    }


def test_interruption_is_not_assumed_to_be_missing_data(audit):
    row = dict(t=100, hero="hero")
    source = frames([[500, 0]] * 7)
    source[102]["heroes"][0]["life_state"] = 1
    assert audit.diagnose(row, source, []) == dict(kind="not_alive", second=2)
    del source[102]
    assert audit.diagnose(row, source, []) == dict(kind="missing_frame", second=2)
    source[102] = dict(heroes=[])
    assert audit.diagnose(row, source, []) == dict(kind="missing_hero", second=2)


def test_jump_is_observed_displacement_not_inferred_teleport(audit):
    source = frames([[500, 0], [5000, 0]] + [[5000, 0]] * 5)
    result = audit.diagnose(dict(t=100, hero="hero"), source, [])
    assert result == dict(kind="jump", second=1, distance=4500, prior_speed=300, current_speed=300)
    source[101]["heroes"].append(dict(hero="enemy", pos=[1, 2], team=3))
    source[130] = dict(gold=999)
    assert audit.diagnose(dict(t=100, hero="hero"), source, []) == result


def test_geometric_failure_is_not_a_new_label(audit):
    path = [[810, 0]] * 7
    result = audit.geometry(path, [0, 0], [dict(id=1, x=1800, y=0)])
    assert result["lane_failed"] == ["fewer_than_four_near_positions", "endpoint_outside_800"]
    assert result["jungle_min_failed"] == 4
    assert audit.geometry([[800, 0]] * 7, [0, 0], [])["lane_failed"] == []


@pytest.mark.parametrize("compact", [False, True])
def test_pinned_reader_accepts_both_json_layouts(audit, tmp_path, compact):
    p = tmp_path / "state.gz"
    rows = [
        dict(match_id=123, schema="gem-state-capture/3"),
        dict(t=100, heroes=[]),
        dict(t=101, heroes=[]),
    ]
    with gzip.open(p, "wt") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":") if compact else None) + "\n")
    sha = audit.digest(p.read_bytes())
    selected, last = audit.frames_at(p, sha, 123, {100})
    assert selected == {100: rows[1]} and last == 101
    with pytest.raises(ValueError, match="hash mismatch"):
        audit.frames_at(p, "wrong", 123, {100})
    with pytest.raises(ValueError, match="identity"):
        audit.frames_at(p, sha, 124, {100})


def test_replay_checks_known_labels_too(audit, tmp_path):
    row = dict(match=123, hero="hero", t=100, fold=0, action="unknown")
    source = frames([[500, 0]] * 7)
    p = tmp_path / "123.jsonl.gz"
    with gzip.open(p, "wt") as f:
        f.write(json.dumps(dict(match_id=123, schema="gem-state-capture/3")) + "\n")
        for t, r in source.items():
            f.write(json.dumps(dict(t=t, **r)) + "\n")
    pin = dict(status="read", sha256=audit.digest(p.read_bytes()))
    expected = audit.label_case(row, source, 106, [])
    job = (123, [row], {(123, "hero", 100): expected}, pin, tmp_path, [])
    assert audit.audit_match(job) == (1, [])
    expected["action"] = "move_to_jungle"
    with pytest.raises(ValueError, match="differs"):
        audit.audit_match(job)
