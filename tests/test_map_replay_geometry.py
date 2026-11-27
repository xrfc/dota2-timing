"""Geometry diagnostics must preserve missing evidence and coordinate boundaries."""

from copy import deepcopy

import pytest

from dota_items.data.map_replay_geometry import (
    audit_replay_geometry,
    compare_landmark_positions,
)


def documents():
    return {
        "worlddata.json": {"worldMinX": 0, "worldMinY": 0, "worldMaxX": 128, "worldMaxY": 128},
        "elevationdata.json": {"data": [[0] * 3 for _ in range(3)]},
        "gridnavdata.json": {"data": [{"x": 64, "y": 64}]},
        "mapdata.json": {
            "data": {
                "npc_dota_tower": [
                    {"name": "tower1", "x": 10, "y": 12},
                    {"name": "tower2", "x": 100, "y": 100},
                ],
                "npc_dota_lantern": [{"x": 64, "y": 64}],
                "npc_dota_watch_tower": [{"x": 0, "y": 128}],
            }
        },
        "lanedata.json": {"type": "FeatureCollection", "features": []},
    }


def row(t=0):
    return {
        "t": t,
        "heroes": [
            {
                "player_id": i,
                "hero": f"npc_dota_hero_test{i}",
                "team": 2 if i < 5 else 3,
                "pos": [16384, 16384],
                "hp": 100,
                "life_state": 0,
            }
            for i in range(10)
        ],
        "world": {
            "buildings": [[99, "Tower", 2, 100, 100]],
            "summons": [{"illusion": True, "pos": [999999, 999999], "hp": 100}],
        },
    }


def audit(rows, *, duration=0, extras=None, maps=None):
    return audit_replay_geometry(
        documents() if maps is None else maps,
        rows,
        match_id=123,
        patch="7.42",
        replay_build=6993,
        duration=duration,
        extras_rows=extras,
    )


def test_offset_body_filter_and_separate_missing_bounds_and_blocked_denominators():
    state = row()
    state["heroes"][0]["pos"] = [16448, 16448]
    state["heroes"][1]["pos"] = None
    state["heroes"][2]["pos"] = [16383, 16384]
    state["heroes"][3]["life_state"] = 2
    result = audit(iter([state]))
    counts = result["hero_positions"]
    assert counts == {
        "all_body_seconds": 10,
        "nonliving_body_seconds": 1,
        "living_body_seconds": 9,
        "missing_position": 1,
        "outside_sample_bounds": 1,
        "nearest_blocked_cell": 1,
        "nearest_walkable_cell": 6,
        "seconds_without_building_channel": 0,
        "blocked_fraction_of_in_bounds_living_positions": 1 / 7,
    }
    assert result["tower_channel"]["unique_replay_entity_ids"] == 1
    assert result["tower_channel"]["coordinate_coverage"] == "unavailable_in_state_v3_building_rows"
    assert "tower_coordinates" in result["not_covered"]
    assert result["compatibility_granted"] is False
    assert result["training_allowed"] is False
    assert result["extras_landmarks"] is None


def test_half_grid_ties_match_existing_ties_to_even_convention():
    state = row()
    state["heroes"][0]["pos"] = [16416, 16416]  # Index .5 rounds to zero, not blocked 1/1.
    assert audit([state])["hero_positions"]["nearest_blocked_cell"] == 0
    state["heroes"][0]["pos"] = [16417, 16417]
    assert audit([state])["hero_positions"]["nearest_blocked_cell"] == 1


@pytest.mark.parametrize(
    "rows,duration",
    [
        ([], 0),
        ([row(1)], 1),
        ([row(0)], 1),
        ([row(0), row(0)], 1),
        ([row(0), row(2)], 2),
        ([row(-1), row(0)], 0),
        ([row(0), row(1)], 0),
        ([{"schema": "gem-state-capture/3"}], 0),
    ],
)
def test_every_game_second_required_and_headers_or_outside_rows_rejected(rows, duration):
    with pytest.raises(ValueError, match="row|window"):
        audit(rows, duration=duration)


@pytest.mark.parametrize(
    "position", [[float("nan"), 1], [1, float("inf")], [True, 2], [1], "[1,2]", {"x": 1, "y": 2}]
)
def test_malformed_or_nonfinite_position_is_not_silently_counted_missing(position):
    state = row()
    state["heroes"][0]["pos"] = position
    with pytest.raises(ValueError, match="hero pos"):
        audit([state])


@pytest.mark.parametrize(
    "field,value",
    [
        ("hp", -1),
        ("hp", float("nan")),
        ("life_state", -1),
        ("life_state", True),
        ("player_id", True),
        ("team", 4),
    ],
)
def test_invalid_body_values_fail(field, value):
    state = row()
    state["heroes"][0][field] = value
    with pytest.raises(ValueError):
        audit([state])


def test_body_identity_is_unique_and_stable():
    state = row()
    state["heroes"][1]["player_id"] = 0
    with pytest.raises(ValueError, match="duplicate"):
        audit([state])
    state = row(1)
    state["heroes"][1]["hero"] = "npc_dota_hero_changed"
    with pytest.raises(ValueError, match="identity changed"):
        audit([row(0), state], duration=1)


def test_buildings_shape_cannot_be_read_as_xy_and_missing_channel_is_reported():
    state = row()
    state["world"]["buildings"] = [[99, "Tower", 2, [10, 12]]]
    with pytest.raises(ValueError, match="max_hp"):
        audit([state])
    del state["world"]["buildings"]
    assert audit([state])["hero_positions"]["seconds_without_building_channel"] == 1


