"""Static entity evidence, replay admission and atomic publication regressions."""

import hashlib
import importlib.util
import json
import sys
from enum import IntFlag
from pathlib import Path
from types import SimpleNamespace

import pytest

from dota_items.sources.map_landmark_capture import LandmarkCollector, capture

ROOT = Path(__file__).resolve().parents[1]


class Op(IntFlag):
    CREATED = 1
    UPDATED = 2
    DELETED = 4

    def has(self, other):
        return bool(self & other)


class Entity:
    def __init__(self, cls="CDOTA_BaseNPC_Tower", *, index=1, serial=1, **fields):
        self.cls, self.index, self.serial = cls, index, serial
        self.fields = {
            "CBodyComponent.m_cellX": 128,
            "CBodyComponent.m_cellY": 127,
            "CBodyComponent.m_vecX": 10.5,
            "CBodyComponent.m_vecY": 20.0,
            "m_iTeamNum": 2,
            "m_pEntity.m_nameStringableIndex": 0,
            **fields,
        }

    def get_class_name(self):
        return self.cls

    def get_index(self):
        return self.index

    def get_serial(self):
        return self.serial

    def get_int32(self, name):
        return self.fields.get(name)

    get_uint32 = get_int32
    get_float32 = get_int32


def _parser(name="npc_dota_goodguys_tower1_mid"):
    return SimpleNamespace(
        tick=10,
        string_tables=SimpleNamespace(
            get_by_name=lambda _: SimpleNamespace(items={0: (name, None)})
        ),
    )


def test_static_coordinates_use_world_space_and_deduplicate_updates():
    parser = _parser()
    collector = LandmarkCollector(parser, Op.DELETED)
    entity = Entity()
    collector.on_entity(entity, Op.CREATED)
    parser.tick = 20
    collector.on_entity(entity, Op.UPDATED)
    row = collector.result()["observations"][0]
    assert (row["x"], row["y"]) == (10.5, -108.0)
    assert (row["first_tick"], row["last_tick"], row["observations"]) == (10, 20, 2)
    assert row["npc_name"] == "npc_dota_goodguys_tower1_mid"
    assert row["kind"] == "npc_dota_tower"


def test_changed_positions_and_reused_entity_indices_are_preserved():
    parser = _parser()
    collector = LandmarkCollector(parser, Op.DELETED)
    collector.on_entity(Entity(), Op.CREATED)
    collector.on_entity(Entity(**{"CBodyComponent.m_vecX": 30}), Op.UPDATED)
    collector.on_entity(Entity(serial=2), Op.CREATED)
    result = collector.result()
    assert len(result["observations"]) == 3
    assert result["changes"] == [
        {"entity_index": 1, "entity_serial": 1, "positions": [(10.5, -108.0), (30, -108.0)]}
    ]


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True])
def test_missing_or_invalid_coordinate_is_retained_not_zero_filled(value):
    collector = LandmarkCollector(_parser(), Op.DELETED)
    collector.on_entity(Entity(**{"CBodyComponent.m_vecX": value}), Op.CREATED)
    result = collector.result()
    assert not result["observations"]
    row = result["missing_coordinates"][0]
    assert row["x"] is row["y"] is None
    assert "vec_x" in row["missing_coordinate_fields"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "cell_x,cell_y,vec_x,vec_y,position",
    [
        (182, 178, 240.0, 192.0, (7152.0, 6592.0)),
        (68, 72, 224.0, 230.0, (-7456.0, -6938.0)),
        (96, 80, 144.0, 32.0, (-3952.0, -6112.0)),
        (128, 127, -1.0, 128.0, (-1.0, 0.0)),
    ],
)
def test_native_formula_preserves_finite_vectors_beyond_cell_size(
    cell_x, cell_y, vec_x, vec_y, position
):
    collector = LandmarkCollector(_parser(), Op.DELETED)
    entity = Entity(
        **{
            "CBodyComponent.m_cellX": cell_x,
            "CBodyComponent.m_cellY": cell_y,
            "CBodyComponent.m_vecX": vec_x,
            "CBodyComponent.m_vecY": vec_y,
        }
    )
    collector.on_entity(entity, Op.CREATED)
    result = collector.result()
    assert not result["missing_coordinates"]
    row = result["observations"][0]
    assert (row["x"], row["y"]) == position


