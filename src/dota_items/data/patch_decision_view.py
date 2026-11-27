"""Pure, conservative as-of projections of recorded entity visibility.

This is an engineering observation boundary, not an approved model feature or a
reconstruction of coordinate fog of war. Source byte verification belongs to the
caller; the supplied source reference and complete capture fingerprint are kept
only in provenance. No filesystem access is performed here.
"""

import hashlib
import json
import math
import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import PurePosixPath

from dota_items.data.patch_vision_evidence import analyze_vision_evidence


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _reference(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "sha256"}
        or not isinstance(value["path"], str)
        or not PurePosixPath(value["path"]).is_absolute()
        or not isinstance(value["sha256"], str)
        or re.fullmatch("[0-9a-f]{64}", value["sha256"]) is None
    ):
        raise ValueError("An absolute source path and SHA-256 reference are required")
    return dict(value)


def _fingerprint(capture):
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    for chunk in encoder.iterencode(capture):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class _Entity:
    index: int
    serial: int
    class_name: str
    npc_name: str | None
    npc_schema: bool


@dataclass(frozen=True, slots=True)
class _State:
    entity_id: int
    x: int | float | None
    y: int | float | None
    active: bool
    team: int | None
    life_state: int | None
    health: int | float | None
    waiting: bool | None


@dataclass(frozen=True, slots=True)
class _Frame:
    game_time: int | float
    tick: int
    state_ids: tuple
    canonical: tuple
    word_refs: tuple