def test_full_window_extras_compare_positions_not_changing_holder_as_identity():
    extra = {"t": 0, "watchers": [[16448, 16448, 0]], "outposts": [[16384, 16512, 2]]}
    changed = deepcopy(extra)
    changed["t"] = 1
    changed["watchers"][0][2] = 3
    result = audit([row(0), row(1)], duration=1, extras=iter([extra, changed]))
    report = result["extras_landmarks"]
    assert report["observation_seconds"] == {"npc_dota_lantern": 2, "npc_dota_watch_tower": 2}
    assert report["categories"]["npc_dota_lantern"]["observations"] == 1
    assert report["categories"]["npc_dota_lantern"]["exact_map_entries_covered"] == 1
    assert report["categories"]["npc_dota_watch_tower"]["exact_map_entries_covered"] == 1
    assert report["entity_identity_verified"] is False


@pytest.mark.parametrize(
    "extras",
    [
        [],
        [{"t": -1}],
        [{"t": 0}],
        [{"t": 0, "watchers": [[1, 2, 4]], "outposts": []}],
        [{"t": 0, "watchers": [[1, 2]], "outposts": []}],
    ],
)
def test_supplied_extras_must_be_complete_and_structurally_valid(extras):
    with pytest.raises(ValueError):
        audit([row()], extras=extras)


def test_landmark_exact_pairs_are_one_to_one_and_nearest_collisions_are_explicit():
    observations = [
        {"kind": "npc_dota_tower", "x": 10, "y": 12, "entity_index": 50, "entity_serial": 2},
        {"kind": "npc_dota_tower", "x": 10, "y": 12, "entity_index": 51, "entity_serial": 2},
        {"kind": "npc_dota_tower", "x": 100.5, "y": 100},
        {"kind": "unknown_category", "x": 1, "y": 2},
    ]
    result = compare_landmark_positions(documents(), observations)
    towers = result["categories"]["npc_dota_tower"]
    assert towers["exact_one_to_one_pairs"] == [{"observation_index": 0, "map_index": 0}]
    assert towers["map_entries_without_exact_observation"] == 1
    assert towers["nearest_collisions"] == 1
    assert towers["max_nearest_distance_world_units"] == 0.5
    assert towers["details"][2]["nearest_map_name"] == "tower2"
    assert result["categories"]["unknown_category"]["details"][0]["nearest_map_index"] is None


def test_repeated_position_cannot_certify_two_colocated_map_entities():
    maps = documents()
    towers = maps["mapdata.json"]["data"]["npc_dota_tower"]
    towers[1]["x"], towers[1]["y"] = towers[0]["x"], towers[0]["y"]
    observation = {"kind": "npc_dota_tower", "x": 10, "y": 12}
    result = compare_landmark_positions(maps, [observation, observation])
    assert result["categories"]["npc_dota_tower"]["exact_map_entries_covered"] == 1


def test_unknown_observed_team_preserves_spatial_evidence_without_inventing_a_team():
    observation = {"kind": "npc_dota_tower", "x": 10, "y": 12, "team": None}
    result = compare_landmark_positions(documents(), [observation])
    towers = result["categories"]["npc_dota_tower"]
    assert towers["exact_map_entries_covered"] == 1
    assert towers["details"][0]["team"] is None
    with pytest.raises(ValueError, match="team"):
        compare_landmark_positions(documents(), [{**observation, "team": "unknown"}])


def test_empty_observed_channels_are_distinguished_from_absent_extras_input():
    result = audit([row()], extras=[{"t": 0, "watchers": [], "outposts": []}])
    channel = result["extras_landmarks"]["observed_channels"]["npc_dota_lantern"]
    assert channel == {"seconds": 1, "entity_seconds": 0, "unique_positions": 0, "map_entries": 1}
    assert audit([row()])["extras_landmarks"] is None


def test_map_shapes_and_grid_coordinates_are_not_guessed():
    maps = documents()
    maps["gridnavdata.json"]["data"].append({"x": 3, "y": 3})
    with pytest.raises(ValueError, match="grid point"):
        audit([row()], maps=maps)
    maps = documents()
    maps["elevationdata.json"]["data"].pop()
    with pytest.raises(ValueError, match="shape"):
        audit([row()], maps=maps)
    maps = documents()
    del maps["lanedata.json"]
    with pytest.raises(ValueError, match="five"):
        audit([row()], maps=maps)


def test_unconsumed_trigger_polygon_is_not_forced_into_a_point_shape():
    maps = documents()
    maps["mapdata.json"]["data"]["trigger_multiple"] = [
        {
            "1": {"x": 4379, "y": -4313},
            "2": {"x": 4379, "y": -3495},
            "3": {"x": 5122, "y": -3495},
            "4": {"x": 5122, "y": -4313},
            "name": "neutralcamp_good_2",
        }
    ]
    assert audit([row()], maps=maps)["hero_positions"]["living_body_seconds"] == 10
    compared = compare_landmark_positions(maps, [{"kind": "npc_dota_tower", "x": 10, "y": 12}])
    assert compared["categories"]["npc_dota_tower"]["exact_map_entries_covered"] == 1
    with pytest.raises(ValueError, match="non-point landmark"):
        compare_landmark_positions(maps, [{"kind": "trigger_multiple", "x": 0, "y": 0}])


def test_input_documents_and_rows_remain_unchanged():
    maps, state = documents(), row()
    original_maps, original_state = deepcopy(maps), deepcopy(state)
    audit([state], maps=maps)
    assert maps == original_maps
    assert state == original_state
