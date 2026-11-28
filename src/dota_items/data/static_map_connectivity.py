"""Strict connectivity in the frozen 7.41 static, four-neighbour map grid.

This graph omits trees, dynamic blockers, unit hulls and movement abilities. A graph
connection is not a claim that a hero can traverse a real route. No route time or
path length is estimated. Replay coordinates use the existing nearest-centre grid
convention (Python round, ties to even), with explicit half-open outer bounds and
without the neighbouring-cell substitution used by map_api's region lookup.
"""

from collections import Counter, deque
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import dist, isfinite
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes

MAP_741_COMMIT = "f793787ecf402f52c9e698da260b02f041256898"
MAP_741_GRIDNAV_SHA256 = "377e99db4bc12de98a09ca9cc47167bffb5d129457103a991cd21c84e29e62d6"
MAP_741_ELEVATION_SHA256 = "01b7898deba8a5ff2d853a721765372d847d9cfdd24604aed38be564816182fc"


@dataclass(frozen=True)
class GridGeometry:
    """Square grid of world-coordinate centres; replay = world + replay_offset."""

    size: int = 327
    cell_size: int = 64
    world_min: int = -10464
    replay_offset: int = 16384

    def __post_init__(self):
        for value in (self.size, self.cell_size, self.world_min, self.replay_offset):
            if type(value) is not int:
                raise ValueError("grid geometry values must be integers")
        if self.size <= 0 or self.cell_size <= 0:
            raise ValueError("grid size and cell size must be positive")


MAP_741_GEOMETRY = GridGeometry()


def _position(position):
    if position is None:
        return None
    if not isinstance(position, (tuple, list)) or len(position) != 2:
        raise ValueError("position must be a two-number replay coordinate or None")
    if any(value is None for value in position):
        # Partial positions are missing, but malformed nonmissing values still fail.
        values = [value for value in position if value is not None]
    else:
        values = position
    for value in values:
        try:
            valid = type(value) in (int, float) and isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("position coordinates must be finite numbers or None")
    return None if len(values) != 2 else tuple(position)


class StaticMapConnectivity:
    """Pure graph calculation; direct construction has unverified input provenance.

    ``elevation[x][y] == -128`` is outside the map. ``blocked`` contains exact grid
    indices, including any outside-map cells marked in the original source. Use
    load_static_map for production: it verifies the two frozen source byte hashes.
    """

    def __init__(self, elevation, blocked, *, geometry=MAP_741_GEOMETRY):
        if not isinstance(geometry, GridGeometry):
            raise ValueError("geometry must be GridGeometry")
        if not isinstance(elevation, Sequence) or len(elevation) != geometry.size:
            raise ValueError("elevation must cover the entire square grid")
        levels = []
        for row in elevation:
            if not isinstance(row, Sequence) or len(row) != geometry.size:
                raise ValueError("elevation must cover the entire square grid")
            if any(type(value) is not int or (value < 0 and value != -128) for value in row):
                raise ValueError("elevation cells must be nonnegative integers or -128")
            levels.append(tuple(row))
        blocked_cells = set()
        for cell in blocked:
            if (
                not isinstance(cell, (tuple, list))
                or len(cell) != 2
                or any(type(index) is not int or not 0 <= index < geometry.size for index in cell)
            ):
                raise ValueError("blocked cells must be integer indices within the grid")
            cell = tuple(cell)
            if cell in blocked_cells:
                raise ValueError("duplicate blocked cell")
            blocked_cells.add(cell)
        self.geometry = geometry
        self._elevation = tuple(levels)
        self._blocked = frozenset(blocked_cells)
        self._source = {"kind": "in_memory_unverified", "byte_hashes_verified": False}
        self._components = self._build_components()

    def _build_components(self):
        geometry = self.geometry
        open_cells = {
            (x, y)
            for x in range(geometry.size)
            for y in range(geometry.size)
            if self._elevation[x][y] != -128 and (x, y) not in self._blocked
        }
        components = {}
        component = 0
        # Stable IDs follow the first lexicographic cell in each component.
        for start in sorted(open_cells):
            if start in components:
                continue
            components[start] = component
            queue = deque([start])
            while queue:
                x, y = queue.popleft()
                for cell in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if cell in open_cells and cell not in components:
                        components[cell] = component
                        queue.append(cell)
            component += 1
        return components

    @property
    def source_info(self):
        """Fresh JSON-compatible provenance and precise graph conventions."""
        geometry = self.geometry
        return {
            **self._source,
            "grid_size": geometry.size,
            "cell_size": geometry.cell_size,
            "world_min_cell_center": geometry.world_min,
            "replay_offset": geometry.replay_offset,
            "coordinate_space": "replay_cell_space",
            "array_axis_order": "x_then_y",
            "cell_assignment": "nearest_center_python_round_ties_to_even",
            "outer_bounds": "half_open_half_cell_beyond_first_and_last_centers",
            "neighbours": "four_edge_adjacent",
            "endpoint_snapping": False,
            "trees_included": False,
            "dynamic_blockers_included": False,
            "unit_hulls_included": False,
            "movement_abilities_included": False,
        }

    @property
    def summary(self):
        counts = Counter(self._components.values())
        return {
            "grid_cells": self.geometry.size**2,
            "on_map_cells": sum(value != -128 for row in self._elevation for value in row),
            "blocked_cells": len(self._blocked),
            "open_cells": len(self._components),
            "component_count": len(counts),
            "component_sizes": sorted(counts.values(), reverse=True),
        }

    def point_facts(self, position):
        """Describe a position without shifting it to another grid cell."""
        position = _position(position)
        result = {
            "status": "missing_position",
            "cell": None,
            "elevation": None,
            "component_id": None,
        }
        if position is None:
            return result
        geometry = self.geometry
        lower = geometry.world_min - geometry.cell_size / 2 + geometry.replay_offset
        upper = lower + geometry.cell_size * geometry.size
        if any(not lower <= value < upper for value in position):
            return {**result, "status": "outside_grid"}
        cell = tuple(
            round((value - geometry.replay_offset - geometry.world_min) / geometry.cell_size)
            for value in position
        )
        # Keep floating-point edge cases outside the grid; never clamp or snap.
        if any(not 0 <= index < geometry.size for index in cell):
            return {**result, "status": "outside_grid"}
        x, y = cell
        level = self._elevation[x][y]
        status = "outside_map" if level == -128 else "blocked" if cell in self._blocked else "open"
        return {
            "status": status,
            "cell": list(cell),
            "elevation": level,
            "component_id": self._components.get(cell),
        }

    def connection(self, start, end):
        """Return graph evidence, never real reachability or a travel-time estimate.

        Distance is between the supplied points, not distance to a camp boundary or
        attack range. It is absent if either point is missing or outside the grid.
        """
        start_position, end_position = _position(start), _position(end)
        start_facts, end_facts = self.point_facts(start_position), self.point_facts(end_position)
        connected = None
        if start_facts["status"] == end_facts["status"] == "open":
            connected = start_facts["component_id"] == end_facts["component_id"]
        distance = None
        excluded = {"missing_position", "outside_grid"}
        if start_facts["status"] not in excluded and end_facts["status"] not in excluded:
            distance = dist(start_position, end_position)
        return {
            "start": start_facts,
            "end": end_facts,
            "static_grid_connected": connected,
            "straight_line_distance": distance,
            "real_route_traversable": None,
            "eta_seconds": None,
        }


