import hashlib
import json

import pytest

from dota_items.data.map_snapshot import FILES, compare_map_snapshots, verify_map_snapshot


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, doc):
    path.write_text(json.dumps(doc), encoding="utf-8")


def _pin(root):
    path = root / "manifest.json"
    doc = json.loads(path.read_text())
    doc["output_sha256"] = {name: _sha(root / name) for name in FILES}
    _write(path, doc)
    return _sha(path)


def _verify(root):
    return verify_map_snapshot(
        root,
        expected_manifest_sha256=_sha(root / "manifest.json"),
        expected_patch_series="7.42",
        expected_client_version=6989,
    )


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / "map"
    root.mkdir()
    world = {"worldMinX": 0, "worldMaxX": 64, "worldMinY": 0, "worldMaxY": 64}
    _write(root / "worlddata.json", world)
    _write(root / "elevationdata.json", {"data": [[0, 1], [1, 2]]})
    _write(root / "gridnavdata.json", {"data": [{"x": 64, "y": 64}]})
    _write(
        root / "mapdata.json",
        {
            "data": {
                "npc_dota_tower": [{"name": "tower", "team": 2, "x": 32, "y": 32}],
                "npc_dota_roshan_spawner": [{"team": 0, "x": 0, "y": 0}],
                "trigger_multiple": [
                    {
                        "name": "camp_box",
                        "1": {"x": 0, "y": 0},
                        "2": {"x": 0, "y": 64},
                        "3": {"x": 64, "y": 64},
                        "4": {"x": 64, "y": 0},
                    }
                ],
            }
        },
    )
    _write(
        root / "lanedata.json",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"name": f"npc_dota_spawner_{team}_{lane}"},
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [64, 64]]},
                }
                for team in ("good", "bad")
                for lane in ("top", "mid", "bot")
            ],
        },
    )
    _write(
        root / "manifest.json",
        {
            "map": "dota",
            "patch_series": "7.42",
            "client_version": 6989,
            "steam_build_id": 26825343,
            "collected_local_date": "2026-11-23",
            "grid_shape": [2, 2],
            "total_blocked": 1,
            "lane_count": 6,
            "entity_counts": {
                "npc_dota_tower": 1,
                "npc_dota_roshan_spawner": 1,
                "trigger_multiple": 1,
            },
            "engine_bounds": world,
            "runtime_extractor_sha256": "a" * 64,
            "upstream_extractor_commit": "b" * 40,
            "inputs_sha256": {"game/dota/maps/dota.vpk": "c" * 64},
            "capture_notes": ["One custom-game initialization; dynamic spawns are incomplete."],
            "validation": {
                "entity_indices_counts_and_bounds_verified": True,
                "two_runtime_reads_identical": ["world_bounds"],
            },
            "outside_grid_test": {"sampled": 0, "traversable": 0},
        },
    )
    _pin(root)
    return root


def test_verified_content_and_metadata_do_not_grant_compatibility(snapshot):
    current = _verify(snapshot)
    assert current.identity["client_version"] == 6989
    assert current.identity["steam_build_id"] == 26825343
    assert current.identity["patch_series"] == "7.42"
    assert current.identity["exact_patch_verified"] is False
    assert current.identity["replay_build_compatibility_verified"] is False
    assert current.summary["capture_declarations"]["independently_reproduced"] is False
    assert current.summary["entity_counts"]["npc_dota_roshan_spawner"] == 1
    json.dumps(current.identity)
    current.identity["output_sha256"]["mapdata.json"] = "d" * 64
    current.summary["entity_counts"]["npc_dota_roshan_spawner"] = 99
    current.read("mapdata.json")["data"].clear()
    assert current.read("mapdata.json")["data"]["npc_dota_roshan_spawner"]
    assert current.summary["entity_counts"]["npc_dota_roshan_spawner"] == 1
    current.verify_again()
    with pytest.raises(ValueError, match="Unknown"):
        current.read("../manifest.json")


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_patch_series", "7.41"),
        ("expected_patch_series", "7.42a"),
        ("expected_client_version", 6993),
        ("expected_client_version", True),
        ("expected_manifest_sha256", "f" * 64),
    ],
)
def test_caller_must_pin_source_identity(snapshot, field, value):
    kwargs = {
        "expected_manifest_sha256": _sha(snapshot / "manifest.json"),
        "expected_patch_series": "7.42",
        "expected_client_version": 6989,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        verify_map_snapshot(snapshot, **kwargs)


@pytest.mark.parametrize("filename", ["manifest.json", *FILES])
def test_publication_reverification_detects_any_file_drift(snapshot, filename):
    current = _verify(snapshot)
    with (snapshot / filename).open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="SHA-256"):
        current.verify_again()


