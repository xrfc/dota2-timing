"""Canonical hero vision fields and team bitsets; retrospective evidence only.

Gem is supplied by the caller's pinned isolated environment. This module does not
infer a daylight schedule, current modifier-adjusted range, or decision-time FOW.
"""

import math
from collections import Counter

from dota_items.sources.replay_identity import entity_evidence

RANGE_FIELDS = {
    "day_vision_range": "m_iDayTimeVisionRange",
    "night_vision_range": "m_iNightTimeVisionRange",
    "current_vision_range": "m_iCurrentVisionRange",
}
RAW_FIELDS = (
    *RANGE_FIELDS.values(),
    "m_iTaggedAsVisibleByTeam",
    "m_nUnitState64",
    "m_iHealth",
)
TIME_OF_DAY = "m_pGameRules.m_iNetTimeOfDay"
TEAM_CLASSES = {
    "radiant": ("CDOTA_DataRadiant", "CDOTADataRadiant"),
    "dire": ("CDOTA_DataDire", "CDOTADataDire"),
}


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _scalar(value):
    if value is None or type(value) in (str, bool, int):
        return value
    return value if type(value) is float and math.isfinite(value) else None


def _present(entity, name):
    serializer = getattr(entity.cls, "serializer", None)
    return bool(serializer and serializer._resolve_field(name).path is not None)


def _identity(entity):
    if entity is None:
        return None
    return {
        "entity_index": entity.get_index(),
        "entity_serial": entity.get_serial(),
        "class_name": entity.get_class_name(),
    }


class VisibilityCollector:
    """Raw-tick candidates regrouped by the completed pause-aware game clock.

    Live Gem clocks omit open pauses until those intervals close. Never reserve
    game-second buckets during parsing: doing so drops samples after a pause.
    Negative seconds are retained explicitly; post-game samples are excluded.
    """

    def __init__(self, parser, players):
        self.parser, self.players = parser, players
        self.frames, self.field_schemas = [], {}
        self.last_candidate_tick, self.last_live_second = None, None
        self.skipped = Counter()

    def _hero(self, player_id, hero, teams):
        raw_identity = entity_evidence(hero)
        row = {key: _scalar(value) for key, value in raw_identity.items()}
        row.update(
            player_id=player_id,
            entity_handle=self.players._hero_handle_for_player(player_id),
            active=hero.active,
            canonical_for_slot=True,
        )
        missing = []
        for axis in ("x", "y"):
            cell, vec = raw_identity[f"cell_{axis}"], raw_identity[f"vec_{axis}"]
            if type(cell) is not int or cell < 0:
                missing.append(f"cell_{axis}")
            if not _finite(vec):
                missing.append(f"vec_{axis}")
        row.update(
            x=None if missing else row["cell_x"] * 128 + row["vec_x"] - 16384,
            y=None if missing else row["cell_y"] * 128 + row["vec_y"] - 16384,
            missing_coordinate_fields=missing,
        )
        raw_fields = {name: _scalar(hero.get(name)) for name in RAW_FIELDS}
        row["raw_fields"] = raw_fields
        row["hp"] = raw_fields["m_iHealth"]
        row["invalid_range_fields"] = []
        for label, name in RANGE_FIELDS.items():
            value = raw_fields[name]
            row[label] = value if _finite(value) and value >= 0 else None
            if value is not None and row[label] is None:
                row["invalid_range_fields"].append(name)
        if row["class_name"] not in self.field_schemas:
            self.field_schemas[row["class_name"]] = {
                name: _present(hero, name) for name in RAW_FIELDS
            }
        index = row["entity_index"]
        if type(index) is not int or not 0 <= index < 16384:
            raise ValueError("Hero entity index outside team visibility bitset")
        word_index, bit = index >> 6, index & 63
        word_field = f"m_bNPCVisibleState.{word_index:04d}"
        words, visible, invalid = {}, {}, []
        for label, entity in teams.items():
            value = None if entity is None else entity.get(word_field)
            words[label] = _scalar(value)
            valid = type(value) is int and 0 <= value < 2**64
            visible[label] = bool(value & (1 << bit)) if valid else None
            if value is not None and not valid:
                invalid.append(label)
        row.update(
            visibility=visible,
            visibility_words=words,
            visibility_word_index=word_index,
            visibility_bit_index=bit,
            invalid_visibility_words=invalid,
            vismask=(
                int(visible["radiant"]) | (int(visible["dire"]) << 1)
                if all(value is not None for value in visible.values())
                else None
            ),
        )
        return row

    def on_tick_start(self, _net_tick):
        parser = self.parser
        tick, manager = parser.tick, parser.entity_manager
        if parser.post_game_tick is not None and tick > parser.post_game_tick:
            self.skipped["post_game_ticks"] += 1
            return
        if manager is None:
            self.skipped["missing_manager_ticks"] += 1
            return
        game_time = parser.game_clock.game_time_at(tick)
        game_time = game_time if _finite(game_time) else None
        second = math.floor(game_time) if game_time is not None else None
        if (
            self.last_candidate_tick is not None
            and tick - self.last_candidate_tick < 15
            and second == self.last_live_second
        ):
            return
        self.last_candidate_tick, self.last_live_second = tick, second
        teams = {}
        for label, names in TEAM_CLASSES.items():
            teams[label] = next(
                (
                    entity
                    for name in names
                    if (entity := manager.find_by_class_name(name)) is not None
                ),
                None,
            )
        rules = manager.find_by_class_name("CDOTAGamerulesProxy")
        day_raw = None if rules is None else _scalar(rules.get(TIME_OF_DAY))
        heroes, missing = [], []
        for player_id in range(10):
            hero = self.players._canonical_hero_entity(player_id)
            if hero is None:
                missing.append(player_id)
            else:
                heroes.append(self._hero(player_id, hero, teams))
        self.frames.append(
            {
                "t": second,
                "tick": tick,
                "sample_game_time": game_time,
                "sample_parser_game_time_s": _scalar(getattr(parser, "game_time_s", None)),
                "time_of_day_raw": day_raw,
                "time_of_day_field_present": None
                if rules is None
                else _present(rules, TIME_OF_DAY),
                "daycycle": {
                    "phase": None,
                    "status": "raw_encoding_unverified" if day_raw is not None else "missing_raw",
                    "fixed_cycle_seconds_assumed": None,
                },
                "visibility_sources": {label: _identity(entity) for label, entity in teams.items()},
                "heroes": heroes,
                "missing_player_ids": missing,
            }
        )

    def result(self):
        clock, end = self.parser.game_clock, self.parser.post_game_tick
        frames, seen = [], set()
        skipped = Counter(self.skipped)
        for original in self.frames:
            if original["tick"] > end:
                skipped["post_game_frames"] += 1
                continue
            value = clock.game_time_at(original["tick"])
            if not _finite(value):
                skipped["missing_final_clock_frames"] += 1
                continue
            second = math.floor(value)
            if original["t"] is None:
                skipped["initial_clock_unknown_candidates"] += 1
            else:
                skipped["final_clock_bucket_changes"] += second != original["t"]
            if second in seen:
                skipped["duplicate_final_seconds"] += 1
                continue
            if frames and second <= frames[-1]["t"]:
                raise ValueError("Non-monotonic final visibility clock")
            seen.add(second)
            frames.append({**original, "t": second, "game_time": value})
        end_time = clock.game_time_at(end)
        end_second = math.floor(end_time) if _finite(end_time) else None
        missing = (
            [second for second in range(max(0, end_second + 1)) if second not in seen]
            if end_second is not None
            else None
        )
        return {
            "frames": frames,
            "field_schemas": self.field_schemas,
            "sampling": {
                "boundary": "before_current_tick_entity_deltas",
                "interval": "first candidate per floor(final exact pause-aware game_time)",
                "candidate_interval_replay_ticks": 15,
                "candidate_extra_trigger": "live game-second change, never a reserved bucket",
                "candidate_frames": len(self.frames),
                "clock": "Gem.GameClock.game_time_at(raw_replay_tick)",
                "game_start_time_s": clock.game_start_time_s,
                "net_tick_offset": clock.net_tick_offset,
                "end_game_time": end_time if _finite(end_time) else None,
                "end_second": end_second,
                "pre_game_frames": sum(frame["t"] < 0 for frame in frames),
                "game_frames": sum(frame["t"] >= 0 for frame in frames),
                "missing_game_seconds": missing,
                "skipped": dict(skipped),
            },
            "visibility_encoding": {
                "source": "team m_bNPCVisibleState 64-bit words",
                "word": "entity_index >> 6",
                "bit": "entity_index & 63",
                "vismask": "bit 0=Radiant, bit 1=Dire; null if either team word unknown",
                "tagged_as_visible_by_team": "raw field only; not used to decode visibility",
            },
            "daycycle_evidence": {
                "raw_field": TIME_OF_DAY,
                "phase_decoder": None,
                "status": "encoding_not_verified",
                "fixed_schedule_assumed": False,
                "current_range_inferred_from_base_ranges": False,
            },
        }


