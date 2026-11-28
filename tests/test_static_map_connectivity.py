from pathlib import Path

import pytest

from dota_items.data.static_map_connectivity import (
    GridGeometry,
    StaticMapConnectivity,
    load_static_map,
)


def graph(elevation=None, blocked=()):
    return StaticMapConnectivity(
        elevation if elevation is not None else [[0] * 3 for _ in range(3)],
        blocked,
        geometry=GridGeometry(size=3, cell_size=64, world_min=-64, replay_offset=16384),
    )


def point(x, y):
    return (16320 + x * 64, 16320 + y * 64)


def test_connected_around_obstacle_is_not_actual_route_or_eta():
    data = graph(blocked=[(1, 1)])
    result = data.connection(point(0, 1), point(2, 1))
    assert result["static_grid_connected"] is True
    assert result["straight_line_distance"] == 128
    assert result["real_route_traversable"] is None
    assert result["eta_seconds"] is None
    assert data.summary["component_sizes"] == [8]
    assert data.source_info["trees_included"] is False
    assert data.source_info["byte_hashes_verified"] is False


def test_diagonal_touch_does_not_add_graph_edges():
    data = graph(blocked=[(0, 1), (1, 0), (1, 2), (2, 1)])
    assert data.connection(point(0, 0), point(1, 1))["static_grid_connected"] is False
    assert data.connection(point(1, 1), point(2, 2))["static_grid_connected"] is False
    assert data.summary["component_sizes"] == [1] * 5


def test_disjoint_halves_and_stable_component_ids():
    blocked = [(1, y) for y in range(3)]
    one, two = graph(blocked=blocked), graph(blocked=reversed(blocked))
    result = one.connection(point(0, 0), point(2, 0))
    assert result["static_grid_connected"] is False
    assert result["start"]["component_id"] == 0
    assert result["end"]["component_id"] == 1
    assert two.connection(point(0, 0), point(2, 0)) == result


def test_blocked_endpoint_is_not_snapped_to_neighbour():
    data = graph(blocked=[(1, 1)])
    result = data.connection(point(1, 1), point(2, 1))
    assert result["start"] == {
        "status": "blocked",
        "cell": [1, 1],
        "elevation": 0,
        "component_id": None,
    }
    assert result["static_grid_connected"] is None


def test_outside_map_is_distinct_from_blocked_and_missing():
    data = graph(elevation=[[-128, 0, 0], [0, 2, 0], [0, 0, 1]], blocked=[(0, 0), (1, 1)])
    assert data.point_facts(point(0, 0))["status"] == "outside_map"
    assert data.point_facts(point(1, 1))["status"] == "blocked"
    assert data.point_facts(None)["status"] == "missing_position"
    assert data.point_facts((None, 16384))["status"] == "missing_position"
    assert data.point_facts((0, 0))["status"] == "outside_grid"


def test_coordinate_offset_axis_order_and_height_changes():
    data = graph(elevation=[[0, 0, 0], [1, 2, 3], [4, 5, 6]])
    assert data.point_facts(point(1, 2)) == {
        "status": "open",
        "cell": [1, 2],
        "elevation": 3,
        "component_id": 0,
    }
    # Height changes do not themselves add an unregistered blocking rule.
    assert data.connection(point(0, 0), point(2, 2))["static_grid_connected"] is True
    assert data.point_facts((-64, -64))["status"] == "outside_grid"


def test_outer_half_open_bounds_and_existing_ties_to_even_convention():
    data = graph()
    assert data.point_facts((16288, 16320))["cell"] == [0, 0]
    assert data.point_facts((16287.99, 16320))["status"] == "outside_grid"
    assert data.point_facts((16479.99, 16320))["cell"] == [2, 0]
    assert data.point_facts((16480, 16320))["status"] == "outside_grid"
    assert data.point_facts((16352, 16320))["cell"] == [0, 0]
    assert data.point_facts((16416, 16320))["cell"] == [2, 0]


@pytest.mark.parametrize(
    "position",
    [(True, 0), (float("nan"), 0), (float("inf"), 0), ("1", 2), [1], (None, "bad"), (10**400, 0)],
)
def test_malformed_position_does_not_turn_into_unknown(position):
    with pytest.raises(ValueError):
        graph().connection(position, point(0, 0))


def test_missing_and_off_grid_have_no_distance_and_zero_is_observed():
    data = graph()
    assert data.connection(None, point(0, 0))["straight_line_distance"] is None
    assert data.connection((0, 0), point(0, 0))["straight_line_distance"] is None
    same = data.connection(point(0, 0), point(0, 0))
    assert same["straight_line_distance"] == 0
    assert same["static_grid_connected"] is True


@pytest.mark.parametrize(
    "elevation",
    [
        [[0] * 3] * 2,
        [[0], [0], [0]],
        [[0] * 3, [0, None, 0], [0] * 3],
        [[0] * 3, [0, True, 0], [0] * 3],
        [[0] * 3, [0, -1, 0], [0] * 3],
    ],
)
def test_elevation_must_fully_cover_valid_integer_grid(elevation):
    with pytest.raises(ValueError):
        graph(elevation=elevation)


@pytest.mark.parametrize(
    "blocked", [[(3, 0)], [(-1, 0)], [(True, 0)], [(0.5, 0)], [(0, 0), (0, 0)]]
)
def test_blocked_indices_are_exact_unique_and_in_range(blocked):
    with pytest.raises(ValueError):
        graph(blocked=blocked)


def test_input_mutation_and_provenance_copy_do_not_change_graph():
    elevation, blocked = [[0] * 3 for _ in range(3)], [(1, 1)]
    data = graph(elevation, blocked)
    elevation[0][0] = -128
    blocked.clear()
    info = data.source_info
    info["byte_hashes_verified"] = True
    assert data.point_facts(point(0, 0))["status"] == "open"
    assert data.point_facts(point(1, 1))["status"] == "blocked"
    assert data.source_info["byte_hashes_verified"] is False


def test_loader_rejects_other_patch_before_reading(tmp_path):
    with pytest.raises(ValueError, match="7.41"):
        load_static_map(tmp_path / "missing", tmp_path / "missing", patch_family="7.42")


def test_loader_rejects_modified_source_bytes(tmp_path):
    source = tmp_path / "grid.json"
    source.write_text('{"data": []}\n')
    with pytest.raises(ValueError, match="SHA-256"):
        load_static_map(source, source)


def test_frozen_local_source_geometry_when_available():
    directory = (
        Path(__file__).resolve().parents[1] / "data/map-reference-2026-10-26-v1/coordinates/data"
    )
    paths = directory / "gridnavdata.json", directory / "elevationdata.json"
    if not all(path.exists() for path in paths):
        pytest.skip("frozen local map assets are not distributed with the repository")
    data = load_static_map(*paths)
    assert data.source_info["byte_hashes_verified"] is True
    assert data.summary == {
        "grid_cells": 106929,
        "on_map_cells": 94880,
        "blocked_cells": 47323,
        "open_cells": 59606,
        "component_count": 25,
        "component_sizes": [59505, 16, 12, 8] + [4] * 14 + [3] + [1] * 6,
    }
