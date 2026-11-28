"""Pure checks and labels for replay-recorded entity visibility, not full map FOW."""

import math
from collections import Counter, defaultdict

STATE_COLUMNS = (
    "entity_id",
    "x",
    "y",
    "active",
    "team",
    "life_state",
    "health",
    "waiting_to_spawn",
    "day_vision_range",
    "night_vision_range",
    "current_vision_range",
    "fow_team",
    "owner_handle",
    "unit_state_raw",
)
COL = {name: index for index, name in enumerate(STATE_COLUMNS)}
TEAM_CLASSES = {
    "radiant": {"CDOTA_DataRadiant", "CDOTADataRadiant"},
    "dire": {"CDOTA_DataDire", "CDOTADataDire"},
    "spectator": {"CDOTA_DataSpectator", "CDOTADataSpectator"},
    "custom": {"CDOTA_DataCustomTeam"},
}
ROLES = {
    "CDOTA_NPC_Observer_Ward": "observer_ward",
    "CDOTA_NPC_Observer_Ward_TrueSight": "sentry_ward",
    "CDOTA_BaseNPC_Tower": "tower",
    "CDOTA_BaseNPC_Barracks": "barracks",
    "CDOTA_BaseNPC_Fort": "fort",
    "CDOTA_Unit_Fountain": "fountain",
    "CDOTA_BaseNPC_Creep_Lane": "lane_creep",
    "CDOTA_BaseNPC_Creep_Siege": "siege_creep",
    "CDOTA_Unit_Courier": "courier",
    "CDOTA_TempTree": "temporary_tree",
    "CDOTA_BaseNPC_Creep_Neutral": "neutral_class_or_controlled_unit",
    "CDOTA_NPC_Lantern": "watcher",
    "CDOTA_BaseNPC_Watch_Tower": "outpost",
}


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _integer(value, lower=0, upper=None):
    return type(value) is int and value >= lower and (upper is None or value < upper)


def _word(value):
    return value is None or _integer(value, upper=2**64)


def _role(entity, canonical=False):
    cls = entity["class_name"]
    if canonical:
        return "canonical_hero"
    if cls.startswith("CDOTA_Unit_Hero_"):
        return "other_hero_entity"
    return ROLES.get(cls, "other_networked_entity_unclassified")


