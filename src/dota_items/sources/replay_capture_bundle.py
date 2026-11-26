"""One verified Gem pass with streamed state/extras and unchanged legacy row semantics.

This is a new producer, not a replacement for any frozen ``gem_capture*`` producer.
The caller owns compression, atomic publication, source binding and quality policy.
Call ``parser_identity`` before capture in the isolated worker. Gem's base extractors
still retain their events/snapshots; only the new state/extras sinks are streaming,
so this module does not promise constant memory for an entire replay.
"""

import hashlib
import json
import math
import re
from enum import Enum
from importlib import import_module
from importlib.metadata import version
from pathlib import Path

from dota_items.contracts.replay_context import export_context
from dota_items.normalize import normalize_match
from dota_items.sources.gem_capture import (
    CAPTURE_VERSION as BASE_CAPTURE_VERSION,
)
from dota_items.sources.gem_capture import (
    require_complete_parse,
    snapshot_evidence,
)
from dota_items.sources.gem_capture_creeps import creep_rows
from dota_items.sources.gem_capture_extras import CAPTURE_VERSION as EXTRAS_VERSION
from dota_items.sources.gem_capture_extras import extras_row
from dota_items.sources.gem_capture_v3 import CAPTURE_VERSION as STATE_VERSION
from dota_items.sources.gem_capture_v3 import hero_row, world_row
from dota_items.sources.gem_replay import adapter_fingerprint, canonicalize_match
from dota_items.storage import file_hash

BUNDLE_VERSION = "replay-capture-bundle/1"
GEM_VERSION = "0.10.0"
EXPECTED_PYTHON_FILES = 190
COORDINATES = "cell space (cell*128+vec), map centre 16384"