def test_changed_data_and_rewritten_manifest_cannot_replace_pinned_source(snapshot):
    current = _verify(snapshot)
    _write(snapshot / "elevationdata.json", {"data": [[0, 0], [0, 0]]})
    _pin(snapshot)
    with pytest.raises(ValueError, match="manifest.json"):
        current.verify_again()


@pytest.mark.parametrize("filename", ["manifest.json", *FILES])
def test_symbolic_files_are_rejected_even_with_matching_bytes(snapshot, filename, tmp_path):
    path = snapshot / filename
    original = path.read_bytes()
    external = tmp_path / "external"
    external.write_bytes(original)
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(ValueError, match="symbolic"):
        _verify(snapshot)


@pytest.mark.parametrize("filename", FILES)
def test_missing_channel_is_rejected(snapshot, filename):
    (snapshot / filename).unlink()
    with pytest.raises(ValueError, match="Missing"):
        _verify(snapshot)


@pytest.mark.parametrize(
    "change",
    [
        "traversal",
        "absolute",
        "extra",
        "missing",
        "bad_hash",
        "boolean_build",
        "bad_date",
        "bad_shape",
        "false_count",
        "wrong_map",
        "unsafe_input",
        "invalid_outside",
        "wrong_entity_count",
    ],
)
def test_invalid_manifest_is_rejected_after_hash_is_repinned(snapshot, change):
    path = snapshot / "manifest.json"
    d = json.loads(path.read_text())
    if change in ("traversal", "absolute", "extra"):
        d["output_sha256"][
            ["../escape.json", "/tmp/escape.json", "extra.json"][
                ["traversal", "absolute", "extra"].index(change)
            ]
        ] = "a" * 64
    elif change == "missing":
        del d["output_sha256"]["worlddata.json"]
    elif change == "bad_hash":
        d["output_sha256"]["worlddata.json"] = "A" * 64
    elif change == "boolean_build":
        d["client_version"] = True
    elif change == "bad_date":
        d["collected_local_date"] = "2026-02-30"
    elif change == "bad_shape":
        d["grid_shape"] = [True, 2]
    elif change == "false_count":
        d["total_blocked"] = 0
    elif change == "wrong_map":
        d["map"] = "custom"
    elif change == "unsafe_input":
        d["inputs_sha256"] = {"../game.vpk": "a" * 64}
    elif change == "invalid_outside":
        d["outside_grid_test"]["traversable"] = 1
    elif change == "wrong_entity_count":
        d["entity_counts"]["npc_dota_tower"] = 2
    _write(path, d)
    with pytest.raises(ValueError):
        _verify(snapshot)


@pytest.mark.parametrize(
    "filename,payload",
    [
        ("gridnavdata.json", {"data": [{"x": 64, "y": 64}, {"x": 64, "y": 64}]}),
        ("gridnavdata.json", {"data": [{"x": 32, "y": 64}]}),
        ("gridnavdata.json", {"data": [{"x": True, "y": 64}]}),
        ("gridnavdata.json", {"data": [{"x": 128, "y": 64}]}),
        ("elevationdata.json", {"data": [[0, 1], [1]]}),
        ("elevationdata.json", {"data": [[0, 1], [1, True]]}),
        ("elevationdata.json", {"data": [[0, 1], [1, 1.5]]}),
        ("worlddata.json", {"worldMinX": 0, "worldMaxX": 65, "worldMinY": 0, "worldMaxY": 64}),
    ],
)
def test_invalid_grid_structure_is_rejected_even_when_hash_matches(snapshot, filename, payload):
    _write(snapshot / filename, payload)
    _pin(snapshot)
    with pytest.raises(ValueError):
        _verify(snapshot)