def _raw_value(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return _finite(value)
    if isinstance(value, list):
        return all(_raw_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _raw_value(item) for key, item in value.items())
    return False


def _validate(capture):
    if (
        not isinstance(capture, dict)
        or capture.get("schema") != "map-vision-evidence/1"
        or capture.get("coordinate_space") != "world"
        or not all(_integer(capture.get(k), 1) for k in ("match_id", "game_build"))
        or not _integer(capture.get("post_game_tick"))
        or capture.get("parse_error") is not None
        or capture.get("truncated_at_tick") is not None
        or capture.get("state_columns") != list(STATE_COLUMNS)
        or not isinstance(capture.get("sampling"), dict)
        or capture["sampling"].get("boundary") != "completed_packet"
    ):
        raise ValueError("Complete world-coordinate completed-packet vision evidence required")
    for name in (
        "entity_catalog",
        "states",
        "frames",
        "team_word_snapshots",
        "tree_word_snapshots",
        "temporary_tree_events",
    ):
        if not isinstance(capture.get(name), list):
            raise ValueError("Vision evidence tables must be lists")
    catalog, states = capture["entity_catalog"], capture["states"]
    identities = set()
    for entity in catalog:
        if not isinstance(entity, dict):
            raise ValueError("Invalid entity catalog row")
        index, serial = entity.get("entity_index"), entity.get("entity_serial")
        if (
            not _integer(index, upper=16384)
            or not _integer(serial)
            or (index, serial) in identities
            or not isinstance(entity.get("class_name"), str)
            or not _integer(entity.get("first_seen_tick"), upper=capture["post_game_tick"] + 1)
        ):
            raise ValueError("Invalid, duplicate or future entity identity")
        identities.add((index, serial))
    for row in states:
        if not isinstance(row, list) or len(row) != len(STATE_COLUMNS):
            raise ValueError("Invalid entity state shape")
        if not _integer(row[0], upper=len(catalog)) or type(row[3]) is not bool:
            raise ValueError("Invalid state identity or activity flag")
        x, y = row[1:3]
        if not ((x is y is None) or (_finite(x) and _finite(y))):
            raise ValueError("Coordinates must be finite or jointly unknown")
        for key in ("team", "life_state", "fow_team", "owner_handle", "unit_state_raw"):
            value = row[COL[key]]
            if value is not None and not _integer(value):
                raise ValueError("Invalid raw integer state field")
        for key in ("health", "day_vision_range", "night_vision_range", "current_vision_range"):
            value = row[COL[key]]
            if value is not None and (not _finite(value) or value < 0):
                raise ValueError("Invalid health or vision range")
        if (
            row[COL["waiting_to_spawn"]] is not None
            and type(row[COL["waiting_to_spawn"]]) is not bool
        ):
            raise ValueError("Invalid raw waiting-to-spawn flag")
    for words in capture["team_word_snapshots"]:
        if not isinstance(words, list):
            raise ValueError("Invalid team word table")
        previous = -1
        for entry in words:
            if (
                not isinstance(entry, list)
                or len(entry) != 2
                or not _integer(entry[0], upper=256)
                or entry[0] <= previous
                or not _word(entry[1])
            ):
                raise ValueError("Invalid or unordered team visibility word")
            previous = entry[0]
    for words in capture["tree_word_snapshots"]:
        if (
            not isinstance(words, list)
            or not 0 < len(words) <= 4096
            or any(not _word(value) for value in words)
        ):
            raise ValueError("Invalid tree word snapshot")
    last_event_tick = -1
    for event in capture["temporary_tree_events"]:
        if (
            not isinstance(event, dict)
            or not _integer(event.get("tick"))
            or not last_event_tick <= event["tick"] <= capture["post_game_tick"]
            or not _integer(event.get("entity_id"), upper=len(catalog))
            or not _integer(event.get("state_id"), upper=len(states))
            or not _integer(event.get("operation_raw"), 1, 32)
            or not event["operation_raw"] & (1 | 4 | 8 | 16)
            or states[event["state_id"]][0] != event["entity_id"]
            or catalog[event["entity_id"]]["class_name"] != "CDOTA_TempTree"
            or catalog[event["entity_id"]]["first_seen_tick"] > event["tick"]
            or (event.get("game_time") is not None and not _finite(event["game_time"]))
        ):
            raise ValueError("Invalid temporary tree lifecycle evidence")
        last_event_tick = event["tick"]
    return catalog, states


def _views(capture):
    catalog, states = _validate(capture)
    previous_second, previous_tick = None, None
    end_time = capture["sampling"].get("end_game_time")
    if end_time is not None and not _finite(end_time):
        raise ValueError("Invalid final game time")
    for frame in capture["frames"]:
        if (
            not isinstance(frame, dict)
            or type(frame.get("t")) is not int
            or not _integer(frame.get("tick"), upper=capture["post_game_tick"] + 1)
            or not _finite(frame.get("game_time"))
            or math.floor(frame["game_time"]) != frame["t"]
            or (end_time is not None and frame["game_time"] > end_time)
        ):
            raise ValueError("Invalid, future or inconsistent vision frame time")
        if previous_second is not None and (
            frame["t"] <= previous_second or frame["tick"] <= previous_tick
        ):
            raise ValueError("Duplicate or unordered vision frames")
        previous_second, previous_tick = frame["t"], frame["tick"]
        for name in ("entity_state_ids", "canonical_heroes"):
            if not isinstance(frame.get(name), list):
                raise ValueError("Missing frame state or canonical hero table")
        for name in ("rules_raw", "tree_model_replacements_raw"):
            if not isinstance(frame.get(name), dict) or not _raw_value(frame[name]):
                raise ValueError("Invalid raw rules or tree replacement evidence")
        selected = {}
        for state_id in frame["entity_state_ids"]:
            if not _integer(state_id, upper=len(states)):
                raise ValueError("Unknown entity state reference")
            row = states[state_id]
            if (
                row[0] in selected
                or not row[3]
                or catalog[row[0]]["first_seen_tick"] > frame["tick"]
            ):
                raise ValueError("Duplicate, inactive or future frame entity")
            selected[row[0]] = row
        canonical, seen_entities = {}, set()
        for entry in frame["canonical_heroes"]:
            if not isinstance(entry, list) or len(entry) != 3:
                raise ValueError("Invalid canonical hero reference")
            pid, entity_id, handle = entry
            if (
                not _integer(pid, upper=10)
                or pid in canonical
                or not _integer(entity_id, upper=len(catalog))
                or entity_id in seen_entities
                or not _integer(handle)
                or not catalog[entity_id]["class_name"].startswith("CDOTA_Unit_Hero_")
                or catalog[entity_id]["first_seen_tick"] > frame["tick"]
            ):
                raise ValueError("Invalid or duplicate canonical hero identity")
            entity = catalog[entity_id]
            if handle & 16383 != entity["entity_index"] or handle >> 14 != entity["entity_serial"]:
                raise ValueError("Canonical hero handle does not bind index and serial")
            canonical[pid] = entity_id
            seen_entities.add(entity_id)
        team_words, tree_words = {}, {}
        for key, pool, destination in (
            ("team_word_refs", capture["team_word_snapshots"], team_words),
            ("tree_word_refs", capture["tree_word_snapshots"], tree_words),
        ):
            refs = frame.get(key)
            if not isinstance(refs, dict):
                raise ValueError("Missing observer-channel references")
            for label, ref in refs.items():
                role = label.split(":", 1)[0] if isinstance(label, str) else None
                if (
                    not isinstance(ref, dict)
                    or role not in TEAM_CLASSES
                    or (key == "team_word_refs" and role not in ("radiant", "dire"))
                    or (role != "custom" and label != role)
                    or not _integer(ref.get("entity_id"), upper=len(catalog))
                    or not _integer(ref.get("snapshot_id"), upper=len(pool))
                    or catalog[ref["entity_id"]]["class_name"] not in TEAM_CLASSES[role]
                    or catalog[ref["entity_id"]]["first_seen_tick"] > frame["tick"]
                ):
                    raise ValueError(
                        "Invalid visibility/tree channel identity or snapshot reference"
                    )
                entity = catalog[ref["entity_id"]]
                if role == "custom" and label != (
                    f"custom:{entity['entity_index']}:{entity['entity_serial']}"
                ):
                    raise ValueError("Custom tree channel must retain exact entity identity")
                destination[label] = pool[ref["snapshot_id"]]
        yield (
            frame,
            selected,
            canonical,
            {key: dict(rows) for key, rows in team_words.items()},
            tree_words,
        )


def _visible(entity, row, words):
    # Temporary trees are captured for lifecycle/geometry evidence, but the
    # NPC visibility array does not establish that a non-NPC tree uses its bit.
    if row is None or row[3] is not True or entity["class_name"] == "CDOTA_TempTree":
        return None
    index = entity["entity_index"]
    word = words.get(index >> 6)
    return bool(word & (1 << (index & 63))) if word is not None else None


def iter_hero_visibility_labels(capture, *, include_pre_game=False):
    """Yield observed target labels only; no position-grid FOW or sight-source inference.

    Consumers must exhaust the iterator so malformed later evidence is rejected.
    Missing target state or observer word stays unknown; no visibility is carried
    between seconds or beyond the observed entity identity.
    """
    if type(include_pre_game) is not bool:
        raise ValueError("include_pre_game must be an explicit boolean")
    catalog = capture.get("entity_catalog", []) if isinstance(capture, dict) else []
    for frame, selected, canonical, words, _ in _views(capture):
        if frame["t"] < 0 and not include_pre_game:
            continue
        for pid, entity_id in sorted(canonical.items()):
            entity = catalog[entity_id]
            for label, team in (("radiant", 2), ("dire", 3)):
                yield {
                    "t": frame["t"],
                    "tick": frame["tick"],
                    "player_id": pid,
                    "entity_index": entity["entity_index"],
                    "entity_serial": entity["entity_serial"],
                    "observer_team": team,
                    "visible": _visible(entity, selected.get(entity_id), words.get(label, {})),
                    "scope": "recorded_entity_visibility_at_completed_packet",
                    "sight_source_attributed": False,
                    "coordinate_fow_inferred": False,
                }


def analyze_vision_evidence(capture, *, expected_duration=None):
    """Summarize measured coverage and explicit limits without creating gameplay rules."""
    if expected_duration is not None and not _integer(expected_duration):
        raise ValueError("Expected duration must be a nonnegative integer")
    counts = Counter(
        {
            "game_frames": 0,
            "pre_game_frames": 0,
            "canonical_hero_samples": 0,
            "missing_player_samples": 0,
            "canonical_hero_state_missing": 0,
            "recorded_hero_team_labels_known": 0,
            "recorded_hero_team_labels_unknown": 0,
            "tree_channel_samples": 0,
            "tree_words_observed": 0,
            "tree_words_unknown": 0,
        }
    )
    roles, ranges, rule_values = defaultdict(Counter), defaultdict(Counter), {}
    tree_changes, tree_bit_changes, previous_trees = Counter(), Counter(), {}
    known_seconds = set()
    catalog = capture.get("entity_catalog", []) if isinstance(capture, dict) else []
    for frame, selected, canonical, words, trees in _views(capture):
        if frame["t"] < 0:
            counts["pre_game_frames"] += 1
            continue
        counts["game_frames"] += 1
        known_seconds.add(frame["t"])
        counts["canonical_hero_samples"] += len(canonical)
        counts["missing_player_samples"] += 10 - len(canonical)
        canonical_ids = set(canonical.values())
        for entity_id, row in selected.items():
            role = _role(catalog[entity_id], entity_id in canonical_ids)
            stats = roles[role]
            stats["samples"] += 1
            stats["world_position_known"] += row[1] is not None
            stats["raw_waiting_to_spawn_true"] += row[COL["waiting_to_spawn"]] is True
            for key in ("day_vision_range", "night_vision_range", "current_vision_range"):
                value = row[COL[key]]
                stats[key + "_known"] += value is not None
                if value is not None:
                    ranges[role + "." + key][str(value)] += 1
            for label in ("radiant", "dire"):
                visible = _visible(catalog[entity_id], row, words.get(label, {}))
                stats[f"recorded_{label}_{visible}"] += 1
        for entity_id in canonical_ids:
            row = selected.get(entity_id)
            counts["canonical_hero_state_missing"] += row is None
            for label in ("radiant", "dire"):
                visible = _visible(catalog[entity_id], row, words.get(label, {}))
                counts[f"hero_{label}_{visible}"] += 1
                counts[
                    "recorded_hero_team_labels_unknown"
                    if visible is None
                    else "recorded_hero_team_labels_known"
                ] += 1
        for label, values in trees.items():
            counts["tree_channel_samples"] += 1
            counts["tree_words_observed"] += len(values)
            counts["tree_words_unknown"] += sum(value is None for value in values)
            if label in previous_trees:
                before = previous_trees[label]
                if len(before) != len(values):
                    raise ValueError("Tree channel word count changed")
                tree_changes[label] += before != values
                tree_bit_changes[label] += sum(
                    (a ^ b).bit_count()
                    for a, b in zip(before, values, strict=True)
                    if a is not None and b is not None
                )
            previous_trees[label] = values
        for name, value in frame.get("rules_raw", {}).items():
            report = rule_values.setdefault(name, {"known": 0, "missing": 0, "examples": []})
            report["known" if value is not None else "missing"] += 1
            if len(report["examples"]) < 8 and value not in report["examples"]:
                report["examples"].append(value)
    end_time = capture["sampling"].get("end_game_time")
    end_second = math.floor(end_time) if _finite(end_time) else None
    duration = expected_duration if expected_duration is not None else end_second
    missing = (
        None if duration is None else [t for t in range(duration + 1) if t not in known_seconds]
    )
    return {
        "schema": "patch-vision-evidence-analysis/1",
        "match_id": capture["match_id"],
        "counts": dict(counts),
        "timeline": {
            "end_second": end_second,
            "expected_duration": expected_duration,
            "duration_matches_expected": None
            if expected_duration is None
            else end_second == expected_duration,
            "missing_game_seconds": missing,
        },
        "potential_source_categories": {role: dict(stats) for role, stats in sorted(roles.items())},
        "observed_ranges": {key: dict(value) for key, value in sorted(ranges.items())},
        "raw_daynight_and_fow_fields": rule_values,
        "dynamic_trees": {
            "channel_word_changes": dict(tree_changes),
            "channel_raw_bit_flips": dict(tree_bit_changes),
            "temporary_tree_lifecycle_events": len(capture["temporary_tree_events"]),
            "world_tree_index_to_position_verified": False,
            "word_bit_meaning_verified": False,
        },
        "recorded_entity_visibility_labels_available": (
            counts["recorded_hero_team_labels_known"] > 0
        ),
        "labels_scope": "only observed identities, teams and sampled completed packets",
        "current_effective_range_certified": False,
        "daynight_integer_encoding_verified": False,
        "source_attribution_available": False,
        "full_coordinate_fog_of_war_available": False,
        "training_allowed": False,
        "action_review_allowed": False,
        "limits": [
            "Visibility bits record target state; sight attribution and geometric FOW are unknown.",
            "Observer, sentry and other classes with base ranges do not prove active sight.",
            "Unknown current range, flying/modifier semantics and tree mapping are not filled in.",
        ],
    }