class VisionDecisionIndex:
    """Index validated 7.42 observations without exposing interned pool references.

    Constructor validation reads the complete capture once. Query results use only
    packets whose actual game time AND replay tick precede the explicit bounds.
    Pregame observations are excluded; no observation is carried beyond max_age.

    Canonical membership and raw team do not establish an observable roster.
    Visibility, NPC schema and spawned-state gates precede all friendly grouping;
    unobserved slots are never enumerated. Roster completeness stays uncertified.
    """

    def __init__(self, capture, *, exact_patch, source_ref):
        if (
            exact_patch != "7.42"
            or not isinstance(capture, dict)
            or capture.get("patch") != exact_patch
            or capture.get("omniscient") is not True
            or capture.get("training_allowed") is not False
            or capture.get("action_review_allowed") is not False
        ):
            raise ValueError("Explicit diagnostic-only 7.42 capture identity is required")
        self._source_ref = _reference(source_ref)
        analyze_vision_evidence(capture)
        schemas = capture.get("field_schemas")
        if not isinstance(schemas, dict):
            raise ValueError("NPC field-schema evidence is required")
        entities = []
        for row in capture["entity_catalog"]:
            name = row.get("npc_name_first_seen")
            if name is not None and not isinstance(name, str):
                raise ValueError("First-seen NPC name must be text or unknown")
            schema = schemas.get(row["class_name"], {})
            if not isinstance(schema, dict):
                raise ValueError("Invalid NPC field-schema evidence")
            npc = schema.get("is_networked_npc_schema") is True
            entities.append(
                _Entity(
                    row["entity_index"],
                    row["entity_serial"],
                    row["class_name"],
                    name,
                    npc and row["class_name"] != "CDOTA_TempTree",
                )
            )
        columns = {name: index for index, name in enumerate(capture["state_columns"])}
        keys = ("entity_id", "x", "y", "active", "team", "life_state", "health", "waiting_to_spawn")
        self._states = tuple(
            _State(*(row[columns[key]] for key in keys)) for row in capture["states"]
        )
        self._entities = tuple(entities)
        self._words = tuple(
            tuple(tuple(pair) for pair in rows) for rows in capture["team_word_snapshots"]
        )
        self._frames = tuple(
            _Frame(
                row["game_time"],
                row["tick"],
                tuple(row["entity_state_ids"]),
                tuple(tuple(item) for item in row["canonical_heroes"]),
                tuple((role, ref["snapshot_id"]) for role, ref in row["team_word_refs"].items()),
            )
            for row in capture["frames"]
            if row["game_time"] >= 0
        )
        self._times = tuple(frame.game_time for frame in self._frames)
        self._ticks = tuple(frame.tick for frame in self._frames)
        self._match_id, self._game_build = capture["match_id"], capture["game_build"]
        self._post_game_tick = capture["post_game_tick"]
        self._end_game_time = capture["sampling"].get("end_game_time")
        self._capture_sha256 = _fingerprint(capture)

    @staticmethod
    def _visibility(entity, words):
        word = words.get(entity.index // 64)
        return None if word is None else bool(word & (1 << (entity.index % 64)))

    @staticmethod
    def _identity(entity):
        return {
            "identity": {"entity_index": entity.index, "entity_serial": entity.serial},
            "class_name": entity.class_name,
            "npc_name": entity.npc_name,
        }

    @staticmethod
    def _position(state):
        if state.life_state != 0 or state.x is None or state.y is None:
            return None
        return {"x": state.x, "y": state.y}

    def _friendly(self, player_id, entity, state):
        position = self._position(state)
        unknown = []
        if state.life_state is None:
            unknown.append("life_state")
        if state.health is None:
            unknown.append("health")
        if position is None:
            unknown.append("position")
        return {
            "player_id": player_id,
            "status": "observed",
            **self._identity(entity),
            "team": state.team,
            "position": position,
            "observed_state": {"life_state": state.life_state, "health": state.health},
            "unknown_fields": unknown,
        }

    def at(self, *, game_time, replay_tick, observer_team, max_age_seconds):
        """Return a bounded observation; never snap forward to a floored game second.

        Friendly raw life/HP requires canonical binding, matching team, an explicit
        visible word and known spawned state. Non-live friendly positions are
        withheld. Other entities require a live state and the same visibility/spawn
        checks; only identity, class/name, team and world position are exposed.
        """
        if not _number(game_time) or game_time < 0:
            raise ValueError("Decision game_time must be finite and nonnegative")
        if type(replay_tick) is not int or replay_tick < 0:
            raise ValueError("An explicit nonnegative replay_tick is required")
        if type(observer_team) is not int or observer_team not in (2, 3):
            raise ValueError("observer_team must be 2 or 3")
        if not _number(max_age_seconds) or max_age_seconds < 0:
            raise ValueError("An explicit finite nonnegative max_age_seconds is required")
        outside = replay_tick > self._post_game_tick or (
            self._end_game_time is not None and game_time > self._end_game_time
        )
        coverage_unknown = self._end_game_time is None
        index = (
            min(bisect_right(self._times, game_time), bisect_right(self._ticks, replay_tick)) - 1
        )
        frame = self._frames[index] if index >= 0 and not outside and not coverage_unknown else None
        age = None if frame is None else game_time - frame.game_time
        stale = frame is not None and age > max_age_seconds
        observation = {
            "status": "unknown" if frame is None or stale else "available",
            "game_time": None if frame is None else frame.game_time,
            "tick": None if frame is None else frame.tick,
            "age_seconds": age,
            "age_replay_ticks": None if frame is None else replay_tick - frame.tick,
            "exact_tick_match": frame is not None and frame.tick == replay_tick,
            "reason": "outside_replay_coverage"
            if outside
            else "replay_time_coverage_unknown"
            if coverage_unknown
            else "no_observation_at_or_before_both_bounds"
            if frame is None
            else "stale_observation"
            if stale
            else None,
        }
        view = {
            "observer_team": observer_team,
            "requested_game_time": game_time,
            "requested_replay_tick": replay_tick,
            "max_age_seconds": max_age_seconds,
            "observation": observation,
            # Constant by design: toggling this when an unobserved enemy row is
            # missing would itself disclose hidden information.
            "friendly_roster_complete": False,
            "friendly_roster_unknown_reason": "complete_friendly_roster_not_certified",
            "friendly_heroes": [],
            "visible_entities": [],
        }
        if frame is not None and not stale:
            role = "radiant" if observer_team == 2 else "dire"
            snapshot = dict(frame.word_refs).get(role)
            words = {} if snapshot is None else dict(self._words[snapshot])
            selected = {self._states[sid].entity_id: self._states[sid] for sid in frame.state_ids}
            friendly_ids = set()
            for player_id, entity_id, _handle in sorted(frame.canonical):
                state = selected.get(entity_id)
                entity = self._entities[entity_id]
                # A hidden raw team or canonical binding must not create even
                # an "unknown" friendly slot: that would disclose its existence.
                if (
                    state is not None
                    and state.active
                    and self._visibility(entity, words) is True
                    and entity.npc_schema
                    and state.waiting is False
                    and state.team == observer_team
                ):
                    friendly_ids.add(entity_id)
                    view["friendly_heroes"].append(self._friendly(player_id, entity, state))
            for entity_id, state in sorted(
                selected.items(),
                key=lambda item: (self._entities[item[0]].index, self._entities[item[0]].serial),
            ):
                if entity_id in friendly_ids:
                    continue
                entity = self._entities[entity_id]
                if (
                    not entity.npc_schema
                    or not state.active
                    or self._visibility(entity, words) is not True
                    or state.waiting is not False
                    or state.life_state != 0
                ):
                    continue
                position = self._position(state)
                view["visible_entities"].append(
                    {
                        **self._identity(entity),
                        "team": state.team,
                        "position": position,
                        "unknown_fields": ["position"] if position is None else [],
                    }
                )
        return {
            "schema": "patch-decision-view/1",
            "exact_patch": "7.42",
            "known_view": view,
            "provenance": {
                "source_ref": dict(self._source_ref),
                "capture_canonical_sha256": self._capture_sha256,
                "match_id": self._match_id,
                "game_build": self._game_build,
            },
            "training_allowed": False,
            "action_review_allowed": False,
            "limits": [
                "Recorded target visibility does not certify full coordinate fog of war.",
                "Friendly HP/life is raw observed state under canonical/team/visible/spawn gates.",
                "Unobserved entities are not enumerated, counted or carried from earlier packets.",
                "Roster completeness is unverified; false does not prove a hero is absent.",
                "Other entity HP, canonical ownership, ranges, modifiers and owners are omitted.",
                "Global rules, trees, future entries and capture fingerprints are not features.",
                "Age is game-clock age; available history need not be the current packet.",
                "Matching ticks cannot identify one inner packet; its ordinal was not captured.",
                "Source bytes must be verified externally before using this diagnostic view.",
            ],
        }
