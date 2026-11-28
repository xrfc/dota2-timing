"""Replay-native camp associations and objective lifecycles, without map inference."""

import math
from collections import Counter, defaultdict

from dota_items.sources.replay_identity import entity_evidence

CLASS_KINDS = {
    "CDOTA_NeutralSpawner": "spawner",
    "CDOTA_BaseNPC_Creep_Neutral": "neutral_unit",
    "CDOTA_Unit_Roshan": "roshan",
    "CDOTA_Unit_Miniboss": "tormentor",
}
RAW_FIELDS = (
    "m_Type",
    "m_iCampType",
    "m_hNeutralSpawner",
    "m_bIsWaitingToSpawn",
    "m_lifeState",
    "m_iHealth",
    "m_iMaxHealth",
    "m_iTeamNum",
    "m_bIsNeutralUnitType",
    "m_iUnitNameStringTableIndex",
    "m_pEntity.m_nameStringTableIndex",
    "m_pEntity.m_nameStringableIndex",
    "m_flCreateTime",
)
SIGNATURE_FIELDS = (
    "m_Type",
    "m_iCampType",
    "m_hNeutralSpawner",
    "m_bIsWaitingToSpawn",
    "m_lifeState",
    "m_iTeamNum",
    "m_iUnitNameStringTableIndex",
    "m_pEntity.m_nameStringTableIndex",
    "m_pEntity.m_nameStringableIndex",
)


def _scalar(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) in (int, float) and math.isfinite(value):
        return value
    return None


def _name(entity, parser, table_name, fields):
    table = parser.string_tables.get_by_name(table_name)
    if table is not None:
        for field in fields:
            index = entity.get_int32(field)
            item = table.items.get(index) if type(index) is int else None
            if item and isinstance(item[0], str) and item[0]:
                return item[0], field
    return None, None


def _identity(entity):
    return [entity.get_index(), entity.get_serial()]


def _snapshot(entity, parser, tick, op):
    row = entity_evidence(entity)
    missing = []
    for axis in ("x", "y"):
        cell, vec = row[f"cell_{axis}"], row[f"vec_{axis}"]
        if type(cell) is not int or cell < 0:
            missing.append(f"cell_{axis}")
        if type(vec) not in (int, float) or not math.isfinite(vec):
            missing.append(f"vec_{axis}")
    row = {name: _scalar(value) for name, value in row.items()}
    row.update(
        tick=tick,
        op=op,
        active=entity.active,
        x=None if missing else row["cell_x"] * 128 + row["vec_x"] - 16384,
        y=None if missing else row["cell_y"] * 128 + row["vec_y"] - 16384,
        missing_coordinate_fields=missing,
        raw_fields={name: _scalar(entity.get(name)) for name in RAW_FIELDS},
    )
    row["npc_name"], row["npc_name_field"] = _name(
        entity, parser, "UnitNames", ("m_iUnitNameStringTableIndex",)
    )
    row["npc_name_table"] = "UnitNames"
    row["entity_name"], row["entity_name_field"] = _name(
        entity,
        parser,
        "EntityNames",
        ("m_pEntity.m_nameStringTableIndex", "m_pEntity.m_nameStringableIndex"),
    )
    row["entity_name_table"] = "EntityNames"
    handle = row["raw_fields"]["m_hNeutralSpawner"]
    resolved = parser.entity_manager.find_by_handle(handle) if type(handle) is int else None
    row["spawner_identity"] = (
        _identity(resolved)
        if resolved is not None and resolved.get_class_name() == "CDOTA_NeutralSpawner"
        else None
    )
    return row


