import gzip
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def data(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("lane_study_data")


def test_hide_future_or_unseen_enemy(data):
    for last in (90, 101):
        frame = {"t": 100, "enemies": [{"last_seen": last, "distance": 700}]}
        with pytest.raises(ValueError, match="sight timestamp"):
            data.frame_values(frame)


def test_censored_cases_keep_history_and_action_boundaries(data):
    t = 950
    frame = {
        "t": t,
        "enemies": [],
        "markers": [{"side": "self", "pos": [0, 0]}],
        "ally": None,
        "wave": [3, 4],
    }
    e = dict(
        t=t,
        match=123,
        hero="h",
        history=[frame],
        ready_names=[],
        hp=[1, 2],
        mana=None,
        recent_hero_damage=False,
        front_distance=5,
        nearby_creeps=3,
    )
    y = dict(lane_last_hits=3, action_window_hits=2, death_seconds=[t + 6])
    row = data.sample(e, {"action": "farm"}, y, t + 20)
    assert row["early_death"] and row["behavior_eligible"] and not row["outcome_eligible"]
    assert row["death"] is None and row["sequence"][0] == [None] * len(data.SEQUENCE)
    assert row["sequence"][-1][-1] == 5
    y["death_seconds"] = [t + 7]
    row = data.sample(e, {"action": "retreat"}, y, t + 20)
    assert row["death"] == row["hits"] == 1
    row = data.sample(e, {"action": "farm"}, y, t + 5)
    assert row["action"] == "unknown" and not row["behavior_eligible"]
    e["history"] = [{**frame, "t": t + 1}, frame]
    with pytest.raises(ValueError, match="history"):
        data.sample(e, {"action": "farm"}, y, t + 20)


def test_capture_checks_clock_and_count(tmp_path, data):
    folder = tmp_path / "state-v3"
    folder.mkdir()
    for times, reason in [([1, 0], "non-increasing"), ([1], "incomplete")]:
        with gzip.open(folder / "123.jsonl.gz", "wt") as f:
            for row in [
                {"match_id": 123, "schema": "test", "seconds": 2},
                *({"t": t} for t in times),
            ]:
                print(json.dumps(row), file=f)
        with pytest.raises(ValueError, match=reason):
            list(data.capture(tmp_path, "state-v3", 123, "test"))
