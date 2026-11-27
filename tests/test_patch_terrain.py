"""Versioned static geometry cannot silently become game pathfinding or actual FOW."""

import math
from copy import deepcopy
from xml.etree import ElementTree

import pytest

from dota_items.data.patch_terrain import StaticTerrain, replay_to_world, run_diagnostics

IGNORE = "ignore_initial_trees"
TREES = "block_initial_tree_cells"


def documents(*, blocked=(), trees=(), size=5):
    return {
        "worlddata.json": {
            "worldMinX": 0,
            "worldMinY": 0,
            "worldMaxX": (size - 1) * 64,
            "worldMaxY": (size - 1) * 64,
        },
        "elevationdata.json": {"data": [[1] * size for _ in range(size)]},
        "gridnavdata.json": {"data": [{"x": x * 64, "y": y * 64} for x, y in blocked]},
        "mapdata.json": {
            "data": {
                "ent_dota_tree": [{"x": x * 64, "y": y * 64} for x, y in trees],
                "npc_dota_tower": [{"x": 64, "y": 128, "name": '<tower & "test">'}],
                "npc_dota_neutral_spawner": [{"x": 128, "y": 64}],
                "npc_dota_unit_twin_gate": [{"x": 0, "y": 256}],
                "trigger_multiple": [{"1": {"x": 0, "y": 0}, "name": "not_a_point"}],
            }
        },
        "lanedata.json": {"features": [{"geometry": {"coordinates": [[0, 0], [256, 256]]}}]},
    }


def terrain(**kwargs):
    return StaticTerrain(documents(**kwargs), exact_patch="7.42", map_manifest_sha256="a" * 64)


def state(t, *, x=0, y=0):
    return {
        "t": t,
        "heroes": [
            {
                "player_id": i,
                "hero": f"npc_dota_hero_test{i}",
                "team": 2 if i < 5 else 3,
                "hp": 100,
                "life_state": 0,
                "pos": [16384 + x, 16384 + y],
                "move_speed": 300,
            }
            for i in range(10)
        ],
    }


def sight(model, source, target, **kwargs):
    return model.line_of_sight(
        source,
        target,
        sight_range=kwargs.pop("sight_range", 500),
        tree_policy=kwargs.pop("tree_policy", IGNORE),
        flying_vision=kwargs.pop("flying_vision", False),
        high_ground_threshold=kwargs.pop("high_ground_threshold", 2),
        **kwargs,
    )


def test_diagonal_route_cannot_cut_a_blocked_corner():
    route = terrain(blocked=[(1, 0)]).route((0, 0), (64, 64), tree_policy=IGNORE)
    assert route["status"] == "found"
    assert route["centre_path_length_world_units"] == 128
    assert route["path_cells"] == [[0, 0], [0, 1], [1, 1]]
    assert route["diagonal_corner_cutting"] is False
    blocked = terrain(blocked=[(1, 0), (0, 1)]).route((0, 0), (64, 64), tree_policy=IGNORE)
    assert blocked["status"] == "blocked"
    assert blocked["reason"] == "no_static_grid_route"


def test_unobstructed_diagonal_uses_euclidean_cell_lengths():
    route = terrain().route((0, 0), (256, 256), tree_policy=IGNORE)
    assert route["centre_path_length_world_units"] == pytest.approx(4 * 64 * math.sqrt(2))
    assert route["path_cells"] == [[i, i] for i in range(5)]


def test_blocked_outside_and_budget_endpoints_are_not_repaired_or_reported_unreachable():
    model = terrain(blocked=[(0, 0)])
    blocked = model.route((1, 1), (64, 64), tree_policy=IGNORE)
    assert blocked["reason"] == "endpoint_cell_blocked"
    assert blocked["blocked_endpoints_relocated"] is False
    assert model.route((-1, 0), (64, 64), tree_policy=IGNORE)["status"] == "unknown"
    budget = terrain().route((0, 0), (256, 256), tree_policy=IGNORE, max_expansions=1)
    assert budget["status"] == "unknown"
    assert budget["reason"] == "search_budget_exhausted"