@pytest.mark.parametrize(
    "change",
    ["outside", "infinity", "duplicate", "missing_coordinate", "bad_team", "degenerate_polygon"],
)
def test_invalid_entities_are_rejected(snapshot, change):
    path = snapshot / "mapdata.json"
    d = json.loads(path.read_text())
    tower = d["data"]["npc_dota_tower"][0]
    if change == "outside":
        tower["x"] = 65
    elif change == "infinity":
        tower["x"] = float("inf")
    elif change == "duplicate":
        d["data"]["npc_dota_tower"].append(dict(tower))
    elif change == "missing_coordinate":
        del tower["x"]
    elif change == "bad_team":
        tower["team"] = True
    elif change == "degenerate_polygon":
        d["data"]["trigger_multiple"][0]["2"] = {"x": 0, "y": 0}
    _write(path, d)
    _pin(snapshot)
    with pytest.raises(ValueError):
        _verify(snapshot)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "wrong_name",
        "wrong_geometry",
        "short_path",
        "bad_point",
        "outside",
        "repeat",
    ],
)
def test_invalid_lane_network_is_rejected(snapshot, change):
    path = snapshot / "lanedata.json"
    d = json.loads(path.read_text())
    f = d["features"][0]
    if change == "missing":
        d["features"].pop()
    elif change == "duplicate":
        d["features"].append(f)
    elif change == "wrong_name":
        f["properties"]["name"] = "unknown"
    elif change == "wrong_geometry":
        f["geometry"]["type"] = "Polygon"
    elif change == "short_path":
        f["geometry"]["coordinates"] = [[0, 0]]
    elif change == "bad_point":
        f["geometry"]["coordinates"][0] = [0, 0, 0]
    elif change == "outside":
        f["geometry"]["coordinates"][0] = [-1, 0]
    elif change == "repeat":
        f["geometry"]["coordinates"][0] = [64, 64]
    _write(path, d)
    _pin(snapshot)
    with pytest.raises(ValueError):
        _verify(snapshot)


@pytest.mark.parametrize(
    "contents", ['{"data":[],"data":[]}', '{"data":[[1e999,0],[0,0]]}', '{"data":[[NaN,0],[0,0]]}']
)
def test_ambiguous_or_nonfinite_json_is_rejected(snapshot, contents):
    (snapshot / "elevationdata.json").write_text(contents)
    _pin(snapshot)
    with pytest.raises(ValueError):
        _verify(snapshot)


def test_comparison_pins_older_files_without_certifying_older_manifest(snapshot, tmp_path):
    older = tmp_path / "older"
    older.mkdir()
    for name in FILES:
        (older / name).write_bytes((snapshot / name).read_bytes())
    _write(older / "elevationdata.json", {"data": [[0, 1], [1, 1]]})
    _write(older / "gridnavdata.json", {"data": [{"x": 0, "y": 0}]})
    d = json.loads((older / "mapdata.json").read_text())
    d["data"]["npc_dota_tower"][0]["x"] = 31
    _write(older / "mapdata.json", d)
    hashes = {name: _sha(older / name) for name in FILES}
    result = compare_map_snapshots(_verify(snapshot), older, expected_file_sha256=hashes)
    assert result["height_changed_cells"] == 1
    assert result["blocked_to_walkable"] == result["walkable_to_blocked"] == 1
    assert result["landmark_xy"]["npc_dota_tower"]["only_old_xy"] == 1
    assert result["landmark_xy"]["npc_dota_tower"]["only_new_xy"] == 1
    assert result["changed_lane_paths"] == []
    assert result["comparand"]["manifest_verified"] is False
    with (older / "mapdata.json").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="SHA-256"):
        compare_map_snapshots(_verify(snapshot), older, expected_file_sha256=hashes)


def test_comparison_detects_drift_during_read(snapshot, tmp_path, monkeypatch):
    older = tmp_path / "older"
    older.mkdir()
    for name in FILES:
        (older / name).write_bytes((snapshot / name).read_bytes())
    current = _verify(snapshot)
    original = current.read

    def drift(name):
        if name == "worlddata.json":
            with (older / "mapdata.json").open("a") as stream:
                stream.write(" ")
        return original(name)

    monkeypatch.setattr(current, "read", drift)
    with pytest.raises(ValueError, match="SHA-256"):
        compare_map_snapshots(
            current, older, expected_file_sha256={name: _sha(older / name) for name in FILES}
        )