class RuntimeCollector:
    """Keep lifecycle changes and explicit empty objective frames at 30-tick intervals."""

    def __init__(self, parser, entity_op):
        self.parser, self.entity_op = parser, entity_op
        self.records = {}
        self.live_objectives = {}
        self.frames = []
        self.field_schemas = {}
        self.last_frame_tick = None

    def on_entity(self, entity, op):
        cls = entity.get_class_name()
        kind = CLASS_KINDS.get(cls)
        if kind is None:
            return
        parser, tick = self.parser, self.parser.tick
        if parser.post_game_tick is not None and tick > parser.post_game_tick:
            return
        if cls not in self.field_schemas:
            serializer = getattr(entity.cls, "serializer", None)
            self.field_schemas[cls] = {
                name: bool(serializer and serializer._resolve_field(name).path is not None)
                for name in RAW_FIELDS
            }
        key = tuple(_identity(entity))
        deleted, left = op.has(self.entity_op.DELETED), op.has(self.entity_op.LEFT)
        record = self.records.setdefault(
            key,
            {
                "entity_index": key[0],
                "entity_serial": key[1],
                "class_name": cls,
                "kind": kind,
                "created_tick": tick if op.has(self.entity_op.CREATED) else None,
                "last_tick": tick,
                "observations": [],
                "deleted_ticks": [],
                "left_ticks": [],
            },
        )
        record["last_tick"] = tick
        if deleted:
            record["deleted_ticks"].append(tick)
        if left:
            record["left_ticks"].append(tick)
        # Store positions at lifecycle changes, not every moving-creep update.
        signature = tuple(_scalar(entity.get(name)) for name in SIGNATURE_FIELDS) + (
            entity.active,
            deleted,
            left,
        )
        if signature != record.get("_signature"):
            label = "deleted" if deleted else "left" if left else "observed"
            record["observations"].append(_snapshot(entity, parser, tick, label))
            record["_signature"] = signature
        if kind in ("roshan", "tormentor"):
            if deleted or left or not entity.active:
                self.live_objectives.pop(key, None)
            else:
                self.live_objectives[key] = entity

    def on_tick_start(self, _net_tick):
        tick = self.parser.tick
        if self.parser.post_game_tick is not None and tick > self.parser.post_game_tick:
            return
        if self.last_frame_tick is not None and tick - self.last_frame_tick < 30:
            return
        self.last_frame_tick = tick
        self.frames.append(
            {
                "tick": tick,
                "roshan": [],
                "tormentor": [],
            }
        )
        frame = self.frames[-1]
        for entity in self.live_objectives.values():
            frame[CLASS_KINDS[entity.get_class_name()]].append(
                _snapshot(entity, self.parser, tick, "pre_tick_sample")
            )

    def result(self):
        end, clock = self.parser.post_game_tick, self.parser.game_clock

        def time_at(tick):
            value = clock.game_time_at(tick)
            return float(value) if type(value) in (int, float) and math.isfinite(value) else None

        coverage = defaultdict(Counter)

        def timed(row, kind):
            row["game_time"] = time_at(row["tick"])
            stats = coverage[kind]
            stats["samples"] += 1
            for field in ("npc_name", "game_time", "x", "y", "spawner_identity"):
                stats[field] += row[field] is None
            for field, value in row["raw_fields"].items():
                stats[field] += value is None
            return row

        channels = {"spawners": [], "neutral_units": [], "objectives": []}
        for record in self.records.values():
            record.pop("_signature", None)
            record["observations"] = [
                timed(row, record["kind"]) for row in record["observations"] if row["tick"] <= end
            ]
            if not record["observations"]:
                continue
            record["last_tick"] = min(record["last_tick"], end)
            record["last_game_time"] = time_at(record["last_tick"])
            record["deleted_ticks"] = [tick for tick in record["deleted_ticks"] if tick <= end]
            record["left_ticks"] = [tick for tick in record["left_ticks"] if tick <= end]
            channel = {"spawner": "spawners", "neutral_unit": "neutral_units"}.get(
                record["kind"], "objectives"
            )
            channels[channel].append(record)
        frames = []
        for frame in self.frames:
            if frame["tick"] > end:
                continue
            frame["game_time"] = time_at(frame["tick"])
            for kind in ("roshan", "tormentor"):
                frame[kind] = [timed(row, kind) for row in frame[kind]]
            frames.append(frame)
        return {
            **channels,
            "objective_frames": frames,
            "field_schemas": self.field_schemas,
            "field_coverage": {
                kind: {
                    "samples": counts["samples"],
                    "missing": {key: value for key, value in counts.items() if key != "samples"},
                    "missing_fraction": {
                        key: value / counts["samples"]
                        for key, value in counts.items()
                        if key != "samples"
                    },
                }
                for kind, counts in sorted(coverage.items())
            },
            "sampling": {
                "objective_interval_replay_ticks": 30,
                "objective_boundary": "before_current_tick_entity_deltas",
                "neutral_units": "first_and_changed_life_waiting_team_name_or_spawner",
                "coverage_basis": "stored_lifecycle_observations_and_objective_frames",
                "clock": "Gem.GameClock.game_time_at(raw_replay_tick); no integer rounding",
                "game_start_time_s": clock.game_start_time_s,
                "net_tick_offset": clock.net_tick_offset,
                "end_game_time": time_at(end),
            },
        }


def capture(path):
    """Use the caller's verified Gem environment; this is omniscient diagnostic evidence."""
    from gem.parser import ReplayParser
    from gem.state.entities import EntityOp

    parser = ReplayParser(path)
    collector = RuntimeCollector(parser, EntityOp)
    parser.on_entity(collector.on_entity)
    parser.on_tick_start(collector.on_tick_start)
    parser.parse()
    if parser.parse_error is not None or parser.truncated_at_tick is not None:
        raise ValueError("Incomplete runtime map parse")
    if any(type(value) is not int or value <= 0 for value in (parser.match_id, parser.game_build)):
        raise ValueError("Runtime map parse lacks match/build identity")
    if type(parser.post_game_tick) is not int or parser.post_game_tick < 0:
        raise ValueError("Runtime map parse lacks post-game marker")
    return {
        "schema": "map-runtime-capture/1",
        "match_id": parser.match_id,
        "game_build": parser.game_build,
        "post_game_tick": parser.post_game_tick,
        "parse_error": None,
        "truncated_at_tick": None,
        "coordinate_space": "world",
        "coordinate_formula": "cell*128+vec-16384",
        **collector.result(),
        "limits": [
            "Entity creation is not spawn: precreated neutrals can be waiting to spawn.",
            "Absent or deleted entity is not a confirmed death; missing fields remain unknown.",
            "Camp enum labels, player vision, control and timer rules are not inferred here.",
            "Samples and raw life transitions are not continuous movement trajectories.",
        ],
    }
