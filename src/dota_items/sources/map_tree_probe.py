"""Independent raw tree/vision probe; no tree-index or bit-plane semantics are inferred.

Run in a fresh process with the caller's verified private Gem copy. Packet ordinals
count Gem completed-packet callbacks, whose inner messages Gem sorts before dispatch;
they are not original demo command or original wire-message ordinals.
"""

import base64
import hashlib
import math
import re
from collections import Counter
from copy import deepcopy

FIELD_PATTERN = re.compile(
    r"tree|world|filename|file_name|resource|vision|sight|fow|fog|viewer|blocker|reveal|day|night",
    re.I,
)
FOCUS_PATTERN = re.compile(r"tree|world|monkeyking", re.I)
FULL_CLASS_PATTERN = re.compile(r"tree|world|fow|fog|viewer|blocker", re.I)
TEAM_CLASSES = {
    "CDOTA_DataRadiant": "radiant",
    "CDOTADataRadiant": "radiant",
    "CDOTA_DataDire": "dire",
    "CDOTADataDire": "dire",
    "CDOTA_DataSpectator": "spectator",
    "CDOTADataSpectator": "spectator",
    "CDOTA_DataCustomTeam": "custom",
}
MAX_ARRAY = 4096
META_KEYS = (
    "var_name",
    "var_type",
    "send_node",
    "serializer_name",
    "serializer_version",
    "encoder",
    "encode_flags",
    "bit_count",
    "low_value",
    "high_value",
    "model",
)


def _full_class(name):
    return (
        bool(FULL_CLASS_PATTERN.search(name))
        and "ability" not in name.lower()
        and "hero" not in name.lower()
    )


def _raw(value):
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else {"unknown": "nonfinite_float"}
    if isinstance(value, (list, tuple)):
        return [_raw(item) for item in value]
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return {"unknown": "unsupported_decoded_type", "type": type(value).__name__}


