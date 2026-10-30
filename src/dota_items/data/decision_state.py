"""Live-probe state card. Source consistency is not full cast/ETA certification."""

import math


def state_card(capture, decision, original_state):
    """Only current/past samples contribute; later validation sample is ignored."""
    tick = decision["tick"]
    if capture["match_id"] != decision["match_id"] or capture["decision_tick"] != tick:
        raise ValueError("Probe decision mismatch")
    rows = [r for r in capture["rows"] if r is not None and r["tick"] == tick]
    if len(rows) != 1:
        raise ValueError("Missing or ambiguous current probe")
    row = rows[0]
    pid = decision["target_slot"] if decision["target_slot"] < 5 else decision["target_slot"] - 123
    identity = (row["hero"]["entity_index"], row["hero"]["entity_serial"])
    if (
        row["player_id"] != pid
        or original_state["player_id"] != pid
        or original_state["tick"] != tick
        or identity != (original_state["entity_index"], original_state["entity_serial"])
    ):
        raise ValueError("Probe state identity mismatch")
    values = row["hero"]["values"]
    for old, native in {
        "hp": "m_iHealth",
        "max_hp": "m_iMaxHealth",
        "mana": "m_flMana",
        "max_mana": "m_flMaxMana",
        "life_state": "m_lifeState",
    }.items():
        if original_state.get(old) != values.get(native):
            raise ValueError("Resource changed against frozen raw")
    prior = [
        r
        for r in capture["rows"]
        if r is not None
        and r["tick"] < tick
        and r["player_id"] == pid
        and (r["hero"]["entity_index"], r["hero"]["entity_serial"]) == identity
    ]
    items, abilities = entries(row, prior)
    tp = [i for i in items if i["name"] == "item_tpscroll"]
    return {
        "schema": "decision-state-card/1",
        "tick": tick,
        "health": {
            "current": values.get("m_iHealth"),
            "max": values.get("m_iMaxHealth"),
            "status": "live_and_frozen_source_consistent",
        },
        "mana": {
            "raw": values.get("m_flMana"),
            "raw_max": values.get("m_flMaxMana"),
            "status": "source_consistent_units_not_independently_certified",
            "scale_correction_applied": False,
        },
        "level": row["level"],
        "items": items,
        "abilities": abilities,
        "tp": tp[0] if len(tp) == 1 else None,
        "enemy_equipment_and_cd": None,
        "tp_destination": None,
        "arrival_seconds": None,
        "support_expected_gain": None,
        "alternative_farm_gain": None,
        "limitations": [
            "Cooldown field zero is not sufficient evidence of castability.",
            "Countdown check uses only the past sample; tolerance .05s/1% is diagnostic.",
            "Mana range/bit metadata do not independently certify gameplay units.",
            "Enemy hidden state, legal landing points, paths and resource value not filled.",
        ],
        "training_allowed": False,
    }


def entries(row, prior):
    """Item/ability source cooldowns at row; only the latest earlier sample checks countdown."""
    tick = row["tick"]
    latest = max((r["tick"] for r in prior), default=-1)
    prior = [r for r in prior if r["tick"] == latest]
    prior = prior[0] if len(prior) == 1 else None
    items, abilities = [], []
    for channel, result in (("items", items), ("abilities", abilities)):
        for item in row[channel]:
            if item["entity"] is None or item["name"] is None:
                continue
            fields = item["entity"]["values"]
            cd = fields.get("m_fCooldown")
            if type(cd) not in (int, float) or not math.isfinite(cd) or cd < 0:
                cd = None
            previous = (
                []
                if prior is None
                else [
                    p
                    for p in prior[channel]
                    if p["slot"] == item["slot"] and p["handle"] == item["handle"] and p["entity"]
                ]
            )
            trend = None
            if len(previous) == 1 and cd is not None:
                old = previous[0]["entity"]["values"].get("m_fCooldown")
                elapsed = row["parser_game_time_s"] - prior["parser_game_time_s"]
                if type(old) in (int, float) and elapsed > 0 and old > 0 and cd > 0:
                    trend = math.isclose(old - cd, elapsed, rel_tol=0.01, abs_tol=0.05)
            entry = {
                "name": item["name"],
                "slot": item["slot"],
                "entity_index": item["entity"]["entity_index"],
                "entity_serial": item["entity"]["entity_serial"],
                "level": fields.get("m_iLevel"),
                "cooldown_source_value": cd,
                "cooldown_status": "unknown"
                if cd is None
                else "zero_observed"
                if cd == 0
                else "countdown_consistent"
                if trend
                else "positive_source_value",
                "past_countdown_consistent": trend,
                "charges": fields.get("m_iCurrentCharges"),
                "activated": fields.get("m_bActivated"),
                "hidden": fields.get("m_bHidden"),
                "can_cast": None,
                "source_ref": f"capture.rows[tick={tick}].{channel}[slot={item['slot']}]",
            }
            result.append(entry)
    return items, abilities