def test_endpoint_quantization_is_reported_separately_from_route_length():
    route = terrain().route((1, 2), (65, 66), tree_policy=IGNORE)
    assert route["endpoint_mapping"]["start_centre_offset"] == math.sqrt(5)
    assert route["endpoint_mapping"]["goal_centre_offset"] == math.sqrt(5)
    assert route["centre_path_length_world_units"] == 64 * math.sqrt(2)


def test_explicit_tree_policy_changes_only_the_static_hypothesis():
    model = terrain(trees=[(0, 0), (2, 2)])
    assert model.route((0, 0), (256, 256), tree_policy=IGNORE)["status"] == "found"
    assert model.route((0, 0), (256, 256), tree_policy=TREES)["reason"] == "endpoint_cell_blocked"
    assert model.segment((64, 64), (192, 192), tree_policy=IGNORE)["status"] == "clear"
    assert model.segment((64, 64), (192, 192), tree_policy=TREES)["status"] == "blocked"
    with pytest.raises(ValueError, match="explicit"):
        model.route((0, 0), (64, 64), tree_policy="current_trees")


def test_segment_supercover_includes_corner_and_both_sides_of_grid_edge():
    model = terrain(blocked=[(1, 0)])
    assert model.segment((0, 0), (64, 64), tree_policy=IGNORE)["status"] == "blocked"
    assert model.segment((64, 64), (0, 0), tree_policy=IGNORE)["status"] == "blocked"
    assert model.segment((32, 0), (32, 128), tree_policy=IGNORE)["status"] == "blocked"
    assert model.segment((32, 128), (32, 0), tree_policy=IGNORE)["status"] == "blocked"
    assert model.segment((31, 0), (31, 128), tree_policy=IGNORE)["status"] == "clear"


def test_sight_requires_explicit_range_and_distinguishes_navigation_from_visibility():
    model = terrain(blocked=[(1, 0)])
    assert model.segment((0, 0), (128, 0), tree_policy=IGNORE)["status"] == "blocked"
    assert sight(model, (0, 0), (128, 0))["status"] == "clear"  # navigation is not FOW
    assert sight(model, (0, 0), (128, 0), sight_range=100)["status"] == "out_of_range"
    assert sight(model, (-1, 0), (128, 0))["status"] == "unknown"
    with pytest.raises(TypeError):
        model.line_of_sight((0, 0), (64, 64))


def test_sight_height_flying_and_tree_assumptions_are_separate():
    maps = documents(trees=[(1, 0)])
    maps["elevationdata.json"]["data"][2][0] = 2
    model = StaticTerrain(maps, exact_patch="7.42", map_manifest_sha256="a" * 64)
    assert sight(model, (0, 0), (128, 0))["reason"] == "target_higher_ground"
    assert sight(model, (0, 0), (128, 0), flying_vision=True)["status"] == "clear"
    assert sight(model, (128, 0), (0, 0), tree_policy=TREES)["reason"] == "initial_tree_cell"
    assert sight(model, (128, 0), (0, 0))["status"] == "clear"
    assert sight(model, (0, 0), (256, 0))["reason"] == "intermediate_higher_ground"


def test_unknown_height_cannot_be_called_clear():
    maps = documents()
    maps["elevationdata.json"]["data"][1][0] = -128
    model = StaticTerrain(maps, exact_patch="7.42", map_manifest_sha256="a" * 64)
    assert sight(model, (0, 0), (128, 0))["status"] == "unknown"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "1800"])
def test_nonfinite_or_invented_geometry_parameters_rejected(bad):
    with pytest.raises(ValueError):
        sight(terrain(), (0, 0), (64, 64), sight_range=bad)
    with pytest.raises(ValueError):
        terrain().segment((bad, 0), (64, 64), tree_policy=IGNORE)


def test_maps_are_copied_and_all_results_identify_patch_without_granting_compatibility():
    maps = documents()
    original = deepcopy(maps)
    model = StaticTerrain(maps, exact_patch="7.42", map_manifest_sha256="a" * 64)
    first_svg = model.render_svg()
    maps["elevationdata.json"]["data"][0][0] = -128
    assert first_svg == model.render_svg()
    assert model.summary()["exact_patch"] == "7.42"
    assert model.summary()["action_review_allowed"] is False
    assert original != maps


