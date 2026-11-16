import json

from dota_items.data import map_api as m


def write(tmp_path):
    def world(i):
        return i * m.CELL + m.WORLD_MIN

    doc = {
        "regions": [
            {
                "id": "radiant_base",
                "name_zh": "天辉高地",
                "owner": "radiant",
                "kind": "high_ground",
            },
            {"id": "river_mid", "name_zh": "河道中段", "owner": "neutral", "kind": "river"},
        ],
        "cells": [
            [10, 10, "radiant_base", 2],
            [11, 10, "radiant_base", 2],
            [20, 20, "river_mid", 0],
        ],
        "cliffs": [[12, 10]],
        "trees": [[11, 10]],
        "ramps": [[10, 10]],
        "landmarks": [{"kind": "camp", "name_zh": "小野", "x": world(20), "y": world(20)}],
    }
    path = tmp_path / "regions-grid.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return m.MapKnowledge(path), world


def test_region_level_side_and_terrain(tmp_path):
    knowledge, world = write(tmp_path)
    x, y = world(10) + m.OFFSET, world(10) + m.OFFSET
    assert knowledge.region_at(x, y)["id"] == "radiant_base"
    assert knowledge.level_at(x, y) == 2
    assert knowledge.side_at(x, y, 2) == "own" and knowledge.side_at(x, y, 3) == "enemy"
    assert knowledge.on_ramp(x, y) and not knowledge.has_tree(x, y)
    cliff = (world(12) + m.OFFSET, world(10) + m.OFFSET)
    assert knowledge.is_cliff(*cliff)
    assert knowledge.region_at(*cliff)["id"] == "radiant_base"  # nearest walkable cell
    river = (world(20) + m.OFFSET, world(20) + m.OFFSET)
    assert knowledge.side_at(*river, 2) == "neutral"
    assert knowledge.region_at(0, 0) is None
    camp, distance = knowledge.nearest_landmark(*river, kind="camp")
    assert camp["name_zh"] == "小野" and distance == 0
    assert knowledge.nearest_landmark(0, 0, kind="roshan") == (None, None)
