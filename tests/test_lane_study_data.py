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


def test_full_cohort_includes_late_batches_after_support(data):
    ready, missing = [1], list(range(2, 105))
    batches = list(data.cohort_batches(ready, missing, full=True, has_support=lambda: True))
    assert batches == [ready, missing[:100], missing[100:]]
    assert list(data.cohort_batches(ready, missing, full=False, has_support=lambda: True)) == [
        ready
    ]


def test_precomputed_batch_waits_for_publication_and_records_rejections(data, tmp_path):
    folder = tmp_path / "extras-v1"
    receipts = folder / "receipts"
    receipts.mkdir(parents=True)
    for mid, status in [(1, "extracted"), (2, "failed")]:
        (receipts / f"{mid}.json").write_text(
            json.dumps({"match_id": mid, "status": status, "error": "damaged replay"})
        )
    (folder / "1.jsonl.gz").touch()
    assert data.cache_batch(tmp_path, [1, 2], 0) == ([1], {2: "damaged replay"})
    with pytest.raises(FileNotFoundError):
        data.cache_batch(tmp_path, [3], 0)


def test_consume_concurrently_published_expansion(data, tmp_path, monkeypatch):
    folder = tmp_path / "extras-v1"
    receipts = folder / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "7.json").write_text("{")

    def finish_receipt(seconds):
        assert seconds > 0
        (folder / "7.jsonl.gz").touch()
        (receipts / "7.json").write_text(json.dumps({"match_id": 7, "status": "extracted"}))

    monkeypatch.setattr(data.time, "sleep", finish_receipt)
    assert data.cache_batch(tmp_path, [7], 60) == ([7], {})
