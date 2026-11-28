"""Guard population isolation, action/outcome separation and honest support counts."""

import gzip
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def census(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("inventory_b5_routes")


def test_route_keeps_failure_after_commitment(census):
    path = [(500, 0), (700, 0), (900, 0), (1100, 0), None, None, None]
    camps = [dict(id=3, x=1850, y=0)]
    assert census.movement(path, (0, 0), camps)[0] == census.JUNGLE
    assert census.movement(path, (0, 0), [])[0] == census.UNKNOWN
    assert census.movement([(500, 0), None] + path[2:], (0, 0), camps)[0] == census.UNKNOWN
    assert census.movement([(500, 0), (1300, 0)] + path[2:], (0, 0), camps)[0] == census.UNKNOWN
    assert census.movement([(500, 0)] * 7, (0, 0), camps)[0] == census.LANE


def test_reserved_duplicate_and_wrong_folds_rejected(census, tmp_path):
    def row(mid):
        fold = (
            int.from_bytes(census.hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big")
            % 5
        )
        return dict(match=mid, hero="hero", t=100, fold=fold)

    reserved = next(n for n in range(1000) if census.is_holdout(n))
    development = next(n for n in range(1000) if not census.is_holdout(n))
    file = tmp_path / "rows.jsonl"
    for rows in ([row(reserved)], [row(development)] * 2, [dict(row(development), fold=-1)]):
        raw = b"\n".join(json.dumps(r).encode() for r in rows)
        file.write_bytes(raw)
        with pytest.raises(ValueError, match="duplicate, holdout, or invalid"):
            census.load_opportunities(file, census.digest(raw))
    with pytest.raises(ValueError, match="hash"):
        census.load_opportunities(file)


def test_only_own_decision_fields_are_projected(census):
    row = dict(match=123, hero="hero", t=100, fold=1, action="unknown")
    frames = {
        s: dict(
            heroes=[
                dict(
                    hero="hero",
                    team=2,
                    pos=[500, 0],
                    life_state=0,
                    hp=100,
                    max_hp=200,
                    move_speed=300,
                )
            ],
            world=dict(lane_fronts={"radiant_bot": dict(count=3, front=[0, 0])}),
        )
        for s in range(100, 107)
    }
    before = census.label_case(row, frames, 120, [])
    frames[100]["heroes"].append(dict(hero="enemy", team=3, pos=[0, 0], gold=9999))
    frames[130] = dict(gold=99999)
    row["gold"] = 999999
    assert census.label_case(row, frames, 120, []) == before
    assert before["action"] == census.LANE
    assert before["state_reaches_20s"] and not before["state_reaches_30s"]
    summary = census.summarize([before, dict(before, t=101)])
    assert summary["actions"][census.LANE] == dict(rows=2, matches=1)
    assert summary["cells_with_both"] == 0
    assert census.label_case(row, {}, None, [dict(x=0, y=0)])["action"] == census.UNKNOWN


def test_state_identity_and_order(census, tmp_path):
    file = tmp_path / "state.gz"
    header = dict(
        match_id=123,
        schema="gem-state-capture/3",
        coordinates="cell space (cell*128+vec), map centre 16384",
    )

    def save(frames):
        with gzip.open(file, "wt") as stream:
            stream.write(json.dumps(header) + "\n")
            for f in frames:
                stream.write(json.dumps(f) + "\n")

    save([dict(t=100, heroes=[]), dict(t=101, heroes=[])])
    frames, last, sha = census.read_frames(file, 123, {100})
    assert list(frames) == [100] and last == 101 and sha == census.digest(file.read_bytes())
    with pytest.raises(ValueError, match="identity"):
        census.read_frames(file, 124, {100})
    save([dict(t=100), dict(t=100)])
    with pytest.raises(ValueError, match="strictly"):
        census.read_frames(file, 123, {100})


def test_missing_state_keeps_all_opportunities(census, tmp_path):
    rows = [dict(match=123, hero="hero", t=t, fold=1, action="unknown") for t in (100, 200)]
    labelled, source = census.process_match((123, rows, tmp_path, []))
    assert source == dict(match=123, sha256=None, status="missing")
    summary = census.summarize(labelled)
    assert summary["opportunities"] == 2
    assert summary["matches"] == 1
    assert summary["actions"][census.UNKNOWN] == dict(rows=2, matches=1)
    assert summary["state_window_short"] == {"20": 2, "30": 2}
