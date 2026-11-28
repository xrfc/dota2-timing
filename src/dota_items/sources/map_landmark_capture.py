"""Replay-native static landmarks; no map inference or downstream data dependencies."""

import math
from collections import defaultdict

from dota_items.sources.replay_identity import entity_evidence

CLASS_KINDS = {
    "CDOTA_BaseNPC_Tower": "npc_dota_tower",
    "CDOTA_BaseNPC_Barracks": "npc_dota_barracks",
    "CDOTA_BaseNPC_Fort": "npc_dota_fort",
    "CDOTA_Unit_Fountain": "ent_dota_fountain",
    "CDOTA_Unit_Twin_Gate": "npc_dota_unit_twin_gate",
    "CDOTA_NeutralSpawner": "npc_dota_neutral_spawner",
    "CDOTA_NPC_Lantern": "npc_dota_lantern",
    "CDOTA_BaseNPC_Watch_Tower": "npc_dota_watch_tower",
    "CDOTA_RoshanSpawner": "npc_dota_roshan_spawner",
    "CDOTA_MinibossSpawner": "npc_dota_miniboss_spawner",
    "CDOTA_BaseNPC_LotusPool": "npc_dota_lotus_pool",
    "CDOTA_BaseNPC_XP_Fountain": "npc_dota_xp_fountain",
    "CDOTA_Item_RuneSpawner_Bounty": "dota_item_rune_spawner_bounty",
    "CDOTA_Item_RuneSpawner_Powerup": "dota_item_rune_spawner_powerup",
}
NPC_KINDS = {"npc_dota_unit_twin_gate": "npc_dota_unit_twin_gate"}
STATIC_TOKENS = (
    "tower",
    "barracks",
    "fort",
    "fountain",
    "gate",
    "portal",
    "building",
    "spawner",
    "lantern",
    "lotus",
    "outpost",
)


def _npc_name(entity, parser):
    names = parser.string_tables.get_by_name("EntityNames")
    if names is None:
        return None
    for field in (
        "m_pEntity.m_nameStringableIndex",
        "m_nameStringableIndex",
        "m_nameStringTableIndex",
    ):
        index = entity.get_int32(field)
        if index is not None:
            item = names.items.get(index)
            if item and isinstance(item[0], str) and item[0]:
                return item[0]
    return None


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _world_position(row):
    invalid = []
    for axis in ("x", "y"):
        cell, vector = f"cell_{axis}", f"vec_{axis}"
        if type(row[cell]) is not int or row[cell] < 0:
            invalid.append(cell)
        # Gem's native position formula does not bound vec to a cell. Static entities
        # in real 7.42 demos have values such as 144, 230 and 240; preserve those values.
        if not _finite(row[vector]):
            invalid.append(vector)
        if not _finite(row[vector]):
            row[vector] = None
        if not _finite(row[cell]):
            row[cell] = None
    if invalid:
        return None, None, invalid
    return (
        row["cell_x"] * 128 + row["vec_x"] - 16384,
        row["cell_y"] * 128 + row["vec_y"] - 16384,
        [],
    )


class LandmarkCollector:
    """Deduplicate repeated observations, preserving incomplete and changed positions."""

    def __init__(self, parser, deleted_op):
        self.parser, self.deleted_op = parser, deleted_op
        self._rows = {}
        self._deletions = set()

    def on_entity(self, entity, op):
        cls = entity.get_class_name()
        if not isinstance(cls, str) or not (
            cls in CLASS_KINDS
            or cls == "CDOTA_BaseNPC"
            or any(token in cls.lower() for token in STATIC_TOKENS)
        ):
            return
        name = _npc_name(entity, self.parser)
        kind = CLASS_KINDS.get(cls) or (NPC_KINDS.get(name) if cls == "CDOTA_BaseNPC" else None)
        if cls == "CDOTA_BaseNPC" and kind is None:
            return
        if op.has(self.deleted_op):
            self._deletions.add((entity.get_index(), entity.get_serial()))
            return
        row = entity_evidence(entity)
        x, y, invalid = _world_position(row)
        row.update(kind=kind, npc_name=name, x=x, y=y, missing_coordinate_fields=invalid)
        key = tuple(
            row[field]
            for field in (
                "entity_index",
                "entity_serial",
                "class_name",
                "team",
                "npc_name",
                "kind",
                "cell_x",
                "cell_y",
                "vec_x",
                "vec_y",
            )
        )
        if key not in self._rows:
            self._rows[key] = {
                **row,
                "first_tick": self.parser.tick,
                "last_tick": self.parser.tick,
                "observations": 0,
            }
        self._rows[key]["last_tick"] = self.parser.tick
        self._rows[key]["observations"] += 1

    def result(self):
        observations, missing, unmapped = [], [], []
        positions = defaultdict(set)
        for row in self._rows.values():
            if row["kind"] is None:
                unmapped.append(row)
            elif row["missing_coordinate_fields"]:
                missing.append(row)
            else:
                observations.append(row)
                positions[row["entity_index"], row["entity_serial"]].add((row["x"], row["y"]))
        return {
            "observations": observations,
            "missing_coordinates": missing,
            "unmapped": unmapped,
            "changes": [
                {"entity_index": key[0], "entity_serial": key[1], "positions": sorted(value)}
                for key, value in sorted(positions.items())
                if len(value) > 1
            ],
            "deleted_entities": [list(key) for key in sorted(self._deletions)],
        }


def capture(path):
    """Decode a raw demo using the caller's already verified, isolated Gem environment."""
    from gem.parser import ReplayParser
    from gem.state.entities import EntityOp

    parser = ReplayParser(path)
    collector = LandmarkCollector(parser, EntityOp.DELETED)
    parser.on_entity(collector.on_entity)
    parser.parse()
    if parser.parse_error is not None or parser.truncated_at_tick is not None:
        raise ValueError("Incomplete landmark parse")
    if any(type(value) is not int or value <= 0 for value in (parser.match_id, parser.game_build)):
        raise ValueError("Landmark parse lacks match/build identity")
    if type(parser.post_game_tick) is not int or parser.post_game_tick < 0:
        raise ValueError("Landmark parse lacks post-game end marker")
    return {
        "schema": "map-landmark-capture/1",
        "match_id": parser.match_id,
        "game_build": parser.game_build,
        "post_game_tick": parser.post_game_tick,
        "parse_error": None,
        "truncated_at_tick": None,
        "coordinate_space": "world",
        "coordinate_formula": "cell*128+vec-16384",
        **collector.result(),
        "limits": (
            "Static entity observations only; no camp inference, terrain or walkability validation."
        ),
    }
