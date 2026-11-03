"""Shared M1 snapshot reader (moved from scripts/train_item_timing.py)."""

import json

import pytest

from dota_items.data import match_snapshot as ms
from dota_items.storage import file_hash

PLAYERS = "match_id,hero_id,collapsed_carry,note\n1,8,false,\n2,9,true,x\n"
PURCHASES = "match_id,item,time_s\n1,123,4.5\n"
SPLIT = {"schema": "m1-time-split/1", "train": [1], "validation": [2]}


def snapshot(
    tmp_path, players=PLAYERS, purchases=PURCHASES, split=SPLIT, schema="m1-match-table/1"
):
    (tmp_path / "players.csv").write_text(players)
    (tmp_path / "purchases.csv").write_text(purchases)
    (tmp_path / "split.json").write_text(json.dumps(split))
    outputs = {n: file_hash(tmp_path / n) for n in ("players.csv", "purchases.csv", "split.json")}
    manifest = {"schema": schema, "outputs": outputs}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def test_load_snapshot_parses_values_and_keeps_item_as_text(tmp_path):
    _, players, purchases, split = ms.load_snapshot(snapshot(tmp_path))
    assert players[0] == {"match_id": 1, "hero_id": 8, "collapsed_carry": False, "note": None}
    assert purchases == [{"match_id": 1, "item": "123", "time_s": 4.5}]
    assert split["train"] == [1]


def test_load_snapshot_rejects_changed_files(tmp_path):
    path = snapshot(tmp_path)
    (path / "players.csv").write_text("match_id\n2\n")
    with pytest.raises(ValueError, match="players.csv"):
        ms.load_snapshot(path)


def test_load_snapshot_requires_every_key_file_in_manifest(tmp_path):
    path = snapshot(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text())
    del manifest["outputs"]["split.json"]
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="split.json"):
        ms.load_snapshot(path)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"schema": "other/1"}, "snapshot schema"),
        ({"split": {**SPLIT, "schema": "other/1"}}, "split schema"),
        ({"split": {**SPLIT, "train": [1, 2], "validation": [2]}}, "shares matches"),
        ({"split": {**SPLIT, "train": [1, 1]}}, "repeats"),
        ({"split": {**SPLIT, "validation": []}}, "needs train and validation"),
        ({"split": {**SPLIT, "validation": [3]}}, "players do not match"),
        ({"purchases": "match_id,item,time_s\n9,123,4.5\n"}, "outside the split"),
    ],
)
def test_load_snapshot_rejects_unsafe_tables_despite_correct_hashes(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        ms.load_snapshot(snapshot(tmp_path, **kwargs))


def test_write_new_json_never_overwrites(tmp_path):
    ms.write_new_json(tmp_path / "a.json", {"x": "中"})
    assert json.loads((tmp_path / "a.json").read_text()) == {"x": "中"}
    with pytest.raises(FileExistsError):
        ms.write_new_json(tmp_path / "a.json", {})
