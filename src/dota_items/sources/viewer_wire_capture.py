"""Observe raw vector writes before Gem loses length metadata; never alter decoding."""

from contextlib import contextmanager

VIEWER_CLASS = "CDOTAFogOfWarTempViewers"
VECTOR = "m_TempViewerInfo"
MAX_WRITES = 2_000_000


@contextmanager
def observe_vector_writes(entities, field_state, callback):
    """Instrument a fixed private parser in a fresh process; always restore both hooks."""
    original_read, original_set = entities.read_fields, field_state._set_compact
    context = None

    def read(reader, serializer, state):
        nonlocal context
        previous = context
        context = (serializer, state) if serializer.name == VIEWER_CLASS else None
        try:
            return original_read(reader, serializer, state)
        finally:
            context = previous

    def write(state, path, value):
        if context is not None and state is context[1]:
            serializer = context[0]
            field = serializer.fields[path[0]]
            if field.var_name == VECTOR:
                if type(value) not in (int, bool, float, str) and value is not None:
                    raise ValueError("Non-atomic vector write")
                names = [field.var_name]
                if len(path) >= 2:
                    names.append(path[1])
                if len(path) == 3 and field.serializer is not None:
                    names.append(field.serializer.fields[path[2]].var_name)
                elif len(path) > 2:
                    raise ValueError("Unsupported temporary viewer nesting")
                callback(state, list(path), names, value)
        return original_set(state, path, value)

    entities.read_fields, field_state._set_compact = read, write
    try:
        yield
    finally:
        entities.read_fields, field_state._set_compact = original_read, original_set


class ViewerWireCollector:
    def __init__(self, parser, entity_op):
        self.parser, self.op = parser, entity_op
        self.pending, self.rows, self.completed = {}, [], []
        self.ordinal, self.sequence, self.end_ordinal = 0, 0, None
        self.schema = None
        self.previous_metadata = {}

    def within_end(self):
        end = self.parser.post_game_tick
        return self.end_ordinal is None and (end is None or self.parser.tick <= end)

    def on_write(self, state, path, names, value):
        if not self.within_end():
            return
        self.sequence += 1
        if self.sequence > MAX_WRITES:
            raise ValueError("Viewer write count exceeds capture bound")
        self.pending.setdefault(id(state), []).append(
            {"write_sequence": self.sequence, "path": path, "names": names, "value": value}
        )

    def on_entity(self, entity, operation):
        if entity.get_class_name() != VIEWER_CLASS or not self.within_end():
            return
        writes = self.pending.pop(id(entity._field_state), [])
        if self.schema is None:
            field = next(f for f in entity.cls.serializer.fields if f.var_name == VECTOR)
            self.schema = {
                "vector_name": field.var_name,
                "vector_type": field.var_type,
                "model": field.model,
                "members": [
                    {"name": f.var_name, "type": f.var_type, "model": f.model}
                    for f in field.serializer.fields
                ],
            }
        lifecycle = {
            name: operation.has(getattr(self.op, name.upper()))
            for name in ("created", "entered", "left", "deleted")
        }
        key = entity.get_index(), entity.get_serial()
        metadata = (entity.get("m_iTeamNum"), entity.get("m_FoWTempViewerVersion"), entity.active)
        if (
            not writes
            and not any(lifecycle.values())
            and self.previous_metadata.get(key) == metadata
        ):
            return
        self.previous_metadata[key] = metadata
        self.rows.append(
            {
                "packet_ordinal": self.ordinal + 1,
                "tick": self.parser.tick,
                "entity_index": entity.get_index(),
                "entity_serial": entity.get_serial(),
                "team_raw": entity.get("m_iTeamNum"),
                "version_raw": entity.get("m_FoWTempViewerVersion"),
                "active_raw": entity.active,
                **lifecycle,
                "writes": writes,
            }
        )

    def on_packet(self, tick):
        self.ordinal += 1
        if not self.within_end():
            return
        self.completed.append((self.ordinal, tick))
        if self.parser.post_game_tick is not None:
            self.end_ordinal = self.ordinal

    def result(self):
        completed = dict(self.completed)
        if self.pending or any(
            completed.get(row["packet_ordinal"]) != row["tick"] for row in self.rows
        ):
            raise ValueError("Unresolved viewer writes or incomplete packet")
        for row in self.rows:
            row["game_time"] = self.parser.game_clock.game_time_at(row["tick"])
        tables = []
        for table in self.parser.string_tables.tables.values():
            # Inventory is an absence/coverage aid, never a complete spatial table.
            matches = [
                {"index": i, "key": key, "bytes": len(value)}
                for i, (key, value) in table.items.items()
                if any(word in key.lower() for word in ("tree", "world", "fow", "fog"))
            ]
            tables.append({"name": table.name, "entries": len(table.items), "matches": matches})
        return {
            "schema": "viewer-wire-capture/1",
            "match_id": self.parser.match_id,
            "game_build": self.parser.game_build,
            "post_game_tick": self.parser.post_game_tick,
            "terminal_packet_ordinal": self.end_ordinal,
            "parse_error": self.parser.parse_error,
            "truncated_at_tick": self.parser.truncated_at_tick,
            "coordinate_space": "raw_uninterpreted",
            "viewer_schema": self.schema,
            "completed_packets": len(self.completed),
            "writes": self.sequence,
            "events": self.rows,
            "string_table_inventory": tables,
            "evidence_use": "retrospective_omniscient_diagnostic_only",
            "action_review_allowed": False,
            "training_allowed": False,
        }


def capture(path, *, expected_match_id, expected_game_build):
    if any(type(v) is not int or v <= 0 for v in (expected_match_id, expected_game_build)):
        raise ValueError("Explicit positive match and build required")
    import gem.state.entities as entities
    from gem.parser import ReplayParser
    from gem.schema.field_state import FieldState

    parser = ReplayParser(str(path))
    collector = ViewerWireCollector(parser, entities.EntityOp)
    parser.on_entity(collector.on_entity)
    parser._on_packet_end(collector.on_packet)
    with observe_vector_writes(entities, FieldState, collector.on_write):
        parser.parse()
    if (
        parser.parse_error is not None
        or parser.truncated_at_tick is not None
        or type(parser.post_game_tick) is not int
        or parser.post_game_tick < 0
        or (parser.match_id, parser.game_build) != (expected_match_id, expected_game_build)
    ):
        raise ValueError("Incomplete or mismatched viewer parse")
    return collector.result()
