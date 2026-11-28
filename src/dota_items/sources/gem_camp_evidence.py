"""Freeze raw neutral-class entity evidence at requested decision seconds.

This is omniscient audit material, not a camp-stock feature. Consumers must project
to the observer's actual team visibility before using unit fields. Active entities
include corpses and player-controlled/summoned units; neither this class nor an
empty visible list establishes camp membership, life, or an empty camp.
"""

import json
import math
from copy import deepcopy
from pathlib import Path

from ..storage import file_hash
from .gem_capture import require_complete_parse

SCHEMA = "gem-camp-evidence/1"
COMPAT_SHA256 = "3f6e9ee2c222869adce45c6dfef757e719c9576bfdde82927e76d6868c47403d"
SAMPLING = "first_tick_start_before_entity_updates"
NEUTRAL_CLASS = "CDOTA_BaseNPC_Creep_Neutral"
ENTITY_NAME_FIELDS = (
    "m_pEntity.m_nameStringTableIndex",
    "m_pEntity.m_nameStringableIndex",
)
OWNERSHIP_FIELDS = (
    "m_hOwnerNPC",
    "m_hOwnerEntity",
    "m_nPlayerOwnerID",
    "m_iIsControllableByPlayer64",
    "m_bIsSummoned",
    "m_bIsControllable",
    "m_bIsControllableByPlayer",
    "m_bIsDominated",
    "m_bIsIllusion",
)
TEAM_CLASSES = {
    "radiant": ("CDOTA_DataRadiant", "CDOTADataRadiant"),
    "dire": ("CDOTA_DataDire", "CDOTADataDire"),
}
HANDLE_INDEX_BITS = 14
NULL_HANDLE = 0xFFFFFF