def capture(path):
    """Completely parse a caller-verified demo; do not accept partial identity or end."""
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser

    parser = ReplayParser(str(path))
    players = PlayerExtractor()
    players.attach(parser)
    collector = VisibilityCollector(parser, players)
    parser.on_tick_start(collector.on_tick_start)
    parser.parse()
    if parser.parse_error is not None or parser.truncated_at_tick is not None:
        raise ValueError("Incomplete map visibility parse")
    if any(type(value) is not int or value <= 0 for value in (parser.match_id, parser.game_build)):
        raise ValueError("Map visibility parse lacks match/build identity")
    if type(parser.post_game_tick) is not int or parser.post_game_tick < 0:
        raise ValueError("Map visibility parse lacks post-game marker")
    return {
        "schema": "map-visibility-capture/1",
        "coordinate_space": "world",
        "coordinate_formula": "cell*128+vec-16384",
        "match_id": parser.match_id,
        "game_build": parser.game_build,
        "post_game_tick": parser.post_game_tick,
        "parse_error": None,
        "truncated_at_tick": None,
        **collector.result(),
        "evidence_use": "retrospective_omniscient_diagnostic_only",
        "action_review_allowed": False,
        "training_allowed": False,
        "limits": [
            "Base day/night ranges do not establish modifier-adjusted current sight range.",
            "Raw time-of-day encoding is not decoded and no fixed day/night schedule is assumed.",
            "Team target visibility does not identify a particular observing hero or sight source.",
            "Pre-tick snapshots are sampled observations, not continuous or player-available data.",
        ],
    }
