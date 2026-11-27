"""Verify explicit Workshop map snapshots without granting replay compatibility.

The native capture manifest identifies a patch *series* and a client build. It does
not certify a letter patch, a later replay build, camp types, dynamic spawns, vision,
or a model. All reads use the public bounded source reader; frozen maps stay intact.
"""

import copy
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path, PurePosixPath

from dota_items.data.source_io import read_source_bytes

FILES = (
    "worlddata.json",
    "elevationdata.json",
    "gridnavdata.json",
    "mapdata.json",
    "lanedata.json",
)
CELL = 64
_BOUNDS = {"worldMinX", "worldMaxX", "worldMinY", "worldMaxY"}
_LANES = {
    f"npc_dota_spawner_{team}_{lane}" for team in ("good", "bad") for lane in ("top", "mid", "bot")
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _digest(value, length=64):
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _finite(value):
    if isinstance(value, float):
        _require(math.isfinite(value), "Non-finite JSON number")
    elif isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def _decode(contents):
    try:
        result = json.loads(contents, object_pairs_hook=_object)
        _finite(result)
        return result
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid map JSON") from exc


def _read(root, name, expected):
    _require(_digest(expected), "Invalid expected file SHA-256")
    path = root / name
    _require(not path.is_symlink() and path.is_file(), f"Missing or symbolic map file: {name}")
    _require(path.resolve().parent == root, "Map file escapes snapshot root")
    contents = read_source_bytes(path)
    _require(not path.is_symlink(), f"Map file changed to a symbolic link: {name}")
    _require(hashlib.sha256(contents).hexdigest() == expected, f"Map SHA-256 mismatch: {name}")
    return contents


def _hashes(value):
    _require(
        isinstance(value, dict) and set(value) == set(FILES), "Expected exactly five map files"
    )
    _require(all(_digest(v) for v in value.values()), "Invalid map output SHA-256")


def _bounds(value):
    _require(isinstance(value, dict) and set(value) == _BOUNDS, "Invalid world bounds")
    _require(all(type(v) is int for v in value.values()), "World bounds must be integers")
    shape = []
    for axis in ("X", "Y"):
        span = value[f"worldMax{axis}"] - value[f"worldMin{axis}"]
        _require(0 < span <= CELL * 4095 and span % CELL == 0, "Invalid 64-unit grid extent")
        shape.append(span // CELL + 1)
    return shape


def _point(x, y, bounds):
    _require(_number(x) and _number(y), "Invalid map coordinate")
    _require(
        bounds["worldMinX"] <= x <= bounds["worldMaxX"]
        and bounds["worldMinY"] <= y <= bounds["worldMaxY"],
        "Map coordinate outside declared bounds",
    )


def _data(doc, kind):
    _require(isinstance(doc, dict) and set(doc) == {"data"}, "Invalid map data wrapper")
    _require(isinstance(doc["data"], kind), "Invalid map data payload")
    return doc["data"]


def _entities(doc, bounds):
    entities = _data(doc, dict)
    for kind, rows in entities.items():
        _require(re.fullmatch("[a-z][a-z0-9_]*", kind) is not None, "Invalid entity class")
        _require(isinstance(rows, list), "Invalid entity list")
        seen = set()
        for row in rows:
            _require(isinstance(row, dict), "Invalid map entity")
            if kind == "trigger_multiple":
                _require(set(row) == {"name", "1", "2", "3", "4"}, "Invalid trigger polygon")
                points = []
                for index in ("1", "2", "3", "4"):
                    p = row[index]
                    _require(isinstance(p, dict) and set(p) == {"x", "y"}, "Invalid trigger point")
                    _point(p["x"], p["y"], bounds)
                    points.append((p["x"], p["y"]))
                _require(len(set(points)) == 4, "Duplicate trigger polygon points")
                area = sum(
                    a[0] * b[1] - b[0] * a[1]
                    for a, b in zip(points, points[1:] + points[:1], strict=True)
                )
                _require(area != 0, "Degenerate trigger polygon")
                key = tuple(points)
            else:
                _require("x" in row and "y" in row, "Missing entity coordinates")
                _point(row["x"], row["y"], bounds)
                key = (row["x"], row["y"])
                _require(
                    "team" in row and _integer(row["team"]) and row["team"] <= 5,
                    "Invalid entity team",
                )
                if "z" in row:
                    _require(_number(row["z"]), "Invalid entity height")
                if "bounds" in row:
                    size = row["bounds"]
                    _require(
                        isinstance(size, list)
                        and len(size) == 2
                        and all(_number(v) and v >= 0 for v in size),
                        "Invalid entity bounds",
                    )
            if "name" in row:
                _require(isinstance(row["name"], str) and bool(row["name"]), "Invalid entity name")
            _require(key not in seen, "Duplicate entity coordinates or polygon")
            seen.add(key)
    return entities


def _lanes(doc, bounds):
    _require(
        isinstance(doc, dict) and doc.get("type") == "FeatureCollection", "Invalid lanes collection"
    )
    features = doc.get("features")
    _require(isinstance(features, list), "Invalid lane features")
    lanes = {}
    for feature in features:
        _require(
            isinstance(feature, dict) and feature.get("type") == "Feature", "Invalid lane feature"
        )
        properties, geometry = feature.get("properties"), feature.get("geometry")
        _require(
            isinstance(properties, dict) and isinstance(geometry, dict), "Missing lane structure"
        )
        name = properties.get("name")
        _require(
            isinstance(name, str) and name in _LANES and name not in lanes,
            "Invalid or duplicate lane name",
        )
        points = geometry.get("coordinates")
        _require(
            geometry.get("type") == "LineString" and isinstance(points, list) and len(points) >= 2,
            "Invalid lane path",
        )
        for point in points:
            _require(isinstance(point, list) and len(point) == 2, "Invalid lane point")
            _point(*point, bounds)
        _require(
            all(a != b for a, b in zip(points, points[1:], strict=False)),
            "Duplicate consecutive lane points",
        )
        lanes[name] = points
    _require(set(lanes) == _LANES, "Expected both teams' three lanes")
    return lanes


def _documents(documents, engine_bounds=None):
    world = documents["worlddata.json"]
    shape = _bounds(world)
    bounds = engine_bounds or world
    _bounds(bounds)
    for axis in ("X", "Y"):
        _require(
            bounds[f"worldMin{axis}"]
            <= world[f"worldMin{axis}"]
            < world[f"worldMax{axis}"]
            <= bounds[f"worldMax{axis}"],
            "Sampling grid exceeds engine bounds",
        )
    elevation = _data(documents["elevationdata.json"], list)
    _require(len(elevation) == shape[0], "Elevation X dimension mismatch")
    for column in elevation:
        _require(
            isinstance(column, list) and len(column) == shape[1], "Elevation Y dimension mismatch"
        )
        _require(
            all(type(v) is int and -128 <= v <= 127 for v in column), "Invalid elevation level"
        )
    blocked = set()
    for point in _data(documents["gridnavdata.json"], list):
        _require(isinstance(point, dict) and set(point) == {"x", "y"}, "Invalid navigation point")
        x, y = point["x"], point["y"]
        _point(x, y, world)
        _require(
            type(x) is int
            and type(y) is int
            and (x - world["worldMinX"]) % CELL == 0
            and (y - world["worldMinY"]) % CELL == 0,
            "Navigation point is off grid",
        )
        _require((x, y) not in blocked, "Duplicate navigation point")
        blocked.add((x, y))
    entities = _entities(documents["mapdata.json"], bounds)
    lanes = _lanes(documents["lanedata.json"], bounds)
    return {
        "grid_shape": shape,
        "sampling_bounds": world,
        "grid_cell_world_units": CELL,
        "total_blocked": len(blocked),
        "entity_counts": {k: len(v) for k, v in entities.items()},
        "lane_count": len(lanes),
    }


def _manifest(doc, patch, client):
    _require(isinstance(doc, dict), "Invalid map manifest")
    _require(
        isinstance(patch, str) and re.fullmatch(r"[0-9]+\.[0-9]+", patch),
        "Expected a patch series, not a letter patch",
    )
    _require(_integer(client, 1), "Invalid expected client version")
    _require(
        doc.get("patch_series") == patch
        and type(doc.get("client_version")) is int
        and doc["client_version"] == client,
        "Map patch series or client version mismatch",
    )
    _require(
        doc.get("map") == "dota" and _integer(doc.get("steam_build_id"), 1),
        "Invalid map or Steam build",
    )
    _hashes(doc.get("output_sha256"))
    _require(
        _digest(doc.get("runtime_extractor_sha256"))
        and _digest(doc.get("upstream_extractor_commit"), 40),
        "Invalid extractor identity",
    )
    value = doc.get("collected_local_date")
    _require(isinstance(value, str), "Missing map capture date")
    try:
        _require(date.fromisoformat(value).isoformat() == value, "Invalid map capture date")
    except ValueError as exc:
        raise ValueError("Invalid map capture date") from exc
    inputs = doc.get("inputs_sha256")
    _require(isinstance(inputs, dict) and bool(inputs), "Missing capture input identities")
    for path, digest in inputs.items():
        p = PurePosixPath(path)
        _require(
            not p.is_absolute()
            and ".." not in p.parts
            and "\\" not in path
            and str(p) == path
            and path != "."
            and _digest(digest),
            "Invalid capture input identity",
        )
    notes = doc.get("capture_notes")
    _require(
        isinstance(notes, list) and bool(notes) and all(isinstance(n, str) and n for n in notes),
        "Missing capture limitations",
    )
    validation = doc.get("validation")
    _require(
        isinstance(validation, dict)
        and type(validation.get("entity_indices_counts_and_bounds_verified")) is bool,
        "Missing capture validation declaration",
    )
    reads = validation.get("two_runtime_reads_identical")
    _require(
        isinstance(reads, list)
        and all(isinstance(s, str) for s in reads)
        and len(set(reads)) == len(reads),
        "Invalid repeated-read declaration",
    )
    _require(
        isinstance(doc.get("grid_shape"), list)
        and len(doc["grid_shape"]) == 2
        and all(_integer(v, 2) for v in doc["grid_shape"]),
        "Invalid declared grid shape",
    )
    _require(
        _integer(doc.get("total_blocked")) and _integer(doc.get("lane_count")),
        "Invalid declared map counts",
    )
    counts = doc.get("entity_counts")
    _require(
        isinstance(counts, dict)
        and all(isinstance(k, str) and _integer(v) for k, v in counts.items()),
        "Invalid declared entity counts",
    )
    _bounds(doc.get("engine_bounds"))
    outside = doc.get("outside_grid_test")
    _require(
        isinstance(outside, dict)
        and set(outside) == {"sampled", "traversable"}
        and all(_integer(v) for v in outside.values())
        and outside["traversable"] <= outside["sampled"],
        "Invalid outside-grid declaration",
    )


class VerifiedMapSnapshot:
    """Pinned map content. Public metadata and reads return independent copies.

    Obtain this object with ``verify_map_snapshot``. Verification establishes file
    integrity and structure, not the truth of the original capture's declarations.
    """

    def __init__(self, root, manifest_sha256, manifest, contents, summary):
        self._root = root
        self._manifest_sha256 = manifest_sha256
        self._manifest = copy.deepcopy(manifest)
        self._contents = dict(contents)
        self._summary = copy.deepcopy(summary)

    @property
    def identity(self):
        return {
            "schema": "verified-map-snapshot/1",
            "root": str(self._root),
            "manifest_sha256": self._manifest_sha256,
            "patch_series": self._manifest["patch_series"],
            "client_version": self._manifest["client_version"],
            "steam_build_id": self._manifest["steam_build_id"],
            "output_sha256": dict(self._manifest["output_sha256"]),
            "verification": "integrity_and_structure_only",
            "exact_patch_verified": False,
            "replay_build_compatibility_verified": False,
        }

    @property
    def summary(self):
        return copy.deepcopy(self._summary)

    def read(self, filename):
        """Return a decoded copy of one of the five pinned source documents."""
        if filename not in FILES:
            raise ValueError("Unknown map snapshot channel")
        return _decode(self._contents[filename])

    def verify_again(self):
        """Recheck disk inputs before publishing any derived report."""
        verify_map_snapshot(
            self._root,
            expected_manifest_sha256=self._manifest_sha256,
            expected_patch_series=self._manifest["patch_series"],
            expected_client_version=self._manifest["client_version"],
        )


def verify_map_snapshot(
    root, *, expected_manifest_sha256, expected_patch_series, expected_client_version
):
    """Verify native Workshop files against a caller-pinned manifest and source build."""
    root = Path(root).resolve(strict=True)
    manifest = _decode(_read(root, "manifest.json", expected_manifest_sha256))
    _manifest(manifest, expected_patch_series, expected_client_version)
    contents = {name: _read(root, name, manifest["output_sha256"][name]) for name in FILES}
    summary = _documents(
        {name: _decode(data) for name, data in contents.items()}, manifest["engine_bounds"]
    )
    for key in ("grid_shape", "total_blocked", "entity_counts", "lane_count"):
        _require(summary[key] == manifest[key], f"Map manifest count mismatch: {key}")
    summary["capture_notes"] = manifest["capture_notes"]
    summary["capture_declarations"] = {
        "validation": manifest["validation"],
        "outside_grid_test": manifest["outside_grid_test"],
        "independently_reproduced": False,
    }
    # Detect replacement during a multi-file read, including edits to the manifest.
    _read(root, "manifest.json", expected_manifest_sha256)
    for name in FILES:
        _read(root, name, manifest["output_sha256"][name])
    return VerifiedMapSnapshot(root, expected_manifest_sha256, manifest, contents, summary)


def compare_map_snapshots(current, older_root, *, expected_file_sha256):
    """Compare against pinned files; do not claim the older map has a verified manifest.

    Counts are exact coordinate-set differences, never inferred identity, ownership,
    camp type, pathing quality, or runtime spawn counts.
    """
    _require(isinstance(current, VerifiedMapSnapshot), "Expected a verified map snapshot")
    _hashes(expected_file_sha256)
    older_root = Path(older_root).resolve(strict=True)
    old = {name: _decode(_read(older_root, name, expected_file_sha256[name])) for name in FILES}
    old_summary = _documents(old)
    new = {name: current.read(name) for name in FILES}
    _require(
        old["worlddata.json"] == new["worlddata.json"],
        "Grid comparisons require identical sampling bounds",
    )
    old_elevation, new_elevation = (d["elevationdata.json"]["data"] for d in (old, new))
    old_blocked, new_blocked = (
        {(p["x"], p["y"]) for p in d["gridnavdata.json"]["data"]} for d in (old, new)
    )
    landmarks = {}
    old_entities, new_entities = (d["mapdata.json"]["data"] for d in (old, new))
    for kind in sorted(old_entities.keys() | new_entities.keys()):
        a, b = old_entities.get(kind, []), new_entities.get(kind, [])
        if kind == "trigger_multiple":
            continue
        axy, bxy = ({(r["x"], r["y"]) for r in rows} for rows in (a, b))
        landmarks[kind] = {
            "old_entries": len(a),
            "new_entries": len(b),
            "only_old_xy": len(axy - bxy),
            "only_new_xy": len(bxy - axy),
        }
    old_lanes, new_lanes = (_lanes(d["lanedata.json"], d["worlddata.json"]) for d in (old, new))
    result = {
        "schema": "map-snapshot-comparison/1",
        "current": current.identity,
        "comparand": {
            "root": str(older_root),
            "files_sha256": dict(expected_file_sha256),
            "verification": "pinned_files_and_structure_only",
            "manifest_verified": False,
        },
        "comparand_summary": old_summary,
        "height_changed_cells": sum(
            a != b
            for x, y in zip(old_elevation, new_elevation, strict=True)
            for a, b in zip(x, y, strict=True)
        ),
        "blocked_to_walkable": len(old_blocked - new_blocked),
        "walkable_to_blocked": len(new_blocked - old_blocked),
        "landmark_xy": landmarks,
        "changed_lane_paths": sorted(
            name for name in old_lanes if old_lanes[name] != new_lanes[name]
        ),
    }
    current.verify_again()
    for name in FILES:
        _read(older_root, name, expected_file_sha256[name])
    return result
