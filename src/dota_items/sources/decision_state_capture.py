"""Optional live-entity probe. Does not alter the historical Gem capture/2 producer."""

import math

VERSION = "decision-live-probe/1"
RESOURCE_FIELDS = ("m_iHealth", "m_iMaxHealth", "m_flMana", "m_flMaxMana", "m_lifeState")
ABILITY_FIELDS = (
    "m_iLevel",
    "m_fCooldown",
    "m_flCooldown",
    "m_flCooldownLength",
    "m_iCurrentCharges",
    "m_iMaxCharges",
    "m_fAbilityChargeRestoreTime",
    "m_bInAbilityPhase",
    "m_bActivated",
    "m_bHidden",
    "m_flChannelStartTime",
)


def scalar(value):
    """Keep absent separate from zero; reject nonfinite/container values."""
    if value is None or type(value) in (bool, str, int):
        return value
    return value if type(value) is float and math.isfinite(value) else None


def metadata(entity, names):
    """Retain send-table range/bit metadata, never guess a scale correction."""
    root = getattr(getattr(entity, "cls", None), "serializer", None)
    result, visited = [], set()

    def walk(serializer):
        if serializer is None or id(serializer) in visited:
            return
        visited.add(id(serializer))
        for field in serializer.fields:
            name = field.var_name
            if name in names or any(w in name.lower() for w in ("cooldown", "charge", "mana")):
                result.append(
                    {
                        k: scalar(getattr(field, k, None))
                        for k in (
                            "var_name",
                            "var_type",
                            "encoder",
                            "bit_count",
                            "encode_flags",
                            "low_value",
                            "high_value",
                            "parent_name",
                        )
                    }
                )
            walk(getattr(field, "serializer", None))

    walk(root)
    return result


def entity_probe(entity, fields):
    return {
        "entity_index": entity.get_index(),
        "entity_serial": entity.get_serial(),
        "class_name": entity.get_class_name(),
        "values": {name: scalar(entity.get(name)) for name in fields},
        "field_metadata": metadata(entity, fields),
    }


def capture(extractor, snapshot, *, empty_handle=0xFFFFFF):
    """Only called for a selected tick in a hash-pinned standalone parser process."""
    hero = extractor._canonical_hero_entity(snapshot.player_id)
    if hero is None:
        return None
    parser = extractor._parser
    manager = parser.entity_manager
    table = parser.string_tables.get_by_name("EntityNames")
    result = {
        "schema": VERSION,
        "tick": snapshot.tick,
        "player_id": snapshot.player_id,
        "hero": entity_probe(hero, RESOURCE_FIELDS),
        "level": snapshot.level,
        "parser_game_time_s": scalar(parser.game_time_s),
        "game_start_time_s": scalar(parser.game_clock.game_start_time_s),
        "items": [],
        "abilities": [],
        "admission": "unverified_source_probe",
    }
    for channel, count in (("items", 17), ("abilities", 32)):
        for slot in range(count):
            field = ("m_hItems" if channel == "items" else "m_hAbilities") + f".{slot:04d}"
            handle = hero.get_uint32(field)
            if handle is None and channel == "abilities":
                handle = hero.get_uint32(f"m_vecAbilities.{slot:04d}")
            row = {
                "slot": slot,
                "handle": handle,
                "status": "unknown",
                "entity": None,
                "name": None,
            }
            if handle == empty_handle:
                row["status"] = "empty"
            elif handle is not None:
                resolved = manager.find_by_handle(handle)
                if resolved is not None:
                    index = resolved.get_int32("m_pEntity.m_nameStringTableIndex")
                    if index is None:
                        index = resolved.get_int32("m_pEntity.m_nameStringableIndex")
                    value = (
                        table.items.get(index) if table is not None and index is not None else None
                    )
                    name = value[0] if isinstance(value, tuple) else value
                    row.update(
                        status="resolved",
                        name=name if isinstance(name, str) else None,
                        entity=entity_probe(resolved, ABILITY_FIELDS),
                    )
            result[channel].append(row)
    return result
