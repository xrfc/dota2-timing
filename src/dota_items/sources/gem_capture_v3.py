"""Parser v3: per-game-second state from a demo (design: docs/parser-v3-design.md, U130).

A second pass over kept demos; the v2 capture used by the running collector is untouched.
Per second it records, for the ten canonical heroes, every ability and item slot with its
remaining cooldown, cooldown length and charges, combat attributes, gold split, respawn and
buyback timers and the raw unit-state mask (decoding is a TODO, U130); and for the world:
time of day, game state, glyph cooldowns, Roshan, buildings, couriers, lane fronts and
summons/illusions. Missing values are null, never zero. All of it is omniscient: track B
must filter by team visibility before using it as input (U6).
"""

from importlib.metadata import version

CAPTURE_VERSION = "gem-state-capture/3"
NULL_HANDLE = 16777215
NO_CHARGE = -1e5  # Gem reports -1000000 for abilities without charges
MAP_CENTER = 16384.0  # cell-space coordinates; the map is centred here
LANE_BAND = 3000.0  # |x - y| beyond this (centred) is a side lane, inside is mid
LANE_CREEPS = ("CDOTA_BaseNPC_Creep_Lane", "CDOTA_BaseNPC_Creep_Siege")
BUILDINGS = ("CDOTA_BaseNPC_Tower", "CDOTA_BaseNPC_Barracks", "CDOTA_BaseNPC_Fort")
NOT_SUMMONS = (
    "CDOTA_Item",
    "CDOTA_Ability",
    "CDOTAWearableItem",
    "CDOTA_Unit_Courier",
    "CDOTA_NPC_Observer_Ward",
    "CDOTA_BaseNPC_Creep_Lane",
    "CDOTA_BaseNPC_Creep_Siege",
    "CDOTA_BaseNPC_Creep_Neutral",
    "CDOTA_BaseNPC_Tower",
    "CDOTA_BaseNPC_Barracks",
    "CDOTA_BaseNPC_Fort",
)
HERO_FIELDS = {
    "hp": "m_iHealth",
    "max_hp": "m_iMaxHealth",
    "life_state": "m_lifeState",
    "level": "m_iCurrentLevel",
    "move_speed": "m_iMoveSpeed",
    "attack_range": "m_iAttackRange",
    "damage_min": "m_iDamageMin",
    "damage_max": "m_iDamageMax",
    "damage_bonus": "m_iDamageBonus",
    "unit_state_raw": "m_nUnitState64",
}
HERO_FLOATS = {
    "mana": "m_flMana",
    "max_mana": "m_flMaxMana",
    "base_attack_time": "m_flBaseAttackTime",
    "armor": "m_flPhysicalArmorValue",
    "magic_resist": "m_flMagicalResistanceValue",
    "hp_regen": "m_flHealthThinkRegen",
    "mana_regen": "m_flManaThinkRegen",
    "strength": "m_flStrengthTotal",
    "agility": "m_flAgilityTotal",
    "intellect": "m_flIntellectTotal",
    "respawn_time": "m_flRespawnTime",
    "last_damage_time": "m_flLastDamageTime",
    "last_attack_time": "m_flLastAttackTime",
}
TEAM_DATA = {
    "reliable_gold": "m_iReliableGold",
    "unreliable_gold": "m_iUnreliableGold",
    "buyback_cooldown_time": "m_flBuybackCooldownTime",
    "buyback_cost_time": "m_flBuybackCostTime",
}
RULES = {
    "time_of_day": "m_pGameRules.m_iNetTimeOfDay",
    "game_state": "m_pGameRules.m_nGameState",
    "paused_ticks": "m_pGameRules.m_nTotalPausedTicks",
    "radiant_glyph_cooldown": "m_pGameRules.m_fGoodGlyphCooldown",
    "dire_glyph_cooldown": "m_pGameRules.m_fBadGlyphCooldown",
    "rune_cycle": "m_pGameRules.m_nRuneCycle",
}


def _round(value, digits=2):
    return round(value, digits) if isinstance(value, float) else value