@pytest.mark.parametrize(
    "cls,kind",
    [
        ("CDOTA_BaseNPC_Barracks", "npc_dota_barracks"),
        ("CDOTA_BaseNPC_Fort", "npc_dota_fort"),
        ("CDOTA_Unit_Fountain", "ent_dota_fountain"),
        ("CDOTA_Unit_Twin_Gate", "npc_dota_unit_twin_gate"),
        ("CDOTA_NeutralSpawner", "npc_dota_neutral_spawner"),
        ("CDOTA_NPC_Lantern", "npc_dota_lantern"),
        ("CDOTA_BaseNPC_Watch_Tower", "npc_dota_watch_tower"),
        ("CDOTA_RoshanSpawner", "npc_dota_roshan_spawner"),
        ("CDOTA_MinibossSpawner", "npc_dota_miniboss_spawner"),
        ("CDOTA_BaseNPC_LotusPool", "npc_dota_lotus_pool"),
        ("CDOTA_BaseNPC_XP_Fountain", "npc_dota_xp_fountain"),
        ("CDOTA_Item_RuneSpawner_Bounty", "dota_item_rune_spawner_bounty"),
        ("CDOTA_Item_RuneSpawner_Powerup", "dota_item_rune_spawner_powerup"),
    ],
)
def test_explicit_building_classes(cls, kind):
    collector = LandmarkCollector(_parser(), Op.DELETED)
    collector.on_entity(Entity(cls), Op.CREATED)
    assert collector.result()["observations"][0]["kind"] == kind


def test_twin_gate_requires_explicit_npc_identity():
    collector = LandmarkCollector(_parser("npc_dota_unit_twin_gate"), Op.DELETED)
    collector.on_entity(Entity("CDOTA_BaseNPC"), Op.CREATED)
    assert collector.result()["observations"][0]["kind"] == "npc_dota_unit_twin_gate"
    other = LandmarkCollector(_parser("unrecognized_gate"), Op.DELETED)
    other.on_entity(Entity("CDOTA_Unit_UnknownGate"), Op.CREATED)
    assert not other.result()["observations"]
    assert len(other.result()["unmapped"]) == 1


def test_neutral_creeps_are_not_camp_landmarks_and_deletions_are_not_positions():
    collector = LandmarkCollector(_parser("npc_dota_neutral_kobold"), Op.DELETED)
    collector.on_entity(Entity("CDOTA_BaseNPC_Creep_Neutral"), Op.CREATED)
    collector.on_entity(Entity("CDOTA_BaseNPC"), Op.CREATED)
    collector.on_entity(Entity(), Op.DELETED)
    result = collector.result()
    assert not result["observations"] and not result["unmapped"]
    assert result["deleted_entities"] == [[1, 1]]


def test_spawner_is_not_a_neutral_creep_and_ability_is_not_a_gate():
    collector = LandmarkCollector(_parser("npc_dota_unit_twin_gate"), Op.DELETED)
    collector.on_entity(Entity("CDOTA_NeutralSpawner"), Op.CREATED)
    collector.on_entity(Entity("CDOTA_BaseNPC_Creep_Neutral", index=2), Op.CREATED)
    collector.on_entity(Entity("CDOTA_Ability_Twin_Gate_Portal_Warp", index=3), Op.CREATED)
    result = collector.result()
    assert [row["kind"] for row in result["observations"]] == ["npc_dota_neutral_spawner"]
    assert [row["class_name"] for row in result["unmapped"]] == [
        "CDOTA_Ability_Twin_Gate_Portal_Warp"
    ]


def test_watch_tower_team_changes_remain_separate_observations():
    collector = LandmarkCollector(_parser(), Op.DELETED)
    for team in (4, 2, 3):
        collector.on_entity(Entity("CDOTA_BaseNPC_Watch_Tower", m_iTeamNum=team), Op.UPDATED)
    result = collector.result()
    assert [row["team"] for row in result["observations"]] == [4, 2, 3]
    assert not result["changes"]


