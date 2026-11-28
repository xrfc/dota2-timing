from dota_items.data import vision_samples_review_v2 as v

ORIGIN = v.OFFSET


def flat(level=1):
    return [[level] * v.SIZE for _ in range(v.SIZE)]


def test_day_and_night_change_a_heros_range():
    terrain = v.Terrain(flat(), [])
    hero, far = (ORIGIN, ORIGIN), (ORIGIN + 1500, ORIGIN)
    assert v.is_day(10) and not v.is_day(310) and v.is_day(600)
    assert v.sees(hero, far, "hero", 10, terrain, "radius")
    assert not v.sees(hero, far, "hero", 310, terrain, "radius")  # night: 800
    assert v.sees(hero, far, "observer", 310, terrain, "radius")  # wards see 1600 always


def test_higher_ground_and_trees_hide():
    ground = flat()
    hill = v.cell_of(ORIGIN + 640, ORIGIN)
    ground[hill[0]][hill[1]] = 2
    terrain = v.Terrain(ground, [(0, 320)])  # a tree north of the source
    source = (ORIGIN, ORIGIN)
    on_hill, behind_hill, behind_tree = (
        (ORIGIN + 640, ORIGIN),
        (ORIGIN + 1000, ORIGIN),
        (ORIGIN, ORIGIN + 640),
    )
    assert v.sees(source, on_hill, "hero", 0, terrain, "radius")
    assert not v.sees(source, on_hill, "hero", 0, terrain, "height")
    assert v.sees(on_hill, source, "hero", 0, terrain, "sight")  # looking down is fine
    assert v.sees(source, behind_hill, "hero", 0, terrain, "height")
    assert not v.sees(source, behind_hill, "hero", 0, terrain, "sight")
    assert v.sees(source, behind_tree, "hero", 0, terrain, "height")
    assert not v.sees(source, behind_tree, "hero", 0, terrain, "sight")
    river = flat(0)
    bank = v.cell_of(ORIGIN + 640, ORIGIN)
    river[bank[0]][bank[1]] = 1
    water = v.Terrain(river, [])
    assert not v.sees(source, on_hill, "hero", 0, water, "height", high_from=1)
    assert v.sees(source, on_hill, "hero", 0, water, "height", high_from=2)


def test_team_sources_lists_heroes_wards_towers_and_wave_fronts():
    tracks = {
        "a": {"team": 2, "pos": {5: (1, 2)}},
        "dead": {"team": 2, "pos": {}},
        "e": {"team": 3, "pos": {5: (9, 9)}},
    }
    wards = [
        {"team": 2, "type": "observer", "x": 3, "y": 4, "start": 0, "end": 10},
        {"team": 2, "type": "sentry", "x": 3, "y": 4, "start": 0, "end": 10},
        {"team": 2, "type": "observer", "x": 7, "y": 7, "start": 6, "end": 10},
    ]
    towers = [
        {"team": 2, "x": 5, "y": 6, "name": "npc_dota_goodguys_tower2_mid"},
        {"team": 3, "x": 0, "y": 0, "name": "npc_dota_badguys_tower1_mid"},
    ]
    fronts = {"radiant_mid": {"front": [8, 8]}, "dire_mid": {"front": [1, 1]}, "radiant_top": None}
    assert v.team_sources(2, 5, tracks, wards, towers, fronts) == [
        ("hero", (1, 2)),
        ("observer", (3, 4)),
        ("tower", (5, 6)),
        ("creep", (8, 8)),
    ]
    terrain = v.Terrain(flat(), [])
    assert v.visible((2, 2), [("hero", (1, 2))], 0, terrain, "sight")


def test_every_creep_replaces_the_wave_fronts_when_given():
    tracks = {"a": {"team": 2, "pos": {5: (1, 2)}}}
    fronts = {"radiant_mid": {"front": [8, 8]}}
    creeps = [[2, 10, 10], [2, 11, 11], [3, 50, 50]]
    assert v.team_sources(2, 5, tracks, [], [], fronts, creeps) == [
        ("hero", (1, 2)),
        ("creep", (10, 10)),
        ("creep", (11, 11)),
    ]
    assert v.team_sources(2, 5, tracks, [], [], fronts, [])[1:] == []  # no creeps alive


def test_buildings_see_by_their_own_ranges():
    kinds = [
        v.building_kind({"name": name} if name else {})
        for name in (
            "npc_dota_goodguys_tower1_top",
            "npc_dota_badguys_tower4",
            "npc_dota_goodguys_fort",
            None,
        )
    ]
    assert kinds == ["tower1", "tower", "fort", "fountain"]
    terrain = v.Terrain(flat(), [])
    spot, far = (ORIGIN, ORIGIN), (ORIGIN + 1000, ORIGIN)
    assert not v.sees(spot, far, "tower1", 310, terrain, "radius")  # 800 at night
    assert v.sees(spot, far, "tower", 310, terrain, "radius")  # 1100 at night
    assert v.sees(spot, (ORIGIN + 2500, ORIGIN), "fort", 310, terrain, "radius")


def test_extra_sources_are_held_watchers_summons_and_illusions():
    watchers = [[10, 10, 2], [20, 20, 0], [30, 30, 3]]
    summons = [
        {"illusion": True, "team": 2, "pos": [1, 1]},
        {"illusion": False, "team": 2, "pos": [2, 2]},
        {"illusion": False, "team": 3, "pos": [3, 3]},
        {"illusion": False, "team": 2, "pos": None},
    ]
    assert v.extra_sources(2, watchers, summons) == [
        ("watcher", (10, 10)),
        ("illusion", (1, 1)),
        ("summon", (2, 2)),
    ]
    assert v.RANGE["watcher"] == (800, 450)


def test_tree_disk_intersects_short_ray_between_clear_endpoints():
    import runpy
    from pathlib import Path

    tree_terrain = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/vision_tree_check.py")
    )["TreeTerrain"]
    terrain = tree_terrain(flat(), [(16, 31)], 32)
    assert not terrain.clear((ORIGIN - 15, ORIGIN), (ORIGIN + 46, ORIGIN), 1)
    assert terrain.clear((ORIGIN - 15, ORIGIN - 2), (ORIGIN + 46, ORIGIN - 2), 1)


def test_creep_samples_require_matching_identity_and_preserve_gaps(tmp_path):
    import gzip
    import json

    import pytest

    path = tmp_path / "creeps.gz"
    for schema in ("gem-creep-capture/1", "other"):
        with gzip.open(path, "wt") as stream:
            for row in ({"schema": schema, "match_id": 7}, {"t": 0, "creeps": []}):
                stream.write(json.dumps(row) + "\n")
        with pytest.raises(ValueError):
            v.read_creep_positions(path, 8)
        if schema == "other":
            with pytest.raises(ValueError):
                v.read_creep_positions(path, 7)
        else:
            assert v.read_creep_positions(path, 7) == {0: []}