def _plain_json_tree(value):
    """Apply the old JSON round-trip's scalar conversion without its huge string.

    Gem ``to_dict`` intentionally leaves str/IntEnum scalar subclasses intact.
    ``json.dumps`` supports those, whereas the archive's plain-value contract
    correctly rejects them. Normalize containers in place to avoid another full
    object tree; preserve dictionary order and reject colliding JSON key spellings.
    """
    if isinstance(value, Enum):
        return _plain_json_tree(value.value)
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, int):
        return int.__int__(value)
    if isinstance(value, float):
        result = float.__float__(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite replay JSON value")
        return result
    if isinstance(value, (list, tuple)):
        result = value if type(value) is list else list(value)
        for index, child in enumerate(result):
            result[index] = _plain_json_tree(child)
        return result
    if isinstance(value, dict):
        result = value
        if type(value) is not dict or any(type(key) is not str for key in value):
            result = {}
            for key, child in value.items():
                key = _plain_json_tree(key)
                if type(key) is str:
                    name = key
                elif key is None or type(key) in (bool, int, float):
                    name = json.dumps(key, allow_nan=False)
                else:
                    raise ValueError("Unsupported replay JSON key")
                if name in result:
                    raise ValueError("Replay JSON key normalization collision")
                result[name] = child
        for key, child in result.items():
            result[key] = _plain_json_tree(child)
        return result
    raise ValueError("Unsupported replay JSON value")


def parser_identity(compat_dir: Path, expected_manifest_sha256: str) -> dict:
    """Verify the caller-pinned compatibility profile and the modules actually loaded.

    A matching distribution version alone is insufficient. The expected manifest
    digest must come from the caller's reviewed configuration, not from this file.
    Nothing is installed and no alternate import path is silently selected.
    """
    if not isinstance(expected_manifest_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_manifest_sha256
    ):
        raise ValueError("Expected compatibility manifest SHA-256 is required")
    root = Path(compat_dir).resolve(strict=True)
    manifest_path = root / "manifest.json"
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("Compatibility manifest SHA-256 mismatch")
    manifest = json.loads(raw)
    expected = manifest.get("patched")
    if (
        manifest.get("schema") != "gem-isolated-backport/1"
        or manifest.get("base_version") != GEM_VERSION
        or not isinstance(expected, dict)
        or len(expected) != EXPECTED_PYTHON_FILES
    ):
        raise ValueError("Unsupported compatibility profile")
    package = root / "gem"
    actual = {str(path.relative_to(package)) for path in package.rglob("*.py")}
    if actual != set(expected):
        raise ValueError("Compatibility Python file inventory mismatch")
    for name, digest in expected.items():
        path = (package / name).resolve(strict=True)
        if not path.is_relative_to(package) or file_hash(path) != digest:
            raise ValueError(f"Compatibility Python source mismatch: {name}")
    if version("gem-dota") != GEM_VERSION:
        raise ValueError("Capture requires the verified gem-dota==0.10.0 distribution")
    gem, parser_module = import_module("gem"), import_module("gem.parser")
    module_path = Path(gem.__file__).resolve(strict=True)
    parser_path = Path(parser_module.__file__).resolve(strict=True)
    if module_path != (package / "__init__.py") or parser_path != (package / "parser.py"):
        raise ValueError("Gem imported from an unverified compatibility path")
    return {
        "schema": "replay-parser-identity/1",
        "manifest_sha256": expected_manifest_sha256,
        "distribution_version": GEM_VERSION,
        "base_version": manifest["base_version"],
        "verified_python_files": len(expected),
        "compat_path": str(root),
        "module_path": str(module_path),
        "parser_path": str(parser_path),
    }


def _parser_evidence(parser):
    keys = (
        "match_id",
        "game_build",
        "game_start_tick",
        "post_game_tick",
        "truncated_at_tick",
        "duration_s",
    )
    result = {key: getattr(parser, key, None) for key in keys}
    error = getattr(parser, "parse_error", None)
    result["parse_error"] = None if error is None else f"{type(error).__name__}: {error}"
    end = result["post_game_tick"]
    clock = getattr(parser, "game_clock", None)
    result["post_game_seconds"] = (
        clock.game_seconds_at(end) if type(end) is int and clock is not None else None
    )
    return result


def _require_end_evidence(parser):
    require_complete_parse(parser)
    result = _parser_evidence(parser)
    for key in ("match_id", "game_build"):
        if type(result[key]) is not int or result[key] <= 0:
            raise ValueError(f"Replay has no valid observed {key}")
    start, end = result["game_start_tick"], result["post_game_tick"]
    if type(start) is not int or type(end) is not int or end <= start:
        raise ValueError("Replay has no observed complete game-end interval")
    second = result["post_game_seconds"]
    if type(second) not in (int, float) or not math.isfinite(second) or second <= 0:
        raise ValueError("Replay has no valid post-game time")
    if result["truncated_at_tick"] is not None:
        raise ValueError("Replay reports truncation despite no parser exception")
    return result


def _sample_state(parser, players, second, position):
    """Reuse the frozen v3 public row functions at the same tick-start phase."""
    em = parser.entity_manager
    names = parser.string_tables.get_by_name("EntityNames")
    heroes = {}
    for pid in range(10):
        hero = players._canonical_hero_entity(pid)
        if hero is not None:
            heroes[pid] = hero
    radiant = em.find_by_class_name("CDOTA_DataRadiant")
    dire = em.find_by_class_name("CDOTA_DataDire")
    resource = em.find_by_class_name("CDOTA_PlayerResource")
    hero_rows = []
    for pid, hero in sorted(heroes.items()):
        team_data = radiant if hero.get("m_iTeamNum") == 2 else dire
        hero_rows.append(hero_row(pid, hero, em, names, players, team_data, resource, position))
    return {"t": second, "heroes": hero_rows, "world": world_row(em, heroes, position, names)}


def capture_bundle(unpacked_path, *, emit_state, emit_extras, start_time=-90):
    """Parse once; emit legacy-compatible rows immediately and return plain values.

    The sinks can receive partial rows if decoding or publication fails; their owner
    must keep those outputs uncommitted until all quality checks pass. Full sampling
    range is preserved. Consumers must separately restrict decision windows to the
    validated match duration, instead of treating post-game rows as opportunities.
    ``raw``/``normalized`` are in-memory mappings, never uncompressed disk files.
    Evidence filenames/digests belong to the storage layer and are not filled here.
    """
    if not callable(emit_state) or not callable(emit_extras):
        raise TypeError("State and extras sinks must be callable")
    if type(start_time) not in (int, float) or not math.isfinite(start_time):
        raise ValueError("Capture start_time must be finite")
    if version("gem-dota") != GEM_VERSION:
        raise ValueError("Bundle capture requires the verified gem-dota==0.10.0")
    import gem
    from gem.combat.aggregator import _CombatAggregator
    from gem.extractors._snapshots import _pos
    from gem.extractors.courier import CourierExtractor
    from gem.extractors.draft import DraftExtractor
    from gem.extractors.intervals import IntervalExtractor
    from gem.extractors.objectives import ObjectivesExtractor
    from gem.extractors.players import _NULL_HANDLE, PlayerExtractor
    from gem.extractors.smoke_vision import SmokeExtractor, VisionModifierExtractor
    from gem.extractors.visibility import VisibilityExtractor
    from gem.extractors.wards import WardsExtractor
    from gem.parser import ReplayParser
    from gem.results.assembly import build_parsed_match

    class StatePlayerExtractor(PlayerExtractor):
        def __init__(self):
            super().__init__()
            self.coach_states = []

        def _sample(self, tick, *, minute=False):
            start = len(self.snapshots)
            super()._sample(tick, minute=minute)
            for snapshot in self.snapshots[start:]:
                row = snapshot_evidence(self, snapshot, _NULL_HANDLE)
                if row is not None:
                    self.coach_states.append(row)

    parser = ReplayParser(str(unpacked_path))
    players = StatePlayerExtractor()
    visibility = VisibilityExtractor(players)
    intervals = IntervalExtractor()
    objectives = ObjectivesExtractor()
    wards = WardsExtractor()
    couriers = CourierExtractor()
    draft = DraftExtractor()
    smoke = SmokeExtractor(players)
    modifiers = VisionModifierExtractor(players)
    for extractor in (players, visibility, intervals, objectives, wards, couriers, draft):
        extractor.attach(parser)
    combat = _CombatAggregator(players)
    entries, chat, neutral = [], [], []
    parser.on_combat_log_entry(combat.on_entry)
    parser.on_combat_log_entry(entries.append)
    parser.on_chat_message(chat.append)
    parser.on_neutral_item_found(neutral.append)
    smoke.attach(parser)
    modifiers.attach(parser)
    counts = {"state": 0, "extras": 0}
    last = None

    def sample(_tick):
        nonlocal last
        em = parser.entity_manager
        game_time = getattr(parser, "game_time_s", None)
        if em is None or game_time is None or game_time < start_time:
            return
        second = int(game_time // 1)
        if second == last:
            return
        last = second
        emit_state(_sample_state(parser, players, second, _pos))
        counts["state"] += 1
        emit_extras({"t": second, "creeps": creep_rows(em, _pos), **extras_row(em, _pos)})
        counts["extras"] += 1

    parser.on_tick_start(sample)
    parser.parse()
    evidence = _require_end_evidence(parser)
    draft.finalize()
    wards.finalize()
    match = build_parsed_match(
        parser=parser,
        player_ext=players,
        obj_ext=objectives,
        ward_ext=wards,
        courier_ext=couriers,
        draft_ext=draft,
        combat_agg=combat,
        all_entries=entries,
        chat_entries=chat,
        smoke_events=smoke.finalize(),
        vision_modifier_events=modifiers.finalize(),
        vision_modifier_pairing_issues=modifiers.pairing_issues,
        neutral_item_finds=neutral,
        interval_ext=intervals,
        hero_visibility_events=visibility.events,
        entity_visibility_events=visibility.entity_events,
    )
    canonical, issues = canonicalize_match(match)
    replay_sha = file_hash(Path(unpacked_path))
    for player in canonical["players"]:
        validated = normalize_match(
            canonical,
            player["player_slot"],
            source=Path(unpacked_path).name,
            fingerprint="sha256:" + replay_sha,
        )
        if any(flag.startswith("invalid_event:") for flag in validated.quality_flags):
            raise ValueError("Bundle adapter produced an invalid purchase event")
    # Keep gem.to_json's metadata order and conversion, without constructing its
    # additional full-size JSON string only to parse it back into Python objects.
    payload = {"schema_version": gem.SCHEMA_VERSION, "gem_version": GEM_VERSION}
    payload.update(gem.to_dict(match))
    payload["coach_state_snapshots"] = players.coach_states
    payload["coach_capture_version"] = BASE_CAPTURE_VERSION
    payload = _plain_json_tree(payload)
    canonical["adapter_fingerprint"] = adapter_fingerprint()
    canonical["capture_version"] = BASE_CAPTURE_VERSION
    canonical["context"] = export_context(payload, match.game_clock, match.duration)
    common = {
        "gem_version": GEM_VERSION,
        "match_id": evidence["match_id"],
        "omniscient": True,
        "coordinates": COORDINATES,
    }
    headers = {
        "state": {
            "schema": STATE_VERSION,
            **common,
            "seconds": counts["state"],
            "unit_state": "raw m_nUnitState64 only; decoding is a TODO (U130)",
        },
        "extras": {
            "schema": EXTRAS_VERSION,
            **common,
            "seconds": counts["extras"],
            "fields": {
                "creeps": ["team", "x", "y"],
                "watchers": ["x", "y", "holder_team_or_0"],
                "outposts": ["x", "y", "team"],
            },
        },
    }
    return {
        "normalized": _plain_json_tree(canonical),
        "raw": payload,
        "parser": evidence,
        "headers": headers,
        "issues": issues,
    }