def test_svg_is_valid_deterministic_north_up_topology_with_no_old_image():
    model = terrain()
    svg = model.render_svg()
    document = ElementTree.fromstring(svg)
    assert svg == model.render_svg()
    assert "Game_map_7.41" not in svg and "<image" not in svg
    assert "CANDIDATE" in svg and "World x: 0..256" in svg
    ns = {"svg": "http://www.w3.org/2000/svg"}
    landmark = next(
        e for e in document.findall("svg:circle", ns) if e.find("svg:title", ns) is not None
    )
    assert landmark.get("cx") == "1.5000"
    assert landmark.get("cy") == "2.5000"  # y=128, north goes up
    assert '<tower & "test">' in landmark.find("svg:title", ns).text
    assert "a" * 64 in document.find("svg:metadata", ns).text


def test_state_diagnostics_describe_blocked_chords_without_inferring_wrong_movement():
    rows = [state(0), state(1, x=128), state(2, x=128)]
    result = run_diagnostics(terrain(blocked=[(1, 0)]), iter(rows), duration=2, tree_policy=IGNORE)
    assert result["movement"]["moving_pairs"] == 10
    assert result["movement"]["moving_blocked"] == 10
    assert result["movement"]["stationary_pairs"] == 10
    assert result["visibility"] == {"status": "not_supplied", "observations": 0}
    assert result["training_allowed"] is False
    assert result["evidence_use"] == "retrospective_omniscient_geometry_diagnostic_only"


def test_death_or_missing_positions_do_not_create_a_chord_across_unknown_seconds():
    rows = [state(0), state(1), state(2, x=128)]
    rows[1]["heroes"][0]["pos"] = None
    rows[1]["heroes"][1]["hp"] = 0
    result = run_diagnostics(terrain(), rows, duration=2, tree_policy=IGNORE)
    assert result["movement"]["moving_pairs"] == 8
    assert result["movement"]["living_missing_position_seconds"] == 1
    assert result["movement"]["nonliving_body_seconds"] == 1


@pytest.mark.parametrize(
    "rows,duration",
    [
        ([], 0),
        ([state(1)], 1),
        ([state(0)], 1),
        ([state(0), state(0)], 1),
        ([state(-1), state(0)], 0),
        ([state(0), state(1)], 0),
    ],
)
def test_diagnostics_require_the_complete_ordered_game_window(rows, duration):
    with pytest.raises(ValueError):
        run_diagnostics(terrain(), rows, duration=duration, tree_policy=IGNORE)


def test_visibility_comparison_preserves_disagreement_and_unknown_without_accuracy_claim():
    record = {
        "t": 0,
        "source": [0, 0],
        "target": [128, 0],
        "sight_range": 500,
        "flying_vision": False,
        "high_ground_threshold": 2,
        "recorded_visible": False,
    }
    records = [record, {**record, "recorded_visible": None}]
    result = run_diagnostics(
        terrain(), [state(0)], duration=0, tree_policy=IGNORE, visibility_observations=records
    )
    assert result["visibility"]["counts"] == {
        "static_clear_recorded_False": 1,
        "static_clear_recorded_None": 1,
    }
    assert result["visibility"]["accuracy_claimed"] is False
    with pytest.raises(ValueError, match="outside"):
        run_diagnostics(
            terrain(),
            [state(0)],
            duration=0,
            tree_policy=IGNORE,
            visibility_observations=[{**record, "t": 1}],
        )
    del record["sight_range"]
    with pytest.raises(ValueError, match="explicit"):
        run_diagnostics(
            terrain(), [state(0)], duration=0, tree_policy=IGNORE, visibility_observations=[record]
        )


def test_replay_offset_is_explicit_and_not_applied_twice_to_world_api():
    assert replay_to_world([16384, 16448]) == (0, 64)
    assert terrain().cell((0, 64)) == (0, 1)
    assert terrain().cell((16384, 16448)) is None
