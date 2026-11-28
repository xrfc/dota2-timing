"""Verified parser loading and one-pass/streaming equivalence at the Gem boundary."""

import hashlib
import json
from dataclasses import dataclass, field
from enum import IntEnum
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

from dota_items.sources import gem_capture, gem_capture_extras, gem_capture_v3
from dota_items.sources import replay_capture_bundle as bundle


def test_gem_enum_tree_matches_legacy_json_round_trip_without_full_string():
    pytest.importorskip("gem")
    from gem.results.models import VisibilityState, VisionModifierSemantic

    class NumericEnum(IntEnum):
        VALUE = 7

    payload = {
        "states": [VisibilityState.VISIBLE, VisibilityState.UNKNOWN],
        "semantic": VisionModifierSemantic.DIRECT_TARGET_REVEAL,
        "tuple": (NumericEnum.VALUE, VisibilityState.HIDDEN),
        "keys": {1: VisibilityState.VISIBLE, None: True},
    }
    expected = json.loads(json.dumps(payload, allow_nan=False))
    original_list = payload["states"]
    actual = bundle._plain_json_tree(payload)
    assert actual == expected
    assert actual is payload and actual["states"] is original_list
    assert type(actual["states"][0]) is str
    assert type(actual["tuple"]) is list and type(actual["tuple"][0]) is int
    assert all(type(key) is str for key in actual["keys"])


@pytest.mark.parametrize("payload", [{1: "a", "1": "b"}, {None: "a", "null": "b"}])
def test_json_key_normalization_rejects_collisions(payload):
    with pytest.raises(ValueError, match="collision"):
        bundle._plain_json_tree(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), b"bytes", object()])
def test_json_tree_rejects_nonfinite_or_unsupported_values(value):
    with pytest.raises(ValueError):
        bundle._plain_json_tree({"nested": [value]})