@pytest.mark.parametrize(
    "changed",
    [
        {"parse_error": ValueError("truncated")},
        {"truncated_at_tick": 12},
        {"match_id": 0},
        {"game_build": 0},
        {"post_game_tick": None},
    ],
)
def test_parser_must_have_real_identity_and_complete_end_marker(monkeypatch, changed):
    parser = SimpleNamespace(
        match_id=9103407326,
        game_build=6993,
        post_game_tick=50,
        parse_error=None,
        truncated_at_tick=None,
        on_entity=lambda _: None,
        parse=lambda: None,
    )
    parser.__dict__.update(changed)
    monkeypatch.setitem(sys.modules, "gem.parser", SimpleNamespace(ReplayParser=lambda _: parser))
    monkeypatch.setitem(sys.modules, "gem.state.entities", SimpleNamespace(EntityOp=Op))
    with pytest.raises(ValueError):
        capture(Path("not-read-by-fake.dem"))


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location(
        "capture_landmarks_test", ROOT / "scripts/capture_map_landmarks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return _hash(path)


@pytest.fixture
def source(tmp_path, cli, monkeypatch):
    mid = 9103407326
    demo = tmp_path / f"{mid}.dem"
    demo.write_bytes(b"PBDEMS2-synthetic")
    metadata = tmp_path / f"{mid}.json"
    _json(metadata, {"match_id": mid, "start_time": 100, "patch": 61})
    compat = tmp_path / "compat"
    sources = {}
    for name in ["__init__.py", *[f"file_{i}.py" for i in range(189)]]:
        path = compat / "gem" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")
        sources[name] = _hash(path)
    compat_hash = _json(
        compat / "manifest.json",
        {"schema": "gem-isolated-backport/1", "base_version": "0.10.0", "patched": sources},
    )
    _json(compat / "gem/catalog/resource.json", {"fixture": "initial"})
    manifest = {
        "schema": "replay-bundle/1",
        "identity": {
            "match_id": mid,
            "training_allowed": False,
            "expected_patch_code": 61,
            "discovery": {"match_id": mid, "start_time": 100},
            "patch_window": {"patch": "7.42", "release_timestamp": 99, "upper_exclusive": 101},
            "source_references": [
                {"path": str(p), "sha256": _hash(p), "size_bytes": p.stat().st_size}
                for p in (demo, metadata)
            ],
        },
        "quality": {
            "status": "passed",
            "base": {"observed_build": 6993},
            "parser": {
                "match_id": mid,
                "game_build": 6993,
                "post_game_tick": 500,
                "parse_error": None,
                "truncated_at_tick": None,
            },
        },
        "producer": {
            "parser": {
                "manifest_sha256": compat_hash,
                "verified_python_files": 190,
                "distribution_version": "0.10.0",
            },
            "dependencies": {"gem-dota": "0.10.0"},
        },
    }
    path = tmp_path / "replay-manifest.json"
    _json(path, manifest)
    monkeypatch.setattr(cli, "version", lambda _: "0.10.0")
    return path, manifest, compat, demo


def _prepare(cli, source, patch="7.42"):
    path, _, compat, _ = source
    return cli.prepare_inputs(path, _hash(path), patch, compat)


def test_cli_pins_demo_full_compatibility_and_code(cli, source):
    result = _prepare(cli, source)
    assert result["match_id"] == 9103407326 and result["game_build"] == 6993
    assert len(result["compatibility"]["python_files"]) == 190
    assert result["pins"][str(source[3])] == _hash(source[3])


def test_code_is_pinned_before_any_manifest_or_input_validation(cli, source, tmp_path, monkeypatch):
    code = tmp_path / "source.py"
    code.write_text("# original validation implementation\n")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "CODE_PATHS", (code.name,))
    original_read = cli._read

    def changed_during_validation(path, digest):
        value = original_read(path, digest)
        if Path(path) == source[0]:
            code.write_text("# changed after the validation began\n")
        return value

    monkeypatch.setattr(cli, "_read", changed_during_validation)
    with pytest.raises(ValueError, match="Source/code/compatibility drift"):
        _prepare(cli, source)


