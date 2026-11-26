"""Pure replay admission checks and bounded per-second quality summaries."""

import math
from collections import Counter

QUALITY_SCHEMA = "replay-quality/1"
CORE_HERO = ("hp", "max_hp", "mana", "max_mana", "level", "pos")


def inspect_base(normalized, parser, meta):
    errors = []
    mid, duration = meta["match_id"], meta["duration"]
    if any(
        type(value.get("match_id")) is not int or value["match_id"] != mid
        for value in (normalized, parser)
    ):
        errors.append("match_identity_mismatch")
    if type(parser.get("game_build")) is not int or parser["game_build"] <= 0:
        errors.append("missing_observed_build")
    if parser.get("parse_error") is not None or parser.get("truncated_at_tick") is not None:
        errors.append("parser_incomplete")
    start, end = parser.get("game_start_tick"), parser.get("post_game_tick")
    if type(start) is not int or type(end) is not int or end <= start:
        errors.append("missing_game_end")
    actual = normalized.get("players") or []
    expected = {p["player_slot"]: p["hero_id"] for p in meta["players"]}
    if (
        not isinstance(actual, list)
        or len(actual) != 10
        or any(
            not isinstance(p, dict)
            or type(p.get("player_slot")) is not int
            or type(p.get("hero_id")) is not int
            or p["hero_id"] <= 0
            for p in actual
        )
        or {p.get("player_slot"): p.get("hero_id") for p in actual} != expected
    ):
        errors.append("hero_identity_mismatch")
    if type(normalized.get("duration")) is not int or normalized["duration"] != duration:
        errors.append("normalized_duration_disagreement")
    post_seconds = parser.get("post_game_seconds")
    if (
        type(post_seconds) not in (int, float)
        or not math.isfinite(post_seconds)
        or abs(post_seconds - duration) > 2
    ):
        errors.append("end_time_disagreement")
    context = normalized.get("context")
    channels = context.get("channels") if isinstance(context, dict) else None
    channels = channels if isinstance(channels, dict) else {}
    for name in (
        "coach_state_snapshots",
        "combat_log",
        "hero_visibility_events",
        "entity_visibility_events",
        "wards",
    ):
        value = channels.get(name)
        if not isinstance(value, list):
            errors.append("missing_channel:" + name)
        elif name in ("coach_state_snapshots", "combat_log") and not value:
            errors.append("empty_channel:" + name)
    return {
        "errors": errors,
        "channels": {
            key: len(value) if isinstance(value, list) else None for key, value in channels.items()
        },
        "normalized_duration": normalized.get("duration"),
        "metadata_duration": duration,
        "post_game_seconds": post_seconds,
        "observed_build": parser.get("game_build"),
    }


class ChannelAudit:
    """One streaming pass, with counters rather than all rows retained in memory."""

    def __init__(self, kind, duration):
        if (
            kind not in ("state", "extras")
            or type(duration) is not int
            or not 0 < duration <= 24 * 3600
        ):
            raise ValueError("Unsupported channel or duration")
        self.kind, self.duration = kind, duration
        self.total, self.in_game, self.outside, self.full = 0, 0, 0, 0
        self.previous, self.expected_next = None, 0
        self.errors, self.missing, self.observations = set(), Counter(), Counter()

    def _measure(self, key, value):
        self.observations[key] += 1
        self.missing[key] += value is None
        if value is not None and key.startswith(("ability.", "item.")):
            if key.endswith(".name"):
                valid = isinstance(value, str) and bool(value.strip())
            else:
                valid = type(value) in (int, float) and math.isfinite(value)
            if not valid:
                self.errors.add("invalid_core_field:" + key)

    def accept(self, row):
        if not isinstance(row, dict):
            raise ValueError("Channel row must be an object")
        t = row.get("t")
        if type(t) is not int or (self.previous is not None and t <= self.previous):
            raise ValueError("Channel seconds must be strictly increasing integers")
        self.previous = t
        self.total += 1
        if not 0 <= t <= self.duration:
            self.outside += 1
            return False
        if t != self.expected_next:
            self.errors.add("missing_in_game_seconds")
        self.expected_next = t + 1
        self.in_game += 1
        if self.kind == "state":
            heroes = row.get("heroes")
            if not isinstance(heroes, list):
                raise ValueError("Missing state heroes")
            if any(not isinstance(hero, dict) for hero in heroes):
                raise ValueError("Invalid hero record")
            ids = [hero.get("player_id") for hero in heroes]
            if (
                any(type(pid) is not int for pid in ids)
                or set(ids) != set(range(10))
                or len(ids) != 10
            ):
                self.errors.add("incomplete_hero_frame")
            else:
                self.full += 1
            for hero in heroes:
                for key in CORE_HERO:
                    self._measure("hero." + key, hero.get(key))
                    value = hero.get(key)
                    if value is not None:
                        values = value if key == "pos" and isinstance(value, list) else [value]
                        if (
                            key == "pos" and (not isinstance(value, list) or len(value) != 2)
                        ) or any(
                            type(v) not in (int, float) or not math.isfinite(v) for v in values
                        ):
                            self.errors.add("invalid_core_field:hero." + key)
                abilities, items = hero.get("abilities"), hero.get("items")
                if not isinstance(abilities, list) or not isinstance(items, dict):
                    raise ValueError("Missing ability/item containers")
                for ability in abilities:
                    if not isinstance(ability, dict):
                        raise ValueError("Invalid ability record")
                    if not str(ability.get("name", "")).startswith("special_bonus_"):
                        for key in ("name", "cd", "cd_len"):
                            self._measure("ability." + key, ability.get(key))
                for item in items.values():
                    if not isinstance(item, dict):
                        raise ValueError("Invalid item record")
                    for key in ("name", "cd", "cd_len"):
                        self._measure("item." + key, item.get(key))
        else:
            for key in ("creeps", "watchers", "outposts"):
                if not isinstance(row.get(key), list):
                    self.errors.add("missing_" + key)
            if not isinstance(row.get("scan"), dict):
                self.errors.add("missing_scan")
        return True

    def finish(self):
        if self.in_game != self.duration + 1 or self.expected_next != self.duration + 1:
            self.errors.add("missing_in_game_seconds")
        if self.kind == "state":
            for key in (
                *("hero." + key for key in CORE_HERO),
                "ability.name",
                "ability.cd",
                "ability.cd_len",
                "item.name",
                "item.cd",
                "item.cd_len",
            ):
                if self.observations[key] == 0 or self.missing[key]:
                    self.errors.add("missing_core_field:" + key)
        return {
            "kind": self.kind,
            "total_rows": self.total,
            "in_game_rows": self.in_game,
            "excluded_rows": self.outside,
            "ten_hero_rows": self.full,
            "errors": sorted(self.errors),
            "field_observations": dict(self.observations),
            "field_missing": dict(self.missing),
            "limits": "Coverage checks do not establish field semantics or map/model validity",
        }


def quality_result(base, state, extras):
    errors = [*base["errors"], *state["errors"], *extras["errors"]]
    return {
        "schema": QUALITY_SCHEMA,
        "status": "passed" if not errors else "review_required",
        "errors": errors,
        "base": base,
        "state": state,
        "extras": extras,
        "policy": (
            "exact ID/heroes; observed end/build; complete 0..duration state/extras; "
            "core nulls require review"
        ),
        "training_allowed": False,
    }