def lane_of(x, y):
    """Top, mid or bot for a cell-space position (approximation by the map diagonal)."""
    dx, dy = x - MAP_CENTER, y - MAP_CENTER
    if dy - dx > LANE_BAND:
        return "top"
    if dx - dy > LANE_BAND:
        return "bot"
    return "mid"


def lane_fronts(creeps):
    """creeps: [(team, x, y)] alive lane creeps. Per team and lane: count and the creep
    furthest toward the enemy base (Radiant pushes toward +x+y, Dire toward -x-y)."""
    fronts = {}
    for team, x, y in creeps:
        key = f"{'radiant' if team == 2 else 'dire'}_{lane_of(x, y)}"
        progress = (x + y) if team == 2 else -(x + y)
        current = fronts.get(key)
        if current is None:
            fronts[key] = {"count": 1, "front": [round(x), round(y)], "_p": progress}
        else:
            current["count"] += 1
            if progress > current["_p"]:
                current.update(front=[round(x), round(y)], _p=progress)
    return {k: {"count": v["count"], "front": v["front"]} for k, v in sorted(fronts.items())}


def _charges(value):
    return None if value is None or value < NO_CHARGE else _round(value)


def _name(entity, names):
    index = entity.get("m_pEntity.m_nameStringTableIndex")
    item = names.items.get(index) if index is not None and index >= 0 else None
    if item is None:
        return None
    return item[0] if isinstance(item, tuple) else str(item)


def _abilities(hero, em, names):
    rows = []
    for slot in range(32):
        handle = hero.get(f"m_hAbilities.{slot:04d}")
        if handle in (None, NULL_HANDLE):
            handle = hero.get(f"m_vecAbilities.{slot:04d}")
        if handle in (None, NULL_HANDLE):
            continue
        ability = em.find_by_handle(handle)
        name = _name(ability, names) if ability is not None else None
        if name is None:
            continue
        row = {"name": name, "level": ability.get("m_iLevel")}
        if name.startswith("special_bonus_"):
            rows.append(row)  # talents: only whether they are taken
            continue
        row.update(
            cd=_round(ability.get("m_fCooldown")),
            cd_len=_round(ability.get("m_flCooldownLength")),
            charges=ability.get("m_nAbilityCurrentCharges"),
            charge_restore=_charges(ability.get("m_fAbilityChargeRestoreTimeRemaining")),
            mana_cost=ability.get("m_iManaCost"),
            hidden=ability.get("m_bHidden"),
            activated=ability.get("m_bActivated"),
            toggled=ability.get("m_bToggleState"),
            in_phase=ability.get("m_bInAbilityPhase"),
        )
        rows.append(row)
    return rows


def _items(hero, em, names):
    rows = {}
    for slot in range(17):
        handle = hero.get(f"m_hItems.{slot:04d}")
        if handle in (None, NULL_HANDLE):
            continue
        item = em.find_by_handle(handle)
        name = _name(item, names) if item is not None else None
        if name is None:
            rows[str(slot)] = {"name": None}  # occupied but unresolved
            continue
        rows[str(slot)] = {
            "name": name,
            "cd": _round(item.get("m_fCooldown")),
            "cd_len": _round(item.get("m_flCooldownLength")),
            "charges": item.get("m_iCurrentCharges"),
            "charge_restore": _charges(item.get("m_fAbilityChargeRestoreTimeRemaining")),
            "purchase_time": _round(item.get("m_flPurchaseTime")),
        }
    return rows