def test_holdout_rejected_before_archive_and_compatibility_access(cli, source, monkeypatch):
    source[3].unlink()
    monkeypatch.setattr(cli, "is_holdout", lambda _: True)
    with pytest.raises(ValueError, match="holdout"):
        _prepare(cli, source)


def test_wrong_patch_rejected_before_archive_access(cli, source):
    source[3].unlink()
    with pytest.raises(ValueError, match="patch"):
        _prepare(cli, source, "7.42a")


def test_changed_archive_cannot_be_parsed(cli, source):
    source[3].write_bytes(b"X" * source[3].stat().st_size)
    with pytest.raises(ValueError, match="Source hash"):
        _prepare(cli, source)


@pytest.mark.parametrize("mutation", ["missing", "added", "changed"])
def test_compatibility_sources_are_exhaustive(cli, source, mutation):
    root = source[2] / "gem"
    if mutation == "missing":
        (root / "file_0.py").unlink()
    elif mutation == "added":
        (root / "new.py").write_text("# added")
    else:
        (root / "file_0.py").write_text("# changed")
    with pytest.raises(ValueError, match="Compatibility"):
        _prepare(cli, source)


def test_existing_output_and_loaded_gem_are_rejected_before_sources(cli, tmp_path, monkeypatch):
    output = tmp_path / "exists"
    output.mkdir()
    with pytest.raises(ValueError, match="Output already exists"):
        cli.run("missing", "bad", "7.42", "missing", output)
    monkeypatch.setitem(sys.modules, "gem", SimpleNamespace())
    with pytest.raises(ValueError, match="Fresh process"):
        cli.run("missing", "bad", "7.42", "missing", tmp_path / "new")


def test_atomic_publication_cannot_replace_empty_directory(cli, tmp_path):
    source, target = tmp_path / "staging", tmp_path / "existing"
    source.mkdir()
    (source / "capture.json").write_text("{}")
    target.mkdir()
    with pytest.raises(OSError):
        cli._publish(source, target)
    assert not list(target.iterdir()) and source.is_dir()
    destination = tmp_path / "new"
    cli._publish(source, destination)
    assert (destination / "capture.json").read_text() == "{}"


@pytest.mark.parametrize(
    "mutate", [None, "archive", "build", "compatibility", "resource_added", "resource_changed"]
)
def test_fresh_capture_publishes_only_after_final_identity_and_drift_checks(
    cli, source, tmp_path, monkeypatch, mutate
):
    # Reserve undo records so the privately imported fake Gem cannot leak into other tests.
    monkeypatch.setitem(sys.modules, "gem", None)
    for name in list(sys.modules):
        if name == "gem" or name.startswith("gem."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "path", list(sys.path))

    def decoded(_):
        if mutate == "archive":
            source[3].write_bytes(b"X" * source[3].stat().st_size)
        elif mutate == "compatibility":
            (source[2] / "gem/file_0.py").write_text("# modified while parsing")
        elif mutate == "resource_added":
            _json(source[2] / "gem/catalog/new-resource.json", {"fixture": "added"})
        elif mutate == "resource_changed":
            _json(source[2] / "gem/catalog/resource.json", {"fixture": "changed"})
        return {
            "schema": "map-landmark-capture/1",
            "match_id": 9103407326,
            "game_build": 7000 if mutate == "build" else 6993,
            "observations": [],
            "missing_coordinates": [],
            "unmapped": [],
            "changes": [],
            "post_game_tick": 500,
        }

    monkeypatch.setattr(cli, "capture", decoded)
    destination = tmp_path / "published"
    if mutate:
        with pytest.raises(ValueError, match="changed|differs|drift"):
            cli.run(source[0], _hash(source[0]), "7.42", source[2], destination)
        assert not destination.exists()
    else:
        receipt = cli.run(source[0], _hash(source[0]), "7.42", source[2], destination)
        result = json.loads((destination / "capture.json").read_text())
        assert result["patch"] == "7.42" and result["training_allowed"] is False
        assert receipt["output_sha256"]["capture.json"] == _hash(destination / "capture.json")
        assert (destination / "receipt.json").is_file()
    assert not list(tmp_path.glob(".landmarks-*"))