def profile(tmp_path, monkeypatch):
    package = tmp_path / "gem"
    package.mkdir()
    names = ["__init__.py", "parser.py", *[f"m{i}.py" for i in range(188)]]
    expected = {}
    for name in names:
        path = package / name
        path.write_text("# pinned synthetic source\n", encoding="utf-8")
        expected[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema": "gem-isolated-backport/1",
        "base_version": "0.10.0",
        "patched": expected,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(bundle, "version", lambda name: "0.10.0")
    modules = {
        "gem": SimpleNamespace(__file__=str(package / "__init__.py")),
        "gem.parser": SimpleNamespace(__file__=str(package / "parser.py")),
    }
    monkeypatch.setattr(bundle, "import_module", modules.__getitem__)
    return hashlib.sha256(path.read_bytes()).hexdigest(), modules


def test_parser_identity_checks_pinned_inventory_and_actual_import(tmp_path, monkeypatch):
    digest, _modules = profile(tmp_path, monkeypatch)
    evidence = bundle.parser_identity(tmp_path, digest)
    assert evidence["verified_python_files"] == 190
    assert evidence["manifest_sha256"] == digest
    assert evidence["module_path"] == str(tmp_path / "gem/__init__.py")
    assert evidence["parser_path"] == str(tmp_path / "gem/parser.py")


@pytest.mark.parametrize("change", ["manifest", "source", "extra", "missing", "path", "version"])
def test_parser_identity_rejects_drift_before_capture(tmp_path, monkeypatch, change):
    digest, modules = profile(tmp_path, monkeypatch)
    if change == "manifest":
        (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    elif change == "source":
        (tmp_path / "gem/m0.py").write_text("# changed\n", encoding="utf-8")
    elif change == "extra":
        (tmp_path / "gem/new.py").write_text("", encoding="utf-8")
    elif change == "missing":
        (tmp_path / "gem/m0.py").unlink()
    elif change == "path":
        modules["gem"].__file__ = str(tmp_path / "gem/m0.py")
    else:
        monkeypatch.setattr(bundle, "version", lambda name: "0.15.0")
    with pytest.raises(ValueError):
        bundle.parser_identity(tmp_path, digest)


@pytest.mark.parametrize("digest", [None, "", "a" * 63, "A" * 64, True])
def test_parser_identity_requires_reviewed_digest(tmp_path, digest):
    with pytest.raises(ValueError, match="manifest SHA"):
        bundle.parser_identity(tmp_path, digest)


def test_parser_identity_rejects_source_symlink_outside_profile(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    root.mkdir()
    digest, _modules = profile(root, monkeypatch)
    path = root / "gem/m0.py"
    outside = tmp_path / "same-bytes.py"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="source mismatch"):
        bundle.parser_identity(root, digest)


@dataclass
class Player:
    player_id: int
    hero_id: int
    purchase_log: list = field(default_factory=list)


@dataclass
class Match:
    match_id: int = 9_103_408_009
    duration: int = 3
    game_mode: int = 22
    post_game_tick: int = 90
    players: list = field(default_factory=lambda: [Player(i, 44 + i) for i in range(10)])
    combat_log: list = field(default_factory=list)
    hero_visibility_events: list = field(default_factory=list)
    entity_visibility_events: list = field(default_factory=list)
    wards: list = field(default_factory=list)
    smoke_events: list = field(default_factory=list)
    vision_modifiers: list = field(default_factory=list)
    game_clock: object = field(
        default_factory=lambda: SimpleNamespace(game_seconds_at=lambda tick: tick / 30),
        metadata={"serialize": False},
    )


class Entity:
    def __init__(self, index, cls="CDOTA_Unit_Hero_Axe", **fields):
        self.index, self.cls = index, cls
        self.pos = [16384 + index, 16384]
        self.fields = {
            "m_pEntity.m_nameStringTableIndex": index,
            "m_iHealth": 100,
            "m_iMaxHealth": 100,
            "m_lifeState": 0,
            "m_iCurrentLevel": 1,
            "m_iTeamNum": 2 if index < 5 else 3,
            **fields,
        }

    def get(self, key):
        return 16777215 if key.startswith("m_hItems.") else self.fields.get(key)

    get_int32 = get
    get_float32 = get
    get_uint32 = get

    def get_index(self):
        return self.index

    def get_serial(self):
        return 1

    def get_class_name(self):
        return self.cls


class EmptyExtractor:
    def __init__(self, *args):
        self.events, self.entity_events, self.pairing_issues = [], [], []

    def attach(self, parser):
        pass

    def finalize(self):
        return []


class FakePlayers(EmptyExtractor):
    def __init__(self):
        super().__init__()
        self.snapshots = []
        self.heroes = {i: Entity(i) for i in range(10)}

    def attach(self, parser):
        parser.players = self

    def _canonical_hero_entity(self, pid):
        return self.heroes[pid]

    def _sample(self, tick, *, minute=False):
        self.snapshots.extend(
            SimpleNamespace(tick=tick, player_id=i, level=1, ability_levels={}, items={})
            for i in range(10)
        )


class FakeCombat:
    def __init__(self, players):
        pass

    def on_entry(self, entry):
        pass


@pytest.fixture
def fake_runtime(monkeypatch):
    pytest.importorskip("gem")

    class Parser:
        calls = 0
        instances = []
        overrides = {}

        def __init__(self, path):
            self.path = path
            self.match_id, self.game_build = 9_103_408_009, 6993
            self.game_start_tick, self.post_game_tick = 0, 90
            self.parse_error = self.truncated_at_tick = None
            self.duration_s = 3
            self.game_clock = Match().game_clock
            self.callbacks = []
            self.parsing = False
            self.game_time_s = None
            creep = Entity(200, "CDOTA_BaseNPC_Creep_Lane", m_iTeamNum=2)
            watcher = Entity(201, "CDOTA_NPC_Lantern", m_nFoWTeam=None)
            self.entity_manager = SimpleNamespace(
                find_by_class_name=lambda name: None,
                all_active=lambda: [creep, watcher],
                find_by_handle=lambda handle: None,
            )
            names = SimpleNamespace(items={i: (f"hero_{i}", None) for i in range(10)})
            self.string_tables = SimpleNamespace(get_by_name=lambda name: names)
            for key, value in self.overrides.items():
                setattr(self, key, value)
            self.instances.append(self)

        def on_tick_start(self, callback):
            self.callbacks.append(callback)

        def on_combat_log_entry(self, callback):
            pass

        on_chat_message = on_combat_log_entry
        on_neutral_item_found = on_combat_log_entry

        def parse(self):
            type(self).calls += 1
            self.parsing = True
            try:
                for game_time in (-1, 0, 0.4, 1, 2, 3, 4):
                    self.game_time_s = game_time
                    self.tick = int(game_time * 30)
                    if hasattr(self, "players"):
                        self.players._sample(self.tick)
                    for callback in self.callbacks:
                        callback(self.tick)
            except Exception as error:
                # Real Gem records callback/stream failures instead of re-raising.
                self.parse_error = error
                self.truncated_at_tick = self.tick
            finally:
                self.parsing = False

    replacements = {
        "gem.parser": {"ReplayParser": Parser},
        "gem.extractors.players": {"PlayerExtractor": FakePlayers},
        "gem.extractors._snapshots": {"_pos": lambda entity: entity.pos},
        "gem.combat.aggregator": {"_CombatAggregator": FakeCombat},
        "gem.results.assembly": {"build_parsed_match": lambda **kwargs: Match()},
    }
    for module, classes in (
        ("courier", ["CourierExtractor"]),
        ("draft", ["DraftExtractor"]),
        ("intervals", ["IntervalExtractor"]),
        ("objectives", ["ObjectivesExtractor"]),
        ("smoke_vision", ["SmokeExtractor", "VisionModifierExtractor"]),
        ("visibility", ["VisibilityExtractor"]),
        ("wards", ["WardsExtractor"]),
    ):
        replacements[f"gem.extractors.{module}"] = {name: EmptyExtractor for name in classes}
    for module, values in replacements.items():
        imported = import_module(module)
        for name, value in values.items():
            monkeypatch.setattr(imported, name, value)
    monkeypatch.setattr(bundle, "version", lambda name: "0.10.0")
    return Parser


def test_one_pass_streams_before_return_and_matches_legacy_channels(tmp_path, fake_runtime):
    source = tmp_path / "test.dem"
    source.write_bytes(b"synthetic replay source")
    states, extras = [], []

    def state_sink(row):
        assert fake_runtime.instances[-1].parsing
        states.append(row)

    def extras_sink(row):
        assert fake_runtime.instances[-1].parsing
        extras.append(row)

    result = bundle.capture_bundle(source, emit_state=state_sink, emit_extras=extras_sink)
    assert fake_runtime.calls == 1
    assert [r["t"] for r in states] == [-1, 0, 1, 2, 3, 4]
    assert result["parser"]["match_id"] == 9_103_408_009
    assert result["parser"]["game_build"] == 6993
    for name in ("state", "extras"):
        assert result["headers"][name]["seconds"] == 6
        assert result["headers"][name]["match_id"] == 9_103_408_009
    old_state_header, old_states = gem_capture_v3.capture_state_v3(source)
    old_extras_header, old_extras = gem_capture_extras.capture_extras(source)
    assert states == old_states and extras == old_extras
    assert result["headers"]["state"] == {**old_state_header, "match_id": 9_103_408_009}
    assert result["headers"]["extras"] == {**old_extras_header, "match_id": 9_103_408_009}
    import gem

    old_match, old_coach_states = gem_capture.parse_with_state(source)
    old_raw = json.loads(gem.to_json(old_match))
    old_raw["coach_state_snapshots"] = old_coach_states
    old_raw["coach_capture_version"] = gem_capture.CAPTURE_VERSION
    assert result["raw"] == old_raw
    assert list(result["raw"]) == list(old_raw)
    old_canonical, _issues = bundle.canonicalize_match(old_match)
    old_canonical["adapter_fingerprint"] = bundle.adapter_fingerprint()
    old_canonical["capture_version"] = gem_capture.CAPTURE_VERSION
    old_canonical["context"] = bundle.export_context(old_raw, old_match.game_clock, 3)
    assert result["normalized"] == old_canonical
    assert "evidence_sha256" not in result["normalized"]
    # The new container preserves the old schema's unknown-to-zero watcher behavior.
    assert extras[0]["watchers"][0][2] == 0


def test_sink_failure_cannot_become_a_successful_bundle(tmp_path, fake_runtime):
    source = tmp_path / "test.dem"
    source.write_bytes(b"synthetic")
    emitted = []

    def broken_sink(row):
        raise OSError("disk full")

    with pytest.raises(ValueError, match="Incomplete Gem parse.*disk full") as error:
        bundle.capture_bundle(source, emit_state=emitted.append, emit_extras=broken_sink)
    assert isinstance(error.value.__cause__, OSError)
    assert len(emitted) == 1 and fake_runtime.calls == 1


def test_capture_gem_enum_payload_can_enter_strict_archive(tmp_path, fake_runtime, monkeypatch):
    from gem.results import assembly
    from gem.results.models import VisibilityState

    from dota_items.data.replay_bundle import BundleWriter, read_json_artifact

    match = Match(
        hero_visibility_events=[
            {
                "tick": 30,
                "radiant_state": VisibilityState.VISIBLE,
                "dire_state": VisibilityState.UNKNOWN,
            }
        ]
    )
    monkeypatch.setattr(assembly, "build_parsed_match", lambda **kwargs: match)
    source = tmp_path / "enum.dem"
    source.write_bytes(b"synthetic")
    result = bundle.capture_bundle(
        source, emit_state=lambda row: None, emit_extras=lambda row: None
    )
    assert type(result["raw"]["hero_visibility_events"][0]["radiant_state"]) is str
    payload = result["normalized"]["context"]["channels"]["hero_visibility_events"][0]["payload"]
    assert type(payload["radiant_state"]) is str and payload["radiant_state"] == "visible"
    archive = tmp_path / "archive"
    writer = BundleWriter(archive, identity={"match_id": match.match_id}, producer={"test": True})
    writer.add_json("raw", result["raw"])
    writer.add_json("normalized", result["normalized"])
    writer.finish({"status": "synthetic-only"})
    assert read_json_artifact(archive, "raw") == result["raw"]


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"match_id": 0}, "match_id"),
        ({"match_id": True}, "match_id"),
        ({"game_build": 0}, "game_build"),
        ({"post_game_tick": None}, "game-end"),
        ({"post_game_tick": 0}, "game-end"),
        ({"game_start_tick": None}, "game-end"),
        ({"truncated_at_tick": 90}, "truncation"),
    ],
)
def test_missing_identity_or_end_is_rejected(tmp_path, fake_runtime, overrides, reason):
    fake_runtime.overrides = overrides
    source = tmp_path / "test.dem"
    source.write_bytes(b"synthetic")
    with pytest.raises(ValueError, match=reason):
        bundle.capture_bundle(source, emit_state=lambda row: None, emit_extras=lambda row: None)


def test_real_header_only_gem_result_is_rejected(tmp_path):
    pytest.importorskip("gem")
    source = tmp_path / "header.dem"
    source.write_bytes(b"PBDEMS2\x00" + b"\x00" * 8)
    with pytest.raises(ValueError, match="observed match_id"):
        bundle.capture_bundle(source, emit_state=lambda row: None, emit_extras=lambda row: None)


@pytest.mark.parametrize("start", [float("nan"), float("inf"), None, True])
def test_invalid_start_is_rejected_before_opening_a_replay(start):
    with pytest.raises(ValueError, match="start_time"):
        bundle.capture_bundle(
            Path("does-not-exist.dem"),
            emit_state=lambda row: None,
            emit_extras=lambda row: None,
            start_time=start,
        )
