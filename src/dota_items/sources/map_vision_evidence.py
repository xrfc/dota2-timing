"""Replay-native NPC, tree and team visibility evidence at completed packets.

This independent collector intentionally does not import or change earlier frozen
captures. Raw state tables are interned to avoid repeating stationary entities and
tree bitsets. No range, day/night schedule, ward lifetime or tree-ID map is inferred.
"""

import math
import re
from collections import Counter

from dota_items.sources.replay_identity import entity_evidence

STATE_FIELDS = {
    "team": "m_iTeamNum",
    "life_state": "m_lifeState",
    "health": "m_iHealth",
    "waiting_to_spawn": "m_bIsWaitingToSpawn",
    "day_vision_range": "m_iDayTimeVisionRange",
    "night_vision_range": "m_iNightTimeVisionRange",
    "current_vision_range": "m_iCurrentVisionRange",
    "fow_team": "m_nFoWTeam",
    "owner_handle": "m_hOwnerEntity",
    "unit_state_raw": "m_nUnitState64",
}
STATE_COLUMNS = ["entity_id", "x", "y", "active", *STATE_FIELDS]
TEAM_CLASSES = {
    "CDOTA_DataRadiant": "radiant",
    "CDOTADataRadiant": "radiant",
    "CDOTA_DataDire": "dire",
    "CDOTADataDire": "dire",
    "CDOTA_DataSpectator": "spectator",
    "CDOTADataSpectator": "spectator",
    "CDOTA_DataCustomTeam": "custom",
}
RULE_PATTERN = re.compile("vision|fow|day|night", re.I)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _raw(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else None
    if isinstance(value, (tuple, list)):
        return [_raw(item) for item in value]
    return None


def _walk(serializer, prefix="", depth=0):
    if serializer is None or depth > 5:
        return
    for field in serializer.fields:
        name = prefix + field.var_name
        yield name, field
        if field.serializer is not None and field.model == 2:
            yield from _walk(field.serializer, name + ".", depth + 1)


def _meta(field):
    return {
        key: getattr(field, key)
        for key in (
            "var_type",
            "encoder",
            "encode_flags",
            "bit_count",
            "low_value",
            "high_value",
            "model",
        )
    }


def _table(entity, name, field):
    """Preserve a networked vector's count and immediate fields without interpreting them."""
    count = entity.get(name)
    if type(count) is not int or count < 0:
        return {"length": _raw(count), "rows": None}
    if count > 4096:
        raise ValueError("Vision evidence vector exceeds explicit capture bound")
    children = field.serializer.fields if field.serializer is not None else []
    return {
        "length": count,
        "rows": [
            {
                child.var_name: _raw(entity.get(f"{name}.{index:04d}.{child.var_name}"))
                for child in children
            }
            for index in range(count)
        ],
    }


class _Pool:
    def __init__(self):
        self.rows, self.ids = [], {}

    def add(self, row):
        key = tuple(tuple(x) if isinstance(x, list) else x for x in row)
        if key not in self.ids:
            self.ids[key] = len(self.rows)
            self.rows.append(row)
        return self.ids[key]


class VisionEvidenceCollector:
    def __init__(self, parser, players, entity_op):
        self.parser, self.players, self.entity_op = parser, players, entity_op
        self.catalog, self.identities, self.schemas = [], {}, {}
        self.fields, self.live, self.teams = {}, {}, {}
        self.states, self.words, self.tree_words = _Pool(), _Pool(), _Pool()
        self.frames, self.temp_tree_events = [], []
        self.last_tick, self.last_live_second = None, None
        self.skipped = Counter()

    def _catalogue(self, entity):
        identity = entity.get_index(), entity.get_serial()
        if identity not in self.identities:
            index = len(self.catalog)
            self.identities[identity] = index
            table = self.parser.string_tables.get_by_name("UnitNames")
            name_index = entity.get_int32("m_iUnitNameStringTableIndex")
            item = (
                table.items.get(name_index)
                if table is not None and type(name_index) is int
                else None
            )
            self.catalog.append(
                {
                    "entity_index": identity[0],
                    "entity_serial": identity[1],
                    "class_name": entity.get_class_name(),
                    "first_seen_tick": self.parser.tick,
                    "npc_name_first_seen": item[0] if item and isinstance(item[0], str) else None,
                    "npc_name_table": "UnitNames",
                    "npc_name_index_first_seen": name_index,
                }
            )
        return self.identities[identity]

    def _discover(self, entity):
        cls = entity.get_class_name()
        if cls in self.fields:
            return
        fields = dict(_walk(getattr(entity.cls, "serializer", None)))
        self.fields[cls] = fields
        relevant = {
            name: _meta(field)
            for name, field in fields.items()
            if RULE_PATTERN.search(name) or "tree" in name.lower()
        }
        self.schemas[cls] = {
            "state_fields_present": {name: name in fields for name in STATE_FIELDS.values()},
            "relevant_fields": relevant,
            "is_networked_npc_schema": "m_iDayTimeVisionRange" in fields,
        }

    def _state(self, entity):
        identity = self._catalogue(entity)
        row = entity_evidence(entity)
        valid = all(
            type(row[f"cell_{axis}"]) is int
            and row[f"cell_{axis}"] >= 0
            and _finite(row[f"vec_{axis}"])
            for axis in ("x", "y")
        )
        position = (
            [row[f"cell_{a}"] * 128 + row[f"vec_{a}"] - 16384 for a in ("x", "y")]
            if valid
            else [None, None]
        )
        return self.states.add(
            [
                identity,
                *position,
                bool(entity.active),
                *(_raw(entity.get(name)) for name in STATE_FIELDS.values()),
            ]
        )

    def on_entity(self, entity, op):
        parser, cls = self.parser, entity.get_class_name()
        if parser.post_game_tick is not None and parser.tick > parser.post_game_tick:
            return
        self._discover(entity)
        npc = self.schemas[cls]["is_networked_npc_schema"]
        temporary = cls == "CDOTA_TempTree"
        team = TEAM_CLASSES.get(cls)
        if not (npc or temporary or team):
            return
        identity = self._catalogue(entity)
        terminal = op.has(self.entity_op.DELETED | self.entity_op.LEFT)
        if team:
            key = f"custom:{entity.get_index()}:{entity.get_serial()}" if team == "custom" else team
            if terminal:
                if self.teams.get(key) is entity:
                    self.teams.pop(key, None)
            else:
                self.teams[key] = entity
        else:
            if terminal or not entity.active:
                self.live.pop(identity, None)
            else:
                self.live[identity] = entity
        if temporary and op.has(
            self.entity_op.CREATED
            | self.entity_op.ENTERED
            | self.entity_op.DELETED
            | self.entity_op.LEFT
        ):
            self.temp_tree_events.append(
                {
                    "tick": parser.tick,
                    "entity_id": identity,
                    "operation_raw": int(op),
                    "state_id": self._state(entity),
                }
            )

    def on_packet_end(self, _tick):
        parser, tick = self.parser, self.parser.tick
        if parser.post_game_tick is not None and tick > parser.post_game_tick:
            self.skipped["post_game_packets"] += 1
            return
        if parser.entity_manager is None:
            return
        time = parser.game_clock.game_time_at(tick)
        second = math.floor(time) if _finite(time) else None
        if (
            self.last_tick is not None
            and tick - self.last_tick < 15
            and second == self.last_live_second
        ):
            return
        self.last_tick, self.last_live_second = tick, second
        state_ids = [self._state(entity) for _, entity in sorted(self.live.items())]
        canonical = []
        for player_id in range(10):
            hero = self.players._canonical_hero_entity(player_id)
            if hero is not None:
                canonical.append(
                    [
                        player_id,
                        self._catalogue(hero),
                        self.players._hero_handle_for_player(player_id),
                    ]
                )
        indices = {self.catalog[self.states.rows[s][0]]["entity_index"] >> 6 for s in state_ids}
        words, trees, replacements = {}, {}, {}
        for label, entity in sorted(self.teams.items()):
            identity = self._catalogue(entity)
            if label in ("radiant", "dire"):
                data = [
                    [index, _raw(entity.get(f"m_bNPCVisibleState.{index:04d}"))]
                    for index in sorted(indices)
                ]
                words[label] = {"entity_id": identity, "snapshot_id": self.words.add(data)}
            fields = self.fields[entity.get_class_name()]
            tree_field = fields.get("m_bWorldTreeState")
            if tree_field is not None:
                count = tree_field.field_type.count
                if type(count) is not int or not 0 < count <= 4096:
                    raise ValueError("Invalid world-tree word count")
                data = [_raw(entity.get(f"m_bWorldTreeState.{i:04d}")) for i in range(count)]
                trees[label] = {"entity_id": identity, "snapshot_id": self.tree_words.add(data)}
            replacement = fields.get("m_vecWorldTreeModelReplacements")
            if replacement is not None:
                replacements[label] = _table(entity, "m_vecWorldTreeModelReplacements", replacement)
        rules = parser.entity_manager.find_by_class_name("CDOTAGamerulesProxy")
        rule_values = {}
        if rules is not None:
            self._discover(rules)
            for name, field in self.fields[rules.get_class_name()].items():
                if RULE_PATTERN.search(name):
                    rule_values[name] = (
                        _table(rules, name, field) if field.model == 4 else _raw(rules.get(name))
                    )
        self.frames.append(
            {
                "tick": tick,
                "live_game_time": time if _finite(time) else None,
                "entity_state_ids": state_ids,
                "canonical_heroes": canonical,
                "team_word_refs": words,
                "tree_word_refs": trees,
                "tree_model_replacements_raw": replacements,
                "rules_raw": rule_values,
            }
        )

    def result(self):
        clock, end = self.parser.game_clock, self.parser.post_game_tick
        frames, seconds = [], set()
        skipped = Counter(self.skipped)
        for frame in self.frames:
            time = clock.game_time_at(frame["tick"])
            if frame["tick"] > end or not _finite(time):
                skipped["outside_end_or_unknown_clock_candidates"] += 1
                continue
            second = math.floor(time)
            if second in seconds:
                skipped["duplicate_final_seconds"] += 1
                continue
            if frames and second <= frames[-1]["t"]:
                raise ValueError("Vision evidence final clock is not monotonic")
            seconds.add(second)
            frames.append({**frame, "t": second, "game_time": time})
        events = [
            {**event, "game_time": _raw(clock.game_time_at(event["tick"]))}
            for event in self.temp_tree_events
            if event["tick"] <= end
        ]
        # Only states referenced by retained samples/events survive; no discarded
        # candidate or future state is exposed through an otherwise unused pool.
        state_ids = {sid for frame in frames for sid in frame["entity_state_ids"]}
        state_ids.update(event["state_id"] for event in events)
        state_map = {old: new for new, old in enumerate(sorted(state_ids))}
        states = [list(self.states.rows[old]) for old in sorted(state_ids)]
        entity_ids = {row[0] for row in states}
        for frame in frames:
            entity_ids.update(item[1] for item in frame["canonical_heroes"])
            for key in ("team_word_refs", "tree_word_refs"):
                entity_ids.update(item["entity_id"] for item in frame[key].values())
        entity_map = {old: new for new, old in enumerate(sorted(entity_ids))}
        for row in states:
            row[0] = entity_map[row[0]]
        pools = {}
        for key, pool in (("team_word_refs", self.words), ("tree_word_refs", self.tree_words)):
            ids = sorted({item["snapshot_id"] for frame in frames for item in frame[key].values()})
            mapping = {old: new for new, old in enumerate(ids)}
            pools[key] = [pool.rows[old] for old in ids]
            for frame in frames:
                frame[key] = {
                    label: {
                        "entity_id": entity_map[item["entity_id"]],
                        "snapshot_id": mapping[item["snapshot_id"]],
                    }
                    for label, item in frame[key].items()
                }
        for frame in frames:
            frame["entity_state_ids"] = [state_map[sid] for sid in frame["entity_state_ids"]]
            frame["canonical_heroes"] = [
                [pid, entity_map[eid], handle] for pid, eid, handle in frame["canonical_heroes"]
            ]
        for event in events:
            event["entity_id"] = entity_map[event["entity_id"]]
            event["state_id"] = state_map[event["state_id"]]
        catalog = [self.catalog[old] for old in sorted(entity_ids)]
        classes = {entity["class_name"] for entity in catalog} | {"CDOTAGamerulesProxy"}
        end_time = clock.game_time_at(end)
        end_second = math.floor(end_time) if _finite(end_time) else None
        return {
            "state_columns": list(STATE_COLUMNS),
            "states": states,
            "entity_catalog": catalog,
            "frames": frames,
            "temporary_tree_events": events,
            "team_word_snapshots": pools["team_word_refs"],
            "tree_word_snapshots": pools["tree_word_refs"],
            "field_schemas": {
                name: schema for name, schema in self.schemas.items() if name in classes
            },
            "sampling": {
                "boundary": "completed_packet",
                "candidate_interval_replay_ticks": 15,
                "extra_candidate_trigger": "live game-second change",
                "final_grouping": "first candidate per floor(final pause-aware game_time)",
                "end_game_time": end_time if _finite(end_time) else None,
                "end_second": end_second,
                "missing_game_seconds": None
                if end_second is None
                else [second for second in range(max(0, end_second + 1)) if second not in seconds],
                "candidate_frames": len(self.frames),
                "skipped": dict(skipped),
                "temporary_tree_boundary": "entity_callback; raw lifecycle operation",
            },
        }


def capture(path):
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser
    from gem.state.entities import EntityOp

    parser, players = ReplayParser(str(path)), PlayerExtractor()
    players.attach(parser)
    collector = VisionEvidenceCollector(parser, players, EntityOp)
    parser.on_entity(collector.on_entity)
    parser._on_packet_end(collector.on_packet_end)
    parser.parse()
    if parser.parse_error is not None or parser.truncated_at_tick is not None:
        raise ValueError("Incomplete map vision evidence parse")
    if any(type(value) is not int or value <= 0 for value in (parser.match_id, parser.game_build)):
        raise ValueError("Map vision evidence lacks real match/build identity")
    if type(parser.post_game_tick) is not int or parser.post_game_tick < 0:
        raise ValueError("Map vision evidence lacks post-game marker")
    return {
        "schema": "map-vision-evidence/1",
        "coordinate_space": "world",
        "coordinate_formula": "cell*128+vec-16384",
        "match_id": parser.match_id,
        "game_build": parser.game_build,
        "post_game_tick": parser.post_game_tick,
        "parse_error": None,
        "truncated_at_tick": None,
        **collector.result(),
        "evidence_use": "retrospective_omniscient_diagnostic_only",
        "training_allowed": False,
        "action_review_allowed": False,
        "limits": [
            "Base ranges and unit-state bits do not certify effective current vision radius.",
            "Day/night raw thresholds do not establish NetTimeOfDay integer normalization.",
            "Tree words retain observer channel identity; bit meaning and spatial ID map unknown.",
            "NPC schema membership does not establish that an entity supplies player vision.",
            "Recorded target visibility does not identify a sight source or full coordinate FOW.",
            "One sample per second cannot describe every within-second visibility transition.",
        ],
    }