def _strict_equal(left, right):
    if left is right:
        return True
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _strict_equal(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _is_storage(value):
    return isinstance(value, dict) and value.get("storage_kind") == "Gem.FieldState"


def _storage_index(value):
    rows = value.get("observed_storage_rows")
    if not isinstance(rows, list):
        raise ValueError("Full observed storage rows required by encoder")
    result = {}
    for row in rows:
        index = row.get("index") if isinstance(row, dict) else None
        if type(index) is not int or not 0 <= index < MAX_ARRAY or index in result:
            raise ValueError("Invalid or duplicate observed storage index")
        result[index] = row
    return result


def _encode_storage_field(value, previous, *, base_field_packet_ordinal):
    """Encode only top-level storage rows; an individual changed row stays complete."""
    if not _is_storage(value):
        return deepcopy(value)
    rows = _storage_index(value)
    metadata = {
        key: deepcopy(item) for key, item in value.items() if key != "observed_storage_rows"
    }
    if not _is_storage(previous):
        return {
            **metadata,
            "storage_rows_encoding": "full",
            "base_field_packet_ordinal": None,
            "observed_storage_rows": [deepcopy(rows[index]) for index in sorted(rows)],
        }
    if type(base_field_packet_ordinal) is not int or base_field_packet_ordinal <= 0:
        raise ValueError("Storage delta requires a preceding field observation")
    old_rows = _storage_index(previous)
    return {
        **metadata,
        "storage_rows_encoding": "delta",
        "base_field_packet_ordinal": base_field_packet_ordinal,
        "changed_rows": [
            deepcopy(rows[index])
            for index in sorted(rows)
            if index not in old_rows or not _strict_equal(rows[index], old_rows[index])
        ],
        "removed_storage_indices": sorted(old_rows.keys() - rows.keys()),
    }


def _field_changes(values, previous, previous_packets):
    if previous is not None and previous.keys() - values.keys():
        raise ValueError("Selected field disappeared instead of reporting explicit unknown")
    return {
        name: _encode_storage_field(
            value,
            None if previous is None else previous.get(name),
            base_field_packet_ordinal=previous_packets.get(name),
        )
        for name, value in values.items()
        if previous is None or name not in previous or not _strict_equal(value, previous[name])
    }


def _schema(serializer, ancestors=()):
    if serializer is None:
        return {"fields": [], "unknown": "serializer_absent"}
    if id(serializer) in ancestors or len(ancestors) >= 16:
        return {"fields": [], "unknown": "recursive_or_depth_limited_serializer"}
    fields = []
    for field in serializer.fields:
        item = {key: _raw(getattr(field, key, None)) for key in META_KEYS}
        item["fixed_count"] = getattr(getattr(field, "field_type", None), "count", None)
        if field.serializer is not None:
            item["children"] = _schema(field.serializer, (*ancestors, id(serializer)))
        fields.append(item)
    return {"name": getattr(serializer, "name", None), "fields": fields}


def _selected(serializer, prefix="", ancestors=()):
    if serializer is None or id(serializer) in ancestors or len(ancestors) >= 16:
        return
    for field in serializer.fields:
        path = prefix + field.var_name
        if FIELD_PATTERN.search(path + " " + field.var_type) or "HeroID_t" in field.var_type:
            yield path, field
        elif field.serializer is not None and field.model == 2:
            yield from _selected(field.serializer, path + ".", (*ancestors, id(serializer)))
        elif field.serializer is not None and field.model == 4:
            if (
                next(_selected(field.serializer, "", (*ancestors, id(serializer))), None)
                is not None
            ):
                yield path, field


def _storage_slots(value):
    """Pinned Gem may replace a decoded vector length with an allocated child tree.

    Its capacity is not the vector length; later length writes can leave old
    children intact. Preserve stored indices without claiming current membership.
    No parser implementation or decoded state is modified here.
    """
    cls = type(value)
    if (cls.__module__, cls.__name__) != ("gem.schema.field_state", "FieldState"):
        return None
    slots = getattr(value, "_state", None)
    if not isinstance(slots, list) or len(slots) > MAX_ARRAY * 2:
        raise ValueError("Unsupported Gem field-state storage")
    if any(item is not None for item in slots[MAX_ARRAY:]):
        raise ValueError("Observed vector index exceeds explicit probe bound")
    return len(slots), [(index, item) for index, item in enumerate(slots) if item is not None]


def _value(entity, field, path, depth=0, *, selected_only=False):
    """Read explicit fixed/vector structure, preserving missing count versus empty."""
    if depth >= 16:
        return {"unknown": "nested_value_depth_limit"}
    if FIELD_PATTERN.search(field.var_name + " " + field.var_type) or "HeroID_t" in field.var_type:
        selected_only = False
    if field.model == 2:
        return {
            "presence_raw": _raw(entity.get(path)),
            "fields": {
                child.var_name: _value(entity, child, path + "." + child.var_name, depth + 1)
                for child in field.serializer.fields
            }
            if field.serializer is not None
            else None,
        }
    if field.model not in (1, 3, 4):
        return _raw(entity.get(path))
    count = field.field_type.count if field.model == 1 else entity.get(path)
    storage = _storage_slots(count) if field.model in (3, 4) else None
    if storage is not None:
        capacity, slots = storage
        children = (
            list(_selected(field.serializer))
            if selected_only
            else [(child.var_name, child) for child in field.serializer.fields]
            if field.serializer is not None
            else []
        )
        rows = []
        for index, item in slots:
            row = {"index": index}
            if field.model == 4:
                row["fields_raw"] = {
                    name: _value(
                        entity,
                        child,
                        f"{path}.{index:04d}." + name,
                        depth + 1,
                        selected_only=selected_only,
                    )
                    for name, child in children
                }
                row["stored_value_kind"] = type(item).__name__
            else:
                row["value_raw"] = _raw(entity.get(f"{path}.{index:04d}"))
            rows.append(row)
        result = {
            "length_raw": None,
            "logical_length_known": False,
            "values": None,
            "storage_kind": "Gem.FieldState",
            "allocated_storage_slots": capacity,
            "stored_slots_may_be_stale": True,
            "current_membership_known": False,
            "observed_storage_rows": rows,
        }
        if field.model == 4 and selected_only:
            result["fields_selection"] = "candidate_descendants_only"
        return result
    if type(count) is not int or not 0 <= count <= MAX_ARRAY:
        return {"length_raw": _raw(count), "values": None, "unknown": "missing_or_invalid_count"}
    if field.model == 4:
        children = (
            list(_selected(field.serializer))
            if selected_only
            else [(child.var_name, child) for child in field.serializer.fields]
            if field.serializer is not None
            else []
        )
        values = [
            {
                name: _value(
                    entity, child, f"{path}.{i:04d}." + name, depth + 1, selected_only=selected_only
                )
                for name, child in children
            }
            if field.serializer is not None
            else None
            for i in range(count)
        ]
    else:
        values = [_raw(entity.get(f"{path}.{i:04d}")) for i in range(count)]
    result = {"length_raw": count, "values": values}
    if field.model == 4 and selected_only:
        result["fields_selection"] = "candidate_descendants_only"
    return result


def _position(entity):
    raw, position = {}, {}
    for axis in ("x", "y", "z"):
        cell = entity.get("CBodyComponent.m_cell" + axis.upper())
        vec = entity.get("CBodyComponent.m_vec" + axis.upper())
        raw["cell_" + axis], raw["vec_" + axis] = _raw(cell), _raw(vec)
        valid = type(cell) is int and cell >= 0 and type(vec) in (int, float) and math.isfinite(vec)
        position[axis] = cell * 128 + vec - 16384 if valid else None
    return {"world": position, "raw_components": raw}


def _protobuf(message):
    result = {}
    for descriptor, value in message.ListFields():
        if getattr(descriptor, "is_repeated", False):
            result[descriptor.name] = [
                _protobuf(item) if hasattr(item, "ListFields") else _raw(item) for item in value
            ]
        else:
            result[descriptor.name] = (
                _protobuf(value) if hasattr(value, "ListFields") else _raw(value)
            )
    return result


class TreeProbeCollector:
    """Collect callbacks and changed completed-packet states without sampling seconds."""

    def __init__(self, parser, players, entity_op):
        self.parser, self.players, self.op = parser, players, entity_op
        self.schemas, self.fields, self.live, self.dirty = {}, {}, {}, {}
        self.focus_live, self.previous_packet, self.previous_field_packets = {}, {}, {}
        self.perched_position_ticks = {}
        self.packets, self.entity_changes, self.entity_events = [], [], []
        self.tree_changes, self.raw_events, self.send_tables = [], [], []
        self.previous, self.previous_trees = {}, {}
        self.ordinal, self.dispatch_index = 0, 0
        self.terminal_packet_ordinal = None
        self.cut_packet_ordinals = set()
        self.counts = Counter()

    def _identity(self, entity):
        return {
            "entity_index": entity.get_index(),
            "entity_serial": entity.get_serial(),
            "class_name": entity.get_class_name(),
        }

    def _stamp(self):
        return {"packet_ordinal": self.ordinal + 1, "tick": self.parser.tick}

    def _within_end(self, tick):
        end = self.parser.post_game_tick
        return (end is None or tick <= end) and self.terminal_packet_ordinal is None

    def on_entity(self, entity, operation):
        if not self._within_end(self.parser.tick):
            self.counts["post_game_entity_callbacks"] += 1
            return
        cls = entity.get_class_name()
        if cls not in self.schemas:
            serializer = getattr(entity.cls, "serializer", None)
            self.schemas[cls] = _schema(serializer)
            self.fields[cls] = (
                {field.var_name: field for field in serializer.fields}
                if serializer is not None and _full_class(cls)
                else dict(_selected(serializer))
            )
        focus = bool(FOCUS_PATTERN.search(cls))
        if not self.fields[cls] and not focus:
            return
        key = entity.get_index(), entity.get_serial()
        terminal = operation.has(self.op.DELETED | self.op.LEFT)
        if focus and operation.has(
            self.op.CREATED | self.op.ENTERED | self.op.DELETED | self.op.LEFT
        ):
            self.entity_events.append(
                {
                    **self._stamp(),
                    **self._identity(entity),
                    "operation_raw": int(operation),
                    "active_raw": bool(entity.active),
                    "position": _position(entity),
                    "boundary": "entity_callback_before_completed_packet",
                }
            )
        self.dirty[key] = (entity, terminal)
        if terminal:
            self.live.pop(key, None)
            self.focus_live.pop(key, None)
        else:
            self.live[key] = entity
            if focus:
                self.focus_live[key] = entity

    def raw_combat(self, message, source, *, original_payload=None):
        if not self._within_end(self.parser.tick):
            self.counts["post_game_raw_combat_messages"] += 1
            return
        fields = _protobuf(message)
        self.counts["raw_s2_combat_messages"] += 1
        if fields.get("type") != 35:
            return
        self.cut_packet_ordinals.add(self.ordinal + 1)
        names = self.parser.string_tables.get_by_name("CombatLogNames")
        resolved = {}
        for key, value in fields.items():
            if key.endswith("_name") and type(value) is int:
                item = names.items.get(value) if names is not None else None
                resolved[key] = item[0] if item and isinstance(item[0], str) else None
        payload = original_payload if original_payload is not None else message.SerializeToString()
        self.raw_events.append(
            {
                **self._stamp(),
                "dispatch_index": self.dispatch_index,
                "wire_source": source,
                "boundary": "before_gem_inner_dispatch",
                "fields_present": fields,
                "names_at_dispatch": resolved,
                "combat_log_names_table_present": names is not None,
                "protobuf_bytes_hex": payload.hex(),
                "protobuf_sha256": hashlib.sha256(payload).hexdigest(),
                "protobuf_bytes_origin": "original_direct_message_payload"
                if original_payload is not None
                else "reserialized_nested_message_including_unknown_fields",
            }
        )

    def on_packet_end(self, tick):
        self.ordinal += 1
        if not self._within_end(tick):
            self.counts["post_game_packet_callbacks"] += 1
            self.dirty.clear()
            return
        if self.parser.post_game_tick is not None:
            self.terminal_packet_ordinal = self.ordinal
        stamp = {"packet_ordinal": self.ordinal, "tick": tick}
        self.packets.append(
            {**stamp, "terminal_packet": self.terminal_packet_ordinal == self.ordinal}
        )
        canonical = {}
        for pid in range(10):
            hero = self.players._canonical_hero_entity(pid)
            if hero is not None:
                canonical.setdefault((hero.get_index(), hero.get_serial()), []).append(
                    {
                        "player_id": pid,
                        "hero_handle": self.players._hero_handle_for_player(pid),
                    }
                )
        trajectory_keys = set()
        for key, entity in self.focus_live.items():
            prior_bindings = self.previous.get(key, {}).get("canonical_player_bindings")
            if self.ordinal in self.cut_packet_ordinals or prior_bindings != canonical.get(key, []):
                self.dirty.setdefault(key, (entity, False))
            perched = entity.get("m_nPerchedTree")
            if (
                entity.get_class_name() == "CDOTA_Unit_Hero_MonkeyKing"
                and canonical.get(key)
                and type(perched) is int
                and 0 <= perched < 2**32 - 1
                and self.perched_position_ticks.get(key) != tick
            ):
                trajectory_keys.add(key)
                self.dirty.setdefault(key, (entity, False))
                self.perched_position_ticks[key] = tick
        for key, (entity, terminal) in self.dirty.items():
            cls = entity.get_class_name()
            focus = bool(FOCUS_PATTERN.search(cls))
            fields = self.fields[cls]
            raw = {
                path: _value(
                    entity,
                    field,
                    path,
                    selected_only=bool(field.model == 4 and not _full_class(cls)),
                )
                for path, field in fields.items()
                if path != "m_bWorldTreeState"
            }
            value = {
                **self._identity(entity),
                "active_raw": bool(entity.active),
                "terminal": terminal,
                "team_raw": _raw(entity.get("m_iTeamNum")),
                "fields_raw": raw,
            }
            if focus:
                value["canonical_player_bindings"] = canonical.get(key, [])
                value["life_state_raw"] = _raw(entity.get("m_lifeState"))
            previous = self.previous.get(key)
            previous_field_packets = self.previous_field_packets.setdefault(key, {})
            field_updates = _field_changes(
                raw,
                None if previous is None else previous["fields_raw"],
                previous_field_packets,
            )
            state_changed = (
                previous is None
                or field_updates
                or any(
                    not _strict_equal(item, previous.get(name))
                    for name, item in value.items()
                    if name != "fields_raw"
                )
            )
            if (
                state_changed
                or (focus and self.ordinal in self.cut_packet_ordinals)
                or key in trajectory_keys
            ):
                snapshot = {
                    name: deepcopy(item) for name, item in value.items() if name != "fields_raw"
                }
                snapshot["fields_raw"] = field_updates
                snapshot.update(
                    initial=previous is None,
                    fields_are_delta=previous is not None,
                    previous_packet_ordinal=self.previous_packet.get(key),
                )
                if focus:
                    snapshot["position"] = _position(entity)
                    snapshot["raw_perched_index_trajectory_sample"] = key in trajectory_keys
                self.entity_changes.append({**stamp, **snapshot})
                self.previous[key] = value
                self.previous_packet[key] = self.ordinal
                previous_field_packets.update({name: self.ordinal for name in field_updates})
            tree_field = fields.get("m_bWorldTreeState")
            if tree_field is not None:
                count = tree_field.field_type.count
                if type(count) is not int or not 0 < count <= MAX_ARRAY:
                    raise ValueError("Invalid world tree array count")
                words = [_raw(entity.get(f"m_bWorldTreeState.{i:04d}")) for i in range(count)]
                if any(w is not None and (type(w) is not int or not 0 <= w < 2**64) for w in words):
                    raise ValueError("Invalid uint64 world tree word")
                before = self.previous_trees.get(key)
                delta = [
                    [i, word] for i, word in enumerate(words) if before is None or word != before[i]
                ]
                if delta or terminal:
                    label = TEAM_CLASSES.get(cls, "unknown")
                    self.tree_changes.append(
                        {
                            **stamp,
                            **self._identity(entity),
                            "observer": label,
                            "word_count": count,
                            "initial": before is None,
                            "words": delta,
                            "terminal": terminal,
                            "active_raw": bool(entity.active),
                        }
                    )
                    self.previous_trees[key] = words
        self.dirty.clear()

    def result(self):
        end, clock = self.parser.post_game_tick, self.parser.game_clock
        allowed = {row["packet_ordinal"] for row in self.packets if row["tick"] <= end}
        unresolved, counts = [], self.counts.copy()

        def timed(rows):
            result = []
            for row in rows:
                if row["tick"] > end or row["packet_ordinal"] not in allowed:
                    counts["records_outside_completed_replay_packets"] += 1
                    unresolved.append(
                        {**row, "completed_packet_known": False, "consumer_use_allowed": False}
                    )
                    continue
                value = clock.game_time_at(row["tick"])
                result.append(
                    {
                        **row,
                        "game_time": value
                        if type(value) in (int, float) and math.isfinite(value)
                        else None,
                    }
                )
            return result

        payload = {
            "packets": timed(self.packets),
            "entity_changes": timed(self.entity_changes),
            "entity_events": timed(self.entity_events),
            "tree_word_changes": timed(self.tree_changes),
            "raw_tree_cut_events": timed(self.raw_events),
            "class_schemas": self.schemas,
            "send_tables_raw": self.send_tables,
        }
        payload["unresolved_packet_records"] = unresolved
        payload["sampling"] = {
            "boundary": "completed_packet",
            "packet_ordinal_base": 1,
            "packet_ordinal_definition": (
                "Gem completed-packet callback order; "
                "not file command or original wire-message order"
            ),
            "event_packet_assignment": (
                "callback event belongs to the next completed-packet ordinal; "
                "unresolved events are separately retained as non-consumable"
            ),
            "entity_change_boundary": "completed_packet",
            "tree_word_change_boundary": "completed_packet",
            "clock": "final pause-aware game_time_at(replay_tick); no second rounding",
            "position_selection": (
                "focus-entity selected-field/lifecycle/canonical change or TREE_CUT packet; "
                "movement-only changes are not a trajectory"
            ),
            "monkey_trajectory_selection": (
                "canonical MonkeyKing with raw m_nPerchedTree in [0, 2**32-2]: "
                "at most one completed-packet position per replay tick; "
                "raw index presence does not certify landing or tree identity"
            ),
            "entity_fields_encoding": (
                "per (entity_index,entity_serial): initial fields_raw is full; "
                "later fields_raw replaces supplied keys, except indexed storage deltas; "
                "null is explicit unknown. "
                "Other row fields are complete snapshots, never carried forward. "
                "previous_packet_ordinal links the preceding entity change."
            ),
            "fieldstate_storage_encoding": {
                "schema": "fieldstate-index-delta/1",
                "scope": "top-level fields_raw Gem.FieldState containers only",
                "full": (
                    "storage_rows_encoding=full; observed_storage_rows and all metadata; "
                    "base_field_packet_ordinal=null"
                ),
                "delta": (
                    "storage_rows_encoding=delta; metadata replaces completely; "
                    "changed_rows replaces rows by index; removed_storage_indices removes slots"
                ),
                "base": (
                    "base_field_packet_ordinal is the previous emitted value of this same "
                    "entity index, serial and field; absent/unknown base cannot be applied"
                ),
                "reset": (
                    "null, unknown or integer-count non-FieldState values replace the whole field; "
                    "later FieldState restarts with full encoding"
                ),
                "membership": (
                    "stored index removal is not proof of logical membership or disappearance; "
                    "capacity is not length"
                ),
            },
            "end_game_time": _raw(clock.game_time_at(end)),
            "terminal_packet_ordinal": self.terminal_packet_ordinal,
            "completed_packet_callbacks": self.ordinal,
            "counts": dict(counts),
        }
        return payload


def install_raw_combat_hook(parser, collector, wire):
    """Intercept raw S2 direct/bulk payloads even when CombatLogNames is missing."""
    original = parser._dispatch_inner

    def dispatch(type_id, payload):
        collector.dispatch_index += 1
        if type_id == wire._DOTA_UM_COMBAT_LOG_HLTV:
            entry = wire.CMsgDOTACombatLogEntry()
            entry.ParseFromString(payload)
            collector.raw_combat(entry, "direct_hltv", original_payload=payload)
        elif type_id == wire._SVC_USER_MESSAGE:
            wrapper = wire.CSVCMsg_UserMessage()
            wrapper.ParseFromString(payload)
            if wrapper.msg_type in (
                wire._DOTA_UM_COMBAT_LOG_DATA,
                wire._DOTA_UM_COMBAT_LOG_BULK_DATA,
            ):
                bulk = wire.CDOTAUserMsg_CombatLogBulkData()
                bulk.ParseFromString(wrapper.msg_data)
                for entry in bulk.combat_entries:
                    collector.raw_combat(entry, "wrapped_bulk")
        return original(type_id, payload)

    parser._dispatch_inner = dispatch
    return original


def install_sendtables_hook(parser, collector):
    original = parser._on_send_tables

    def capture_tables(data):
        collector.send_tables.append(
            {
                "tick": parser.tick,
                "byte_length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "payload_base64": base64.b64encode(data).decode("ascii"),
                "payload_kind": "original_decompressed_CDemoSendTables_outer_command_payload",
            }
        )
        return original(data)

    parser._on_send_tables = capture_tables
    return original


def capture(path, *, expected_match_id, expected_game_build):
    """Fully parse an explicitly identified replay in the caller's isolated Gem process."""
    if any(type(v) is not int or v <= 0 for v in (expected_match_id, expected_game_build)):
        raise ValueError("Explicit positive match and build required")
    import gem.parser as wire
    from gem.extractors.players import PlayerExtractor
    from gem.state.entities import EntityOp

    parser, players = wire.ReplayParser(str(path)), PlayerExtractor()
    players.attach(parser)
    collector = TreeProbeCollector(parser, players, EntityOp)
    parser.on_entity(collector.on_entity)
    parser._on_packet_end(collector.on_packet_end)
    original = install_raw_combat_hook(parser, collector, wire)
    sendtables_original = install_sendtables_hook(parser, collector)
    try:
        parser.parse()
    finally:
        parser._dispatch_inner = original
        parser._on_send_tables = sendtables_original
    if parser.parse_error is not None or parser.truncated_at_tick is not None:
        raise ValueError("Incomplete tree probe parse")
    if any(type(v) is not int for v in (parser.match_id, parser.game_build)) or (
        parser.match_id,
        parser.game_build,
    ) != (expected_match_id, expected_game_build):
        raise ValueError("Tree probe replay match/build differs from explicit identity")
    if type(parser.post_game_tick) is not int or parser.post_game_tick < 0:
        raise ValueError("Tree probe lacks post-game marker")
    return {
        "schema": "map-tree-probe/1",
        "coordinate_space": "world",
        "coordinate_formula": "cell*128+vec-16384; combat-log coordinates retain wire convention",
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
            "No tree index, bit-plane meaning or coordinate correspondence is inferred.",
            "Raw TREE_CUT value is uint32; its meaning and location convention are unverified.",
            "Packet words are endpoint states; multiple changes inside a packet may cancel.",
            "Schema covers encountered entity classes, not every declared replay class.",
            "Vision and HeroID aliases are raw candidates, not effective radius or decoding proof.",
            "S1 legacy game-event combat logs are not intercepted by this S2 raw probe.",
        ],
    }