def verify_compatibility(root):
    """Verify the registered compat-v1 manifest and its complete Python source set.

    ``root`` is the imported Gem package directory, not its parent. The pinned
    manifest covers every Python file, including unmodified upstream sources.
    """
    root = Path(root)
    manifest = root.parent / "manifest.json"
    if not manifest.is_file() or file_hash(manifest) != COMPAT_SHA256:
        raise ValueError("camp evidence requires the registered Gem compatibility manifest")
    expected = json.loads(manifest.read_bytes())["patched"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*.py")}
    if actual != set(expected):
        raise ValueError("Gem compatibility Python source set mismatch")
    for name, sha in expected.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or file_hash(path) != sha:
            raise ValueError(f"Gem compatibility source fingerprint mismatch: {name}")
    return COMPAT_SHA256


def _runtime():
    # Keep optional replay dependencies out of import-time data/CLI validation.
    import gem

    root = Path(gem.__file__).resolve().parent
    verify_compatibility(root)
    from gem.parser import ReplayParser

    return ReplayParser, root


def _cases(cases):
    result = set()
    for hero, second in cases:
        if not isinstance(hero, str) or not hero or type(second) is not int or second < 0:
            raise ValueError("each camp case needs a hero and a nonnegative integer second")
        if (hero, second) in result:
            raise ValueError("duplicate camp evidence case")
        result.add((hero, second))
    if not result:
        raise ValueError("camp evidence requires at least one case")
    return sorted(result)


def _table_name(entity, field, table, table_name):
    index = entity.get(field)
    value, reason = None, None
    if index is None:
        reason = "missing_index"
    elif type(index) is not int or index < 0:
        reason = "invalid_index"
    elif table is None:
        reason = "missing_table"
    else:
        item = table.items.get(index)
        value = item[0] if isinstance(item, tuple) and item else item
        if not isinstance(value, str) or not value:
            value, reason = None, "unresolved_index"
    return dict(field=field, table=table_name, index=index, value=value, missing_reason=reason)


def _entity_name(entity, table):
    evidence = [_table_name(entity, field, table, "EntityNames") for field in ENTITY_NAME_FIELDS]
    names = {row["value"] for row in evidence if row["value"] is not None}
    if len(names) > 1:
        return None, evidence, "conflicting_entity_names"
    return next(iter(names), None), evidence, None


def _unique_entity(active, classes):
    found = [e for e in active if e.get_class_name() in classes]
    if len(found) > 1:
        raise ValueError(f"ambiguous active entity class: {classes}")
    return found[0] if found else None


def _observers(em, active, entity_names):
    """Resolve current PlayerResource selections, never controller PID caches."""
    resource = _unique_entity(active, ("CDOTA_PlayerResource",))
    result, slots, selected = {}, set(), set()
    if resource is None:
        return result
    for index in range(30):
        team = resource.get(f"m_vecPlayerData.{index:04d}.m_iPlayerTeam")
        slot = resource.get(f"m_vecPlayerTeamData.{index:04d}.m_iTeamSlot")
        if team not in (2, 3) or slot is None or (type(slot) is int and slot < 0):
            continue
        if type(team) is not int or type(slot) is not int or not 0 <= slot < 5:
            raise ValueError("invalid camp observer roster team-slot")
        if (team, slot) in slots:
            raise ValueError("duplicate camp observer roster team-slot")
        slots.add((team, slot))
        handle = resource.get(f"m_vecPlayerTeamData.{index:04d}.m_hSelectedHero")
        if handle is None or handle == NULL_HANDLE:
            continue
        if type(handle) is not int or not 0 <= handle <= 0xFFFFFFFF:
            raise ValueError("invalid selected hero handle")
        entity = em.find_by_handle(handle)
        if entity is None or not entity.active:
            continue
        identity = (entity.get_index(), entity.get_serial())
        if identity != (handle & ((1 << HANDLE_INDEX_BITS) - 1), handle >> HANDLE_INDEX_BITS):
            raise ValueError("selected hero handle identity mismatch")
        if identity in selected:
            raise ValueError("duplicate selected hero identity")
        selected.add(identity)
        if not entity.get_class_name().startswith("CDOTA_Unit_Hero_"):
            raise ValueError("selected entity is not a hero")
        entity_team = entity.get("m_iTeamNum")
        if entity_team is None:
            continue
        if type(entity_team) is not int or entity_team != team:
            raise ValueError("selected hero disagrees with roster team")
        hero, names, conflict = _entity_name(entity, entity_names)
        if conflict:
            raise ValueError("ambiguous selected hero name")
        if hero is None:
            continue
        if not hero.startswith("npc_dota_hero_") or hero in result:
            raise ValueError("invalid or duplicate selected hero name")
        result[hero] = (
            dict(team=team, slot=slot, resource_index=index),
            dict(
                selected_handle=handle,
                entity_index=identity[0],
                entity_serial=identity[1],
                naming=names,
            ),
        )
    return result


def _number(entity, field):
    value = entity.get(field)
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError(f"invalid numeric entity field: {field}")
    return value


def _position(entity, axis):
    cell = _number(entity, f"CBodyComponent.m_cell{axis.upper()}")
    offset = _number(entity, f"CBodyComponent.m_vec{axis.upper()}")
    return None if cell is None or offset is None else cell * 128 + offset


def _unit(entity, teams, entity_names, unit_names):
    index, serial = entity.get_index(), entity.get_serial()
    if type(index) is not int or not 0 <= index < (1 << HANDLE_INDEX_BITS):
        raise ValueError("invalid neutral entity index")
    if type(serial) is not int or serial < 0:
        raise ValueError("invalid neutral entity serial")
    name, naming, conflict = _entity_name(entity, entity_names)
    specific = _table_name(entity, "m_iUnitNameStringTableIndex", unit_names, "UnitNames")
    row = dict(
        entity_index=index,
        entity_serial=serial,
        class_name=entity.get_class_name(),
        entity_name=name,
        unit_name=specific["value"],
        team=_number(entity, "m_iTeamNum"),
        x=_position(entity, "x"),
        y=_position(entity, "y"),
        health=_number(entity, "m_iHealth"),
        max_health=_number(entity, "m_iMaxHealth"),
        life_state=_number(entity, "m_lifeState"),
        ownership={field: deepcopy(entity.get(field)) for field in OWNERSHIP_FIELDS},
        naming=dict(entity_names=naming, unit_name=specific),
        visibility={},
        visibility_source={},
        missing_reasons=[],
    )
    for key in ("entity_name", "unit_name", "team", "x", "y", "health", "max_health", "life_state"):
        if row[key] is None:
            row["missing_reasons"].append(
                conflict if key == "entity_name" and conflict else f"missing_{key}"
            )
    for field, value in row["ownership"].items():
        if value is None:
            row["missing_reasons"].append(f"missing_ownership:{field}")
    word_field = f"m_bNPCVisibleState.{index >> 6:04d}"
    for team, team_entity in teams.items():
        word = None if team_entity is None else team_entity.get(word_field)
        if word is not None and (type(word) is not int or not 0 <= word < (1 << 64)):
            raise ValueError("invalid team visibility word")
        state = "unknown" if word is None else "visible" if word & (1 << (index & 63)) else "hidden"
        row["visibility"][team] = state
        row["visibility_source"][team] = dict(
            field=word_field,
            bit=index & 63,
            word=word,
            team_entity_index=None if team_entity is None else team_entity.get_index(),
            team_entity_serial=None if team_entity is None else team_entity.get_serial(),
        )
        if state == "unknown":
            row["missing_reasons"].append(f"missing_visibility:{team}")
    return row


def capture_camp_evidence(raw_demo_path, cases):
    """Read an unpacked .dem completely; return one frozen raw frame per case.

    The first tick-start callback of a game second consumes that second even if
    its entity manager/observer is missing. No later callback or final string table
    can fill the missing evidence. Complete parsing and final clock agreement are
    required before any result is returned; missing requested seconds stay null.
    """
    needed = _cases(cases)
    by_second = {}
    for hero, second in needed:
        by_second.setdefault(second, []).append(hero)
    parser_type, gem_root = _runtime()
    compatibility = verify_compatibility(gem_root)
    parser = parser_type(str(raw_demo_path))
    frames, last = {}, None

    def sample(net_tick):
        nonlocal last
        second = parser.game_time_s
        if second is None:
            return
        if type(second) is not int:
            raise ValueError("camp frame requires an integer game second")
        if last is not None and second < last:
            raise ValueError("camp frame clock moved backwards")
        if second == last:
            return
        last = second
        if second not in by_second:
            return
        if type(parser.tick) is not int or type(net_tick) is not int:
            raise ValueError("camp frame requires replay and network tick identities")
        em = parser.entity_manager
        units, observers = None, {}
        if em is not None:
            active = em.all_active()
            entity_names = parser.string_tables.get_by_name("EntityNames")
            unit_names = parser.string_tables.get_by_name("UnitNames")
            teams = {
                team: _unique_entity(active, classes) for team, classes in TEAM_CLASSES.items()
            }
            observers = _observers(em, active, entity_names)
            units = [
                _unit(e, teams, entity_names, unit_names)
                for e in active
                if e.get_class_name() == NEUTRAL_CLASS
            ]
            units.sort(key=lambda u: (u["entity_index"], u["entity_serial"]))
            if len({u["entity_index"] for u in units}) != len(units):
                raise ValueError("duplicate active neutral entity index")
        for hero in by_second[second]:
            observer, evidence = observers.get(hero, (None, None))
            status = (
                "missing_frame"
                if em is None
                else "missing_observer"
                if observer is None
                else "observed"
            )
            frames[hero, second] = deepcopy(
                dict(
                    hero=hero,
                    t=second,
                    tick=parser.tick,
                    net_tick=net_tick,
                    status=status,
                    observer=observer,
                    observer_evidence=evidence,
                    units=units,
                    missing_reasons=["missing_entity_manager"]
                    if em is None
                    else ["missing_observer"]
                    if observer is None
                    else [],
                )
            )

    parser.on_tick_start(sample)
    parser.parse()
    require_complete_parse(parser)
    if type(parser.match_id) is not int or parser.match_id <= 0:
        raise ValueError("camp evidence replay identity is missing")
    for frame in frames.values():
        if parser.game_clock.game_seconds_at(frame["tick"]) != frame["t"]:
            raise ValueError("camp evidence final clock disagrees with sampled game second")
    verify_compatibility(gem_root)
    return dict(
        schema=SCHEMA,
        match_id=parser.match_id,
        compat_manifest_sha256=compatibility,
        sampling=SAMPLING,
        omniscient=True,
        usage="audit_only_requires_team_visibility_projection",
        coordinates="unsigned_cell_space:cell*128+vec",
        frames=[
            frames.get(
                (hero, second),
                dict(
                    hero=hero,
                    t=second,
                    tick=None,
                    net_tick=None,
                    status="missing_frame",
                    observer=None,
                    observer_evidence=None,
                    units=None,
                    missing_reasons=["second_not_observed"],
                ),
            )
            for hero, second in needed
        ],
    )