def hero_row(player_id, hero, em, names, players, team_data, resource, position):
    row = {
        "player_id": player_id,
        "hero": _name(hero, names),
        "team": hero.get("m_iTeamNum"),
        "pos": position(hero),
    }
    row["pos"] = [round(v) for v in row["pos"]] if row["pos"] else None
    for key, field in HERO_FIELDS.items():
        row[key] = hero.get(field)
    for key, field in HERO_FLOATS.items():
        row[key] = _round(hero.get(field))
    row["abilities"] = _abilities(hero, em, names)
    row["items"] = _items(hero, em, names)
    if team_data is not None:
        slot = players._player_team_slot.get(player_id, player_id % 5)
        for key, field in TEAM_DATA.items():
            row[key] = _round(team_data.get(f"m_vecDataTeam.{slot:04d}.{field}"))
    if resource is not None:
        index = players._resource_index(player_id)
        row["respawn_seconds"] = resource.get(f"m_vecPlayerTeamData.{index:04d}.m_iRespawnSeconds")
        row["last_buyback_time"] = _round(
            resource.get(f"m_vecPlayerTeamData.{index:04d}.m_flLastBuybackTime")
        )
    return row


def owner_player(entity, em, hero_index_to_pid, depth=2):
    """Player who owns a summon: follow its owner handles to a canonical hero."""
    for field in ("m_hOwnerNPC", "m_hOwnerEntity"):
        handle = entity.get(field)
        if handle in (None, NULL_HANDLE):
            continue
        owner = em.find_by_handle(handle)
        if owner is None:
            continue
        if owner.get_index() in hero_index_to_pid:
            return hero_index_to_pid[owner.get_index()]
        if depth > 1:
            found = owner_player(owner, em, hero_index_to_pid, depth - 1)
            if found is not None:
                return found
    return None


def world_row(em, heroes, position, names=None):
    rules = em.find_by_class_name("CDOTAGamerulesProxy")
    world = {k: _round(rules.get(v)) if rules else None for k, v in RULES.items()}
    roshan = em.find_by_class_name("CDOTA_Unit_Roshan")
    world["roshan"] = (
        {
            "alive": roshan.get("m_lifeState") == 0,
            "hp": roshan.get("m_iHealth"),
            "pos": [round(v) for v in position(roshan)] if position(roshan) else None,
        }
        if roshan is not None
        else None
    )
    buildings, couriers, creeps, summons = [], [], [], []
    hero_index_to_pid = {h.get_index(): pid for pid, h in heroes.items()}
    for entity in em.all_active():
        cls = entity.get_class_name()
        if cls.startswith(BUILDINGS):
            kind = cls.removeprefix("CDOTA_BaseNPC_")
            buildings.append(
                [
                    entity.get_index(),
                    kind,
                    entity.get("m_iTeamNum"),
                    entity.get("m_iHealth"),
                    entity.get("m_iMaxHealth"),
                ]
            )
        elif cls == "CDOTA_Unit_Courier":
            pos = position(entity)
            couriers.append(
                {
                    "team": entity.get("m_iTeamNum"),
                    "alive": entity.get("m_lifeState") == 0,
                    "state": entity.get("m_nCourierState"),
                    "pos": [round(v) for v in pos] if pos else None,
                }
            )
        elif cls in LANE_CREEPS:
            pos = position(entity)
            if entity.get("m_lifeState") == 0 and pos:
                creeps.append((entity.get("m_iTeamNum"), pos[0], pos[1]))
        elif cls.startswith("CDOTA_Unit_Hero_") and entity.get_index() not in hero_index_to_pid:
            pos = position(entity)
            if entity.get("m_lifeState") == 0 and pos:  # illusion or replica of a hero
                summons.append(
                    {
                        "illusion": True,
                        "of": cls.removeprefix("CDOTA_Unit_Hero_"),
                        "team": entity.get("m_iTeamNum"),
                        "owner": owner_player(entity, em, hero_index_to_pid),
                        "hp": entity.get("m_iHealth"),
                        "pos": [round(pos[0]), round(pos[1])],
                    }
                )
        elif cls.startswith("CDOTA_") and not cls.startswith(NOT_SUMMONS):
            if entity.get("m_lifeState") != 0:
                continue
            name = _name(entity, names) if names is not None else None
            if name == "npc_dota_thinker":
                continue  # invisible helpers of ground spells, not units
            owner = owner_player(entity, em, hero_index_to_pid)
            pos = position(entity)
            if owner is not None and pos:
                summons.append(
                    {
                        "illusion": False,
                        "class": cls,
                        "name": name,
                        "team": entity.get("m_iTeamNum"),
                        "owner": owner,
                        "hp": entity.get("m_iHealth"),
                        "pos": [round(pos[0]), round(pos[1])],
                    }
                )
    world["buildings"] = sorted(buildings)
    world["couriers"] = couriers
    world["lane_fronts"] = lane_fronts(creeps)
    world["summons"] = summons
    return world


