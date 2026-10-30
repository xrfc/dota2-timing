"""Decision-tick state for all visible heroes; enemy cooldowns are withheld by design.

User decision 2026-10-30 (option A): allies show mana, ability/item cooldowns and TP;
currently visible enemies show mana only; hidden heroes show nothing. Values remain
re-decoded source observations, not independently certified gameplay units.
"""

import math

from dota_items.data.decision_state import entries

SCHEMA = "decision-team-state/1"
PRODUCER = "decision-team-probe/1"
STATUS = "redecoded_source_observation_not_independent_gameplay_certification"


def player_id(slot):
    if 0 <= slot < 5:
        return slot
    if 128 <= slot < 133:
        return slot - 123
    raise ValueError("Unknown player slot")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def team_state(capture, decision_input, team_rows):
    """Build per-hero cards from rows at or before the decision tick only.

    team_rows are the package's existing same-tick visible rows; their health must
    equal the probe's, which binds each probe entity to the displayed hero.
    """
    tick = decision_input["tick"]
    if capture["decision_tick"] != tick or capture["producer"] != PRODUCER:
        raise ValueError("Capture does not describe this decision")
    if capture["build"] != 6965 or capture["schema_game_build"] != 6965:
        raise ValueError("Unaudited capture build")
    usable = [r for r in capture["rows"] if r["tick"] <= tick]
    visible = {
        r["player_slot"]: r
        for r in team_rows
        if r["visibility"] == "visible" and r.get("health") is not None
    }
    cards = []
    for position in decision_input["positions"]:
        slot = position["player_slot"]
        shown = visible.get(slot)
        if position["visibility"] != "visible" or shown is None:
            continue
        if shown["hero_id"] != position["hero_id"]:
            raise ValueError("Package hero identity mismatch")
        pid = player_id(slot)
        rows = [r for r in usable if r["player_id"] == pid and r["tick"] == tick]
        if len(rows) != 1:
            raise ValueError("Missing or duplicate current probe row")
        row = rows[0]
        values = row["hero"]["values"]
        if (values["m_iHealth"], values["m_iMaxHealth"]) != (
            shown["health"]["current"],
            shown["health"]["max"],
        ):
            raise ValueError("Probe hero does not match package health")
        mana, maximum = values["m_flMana"], values["m_flMaxMana"]
        if not (_number(mana) and _number(maximum) and 0 <= mana <= maximum):
            raise ValueError("Invalid mana observation")
        card = {
            "player_slot": slot,
            "hero_id": position["hero_id"],
            "relation": position["relation"],
            "health": {"current": values["m_iHealth"], "max": values["m_iMaxHealth"]},
            "mana": {"current": mana, "max": maximum, "status": STATUS, "can_cast": None},
            "level": row["level"],
            "items": [],
            "abilities": [],
            "tp": None,
            "cooldowns": "withheld_enemy_visibility_unverified",
        }
        if position["relation"] == "ally":
            identity = (row["hero"]["entity_index"], row["hero"]["entity_serial"])
            prior = [
                r
                for r in usable
                if r["tick"] < tick
                and r["player_id"] == pid
                and (r["hero"]["entity_index"], r["hero"]["entity_serial"]) == identity
            ]
            items, abilities = entries(row, prior)
            tp = [i for i in items if i["name"] == "item_tpscroll"]
            card.update(
                items=items,
                abilities=abilities,
                tp=tp[0] if len(tp) == 1 else None,
                cooldowns="source_observed",
            )
        cards.append(card)
    return {
        "schema": SCHEMA,
        "tick": tick,
        "cards": cards,
        "enemy_policy": "visible enemies: mana only; cooldowns withheld; hidden: nothing",
        "independent_gameplay_units_certified": False,
        "training_allowed": False,
    }
