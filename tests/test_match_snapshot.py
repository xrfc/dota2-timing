"""Shared M1 snapshot reader (moved from scripts/train_item_timing.py)."""

import json

import pytest

from dota_items.data import match_snapshot as ms
from dota_items.storage import file_hash


def snapshot(tmp_path):
    (tmp_path / "players.csv").write_text("match_id,hero_id,collapsed_carry,note\n1,8,false,\n")
    (tmp_path / "purchases.csv").write_text("match_id,item,time_s\n1,123,4.5\n")
    (tmp_path / "split.json").write_text('{"train": [1], "validation": []}')
    outputs = {n: file_hash(tmp_path / n) for n in ("players.csv", "purchases.csv", "split.json")}
    (tmp_path / "manifest.json").write_text(json.dumps({"outputs": outputs}))
    return tmp_path


def test_load_snapshot_parses_values_and_keeps_item_as_text(tmp_path):
    _, players, purchases, split = ms.load_snapshot(snapshot(tmp_path))
    assert players == [{"match_id": 1, "hero_id": 8, "collapsed_carry": False, "note": None}]
    assert purchases == [{"match_id": 1, "item": "123", "time_s": 4.5}]
    assert split["train"] == [1]


def test_load_snapshot_rejects_changed_files(tmp_path):
    path = snapshot(tmp_path)
    (path / "players.csv").write_text("match_id\n2\n")
    with pytest.raises(ValueError, match="players.csv"):
        ms.load_snapshot(path)


def test_write_new_json_never_overwrites(tmp_path):
    ms.write_new_json(tmp_path / "a.json", {"x": "中"})
    assert json.loads((tmp_path / "a.json").read_text()) == {"x": "中"}
    with pytest.raises(FileExistsError):
        ms.write_new_json(tmp_path / "a.json", {})