def capture_state_v3(path, start_time=-90.0):
    """Parse one unpacked .dem; return (header, rows) with one row per game second."""
    if version("gem-dota") != "0.10.0":
        raise ValueError("State capture v3 requires the verified gem-dota==0.10.0")
    from gem.extractors._snapshots import _pos
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser

    from dota_items.sources.gem_capture import require_complete_parse

    parser = ReplayParser(str(path))
    players = PlayerExtractor()
    players.attach(parser)
    rows, last = [], {"second": None}

    def sample(_tick):
        em = parser.entity_manager
        game_time = getattr(parser, "game_time_s", None)
        if em is None or game_time is None or game_time < start_time:
            return
        second = int(game_time // 1)
        if second == last["second"]:
            return
        last["second"] = second
        names = parser.string_tables.get_by_name("EntityNames")
        heroes = {}
        for pid in range(10):
            hero = players._canonical_hero_entity(pid)
            if hero is not None:
                heroes[pid] = hero
        radiant = em.find_by_class_name("CDOTA_DataRadiant")
        dire = em.find_by_class_name("CDOTA_DataDire")
        resource = em.find_by_class_name("CDOTA_PlayerResource")
        hero_rows = []
        for pid, hero in sorted(heroes.items()):
            team_data = radiant if hero.get("m_iTeamNum") == 2 else dire
            hero_rows.append(hero_row(pid, hero, em, names, players, team_data, resource, _pos))
        rows.append(
            {
                "t": second,
                "heroes": hero_rows,
                "world": world_row(em, heroes, _pos, names),
            }
        )

    parser.on_tick_start(sample)
    parser.parse()
    require_complete_parse(parser)
    header = {
        "schema": CAPTURE_VERSION,
        "gem_version": version("gem-dota"),
        "seconds": len(rows),
        "unit_state": "raw m_nUnitState64 only; decoding is a TODO (U130)",
        "omniscient": True,
        "coordinates": "cell space (cell*128+vec), map centre 16384",
    }
    return header, rows


def check_cooldowns(rows, combat_log, window=3):
    """Do casts in the combat log start a cooldown in the captured state?

    For each hero ABILITY/ITEM entry, look at the caster's slot with that name in the next
    `window` seconds: a cooldown counts as seen when its remaining time is above zero. Slots
    whose cooldown length is zero (passives, toggles) are not checked.
    """
    by_second = {row["t"]: row for row in rows}
    checked = seen = 0
    missed = []
    for entry in combat_log:
        payload = entry["payload"]
        if payload.get("log_type") not in ("ABILITY", "ITEM"):
            continue
        if not payload.get("attacker_is_hero") or payload.get("attacker_is_illusion"):
            continue
        name, hero = payload.get("inflictor_name"), payload.get("attacker_name")
        if not name or entry.get("time") is None:
            continue
        slots = []
        for second in range(int(entry["time"]), int(entry["time"]) + window + 1):
            row = by_second.get(second)
            caster = next((h for h in row["heroes"] if h["hero"] == hero), None) if row else None
            if caster is None:
                continue
            slots += [a for a in caster["abilities"] if a["name"] == name]
            slots += [i for i in caster["items"].values() if i.get("name") == name]
        if not slots or not any(s.get("cd_len") for s in slots):
            continue
        checked += 1
        if any((s.get("cd") or 0) > 0 for s in slots):
            seen += 1
        elif len(missed) < 20:
            missed.append({"time": entry["time"], "hero": hero, "name": name})
    return {
        "checked": checked,
        "cooldown_seen": seen,
        "share": round(seen / checked, 4) if checked else None,
        "missed_examples": missed,
    }