def load_static_map(gridnav_path, elevation_path, *, patch_family="7.41"):
    """Load exact upstream 7.41 assets, with local 7.41f alignment evidence only.

    The upstream declaration is 7.41, not an official certification of every letter
    patch. Never pass a 7.42 match through this loader as a 7.41 map application.
    """
    if patch_family != "7.41":
        raise ValueError("only the frozen 7.41 static map source is supported")
    payloads = []
    for path, expected in (
        (gridnav_path, MAP_741_GRIDNAV_SHA256),
        (elevation_path, MAP_741_ELEVATION_SHA256),
    ):
        contents = read_source_bytes(Path(path))
        if sha256(contents).hexdigest() != expected:
            raise ValueError("static map source SHA-256 mismatch")
        document = parse_source_json(contents)
        if not isinstance(document, dict) or set(document) != {"data"}:
            raise ValueError("invalid static map source schema")
        payloads.append(document["data"])
    gridnav, elevation = payloads
    geometry = GridGeometry()
    if not isinstance(gridnav, list):
        raise ValueError("gridnav data must be a list")
    blocked = []
    for point in gridnav:
        if not isinstance(point, dict) or set(point) != {"x", "y"}:
            raise ValueError("gridnav points must contain world x and y")
        position = _position((point["x"], point["y"]))
        if position is None:
            raise ValueError("gridnav point is missing")
        indices = tuple((value - geometry.world_min) / geometry.cell_size for value in position)
        if any(not value.is_integer() for value in indices):
            raise ValueError("gridnav point is not an exact grid centre")
        blocked.append(tuple(int(value) for value in indices))
    result = StaticMapConnectivity(elevation, blocked, geometry=geometry)
    result._source = {
        "kind": "frozen_upstream_map",
        "byte_hashes_verified": True,
        "repository": "leamare/dota-map-coordinates",
        "commit": MAP_741_COMMIT,
        "upstream_patch_family": "7.41",
        "local_alignment_evidence_patch": "7.41f",
        "gridnav_sha256": MAP_741_GRIDNAV_SHA256,
        "elevation_sha256": MAP_741_ELEVATION_SHA256,
    }
    return result
