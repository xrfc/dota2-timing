"""Conservative exploratory source appendix, not admitted decision features.

No finished teamfight summaries, enemy inventories, future ward/smoke endpoints
or event-derived cast readiness. Public source reader is owned by the caller.
"""

from collections import Counter


def source_context(raw, decision, clock, *, history_seconds=60):
    """Cut by native tick AND reconstructed game time; same-tick events excluded.

    history_seconds is a display inspection setting, not a label horizon.
    Clock callable must be pinned by the producer. No input mutation.
    """
    if type(history_seconds) is not int or not 0 < history_seconds <= 300:
        raise ValueError("Invalid inspection window")
    if raw["match_id"] != decision["match_id"] or decision["observer_team"] not in {
        "radiant",
        "dire",
    }:
        raise ValueError("Context identity/view mismatch")
    tick, now, view = decision["tick"], decision["time"], decision["observer_team"]
    team = 2 if view == "radiant" else 3
    pid = decision["target_slot"] if team == 2 else decision["target_slot"] - 123
    targets = [p for p in raw["players"] if p["player_id"] == pid]
    if (
        len(targets) != 1
        or targets[0]["hero_id"] != decision["target_hero_id"]
        or targets[0]["team"] != team
    ):
        raise ValueError("Target identity mismatch")
    target = targets[0]["hero_name"]
    heroes = {p["hero_name"]: p["hero_id"] for p in raw["players"]}

    def past(row):
        t = row.get("tick")
        if type(t) is not int or not 0 <= t < tick:
            return None
        sec = clock(t)
        return sec if sec is not None and now - history_seconds <= sec <= now else None

    combat, own_actions, farming = [], [], Counter()
    eligible, flags = 0, Counter()
    for i, event in enumerate(raw.get("combat_log") or []):
        sec = past(event)
        if sec is None:
            continue
        eligible += 1
        flags[str(event.get("visible_" + view))] += 1
        if event.get("visible_" + view) is not True:
            continue
        attacker, receiver = event.get("attacker_name"), event.get("target_name")
        kind = event.get("log_type")
        base = {"tick": event["tick"], "time": sec, "type": kind, "source_ref": f"combat_log[{i}]"}
        if kind == "DAMAGE" and attacker == target and isinstance(receiver, str):
            if receiver.startswith("npc_dota_neutral_"):
                farming["neutral_damage_records"] += 1
            elif receiver.startswith("npc_dota_creep_"):
                farming["creep_damage_records"] += 1
        if kind in {"ABILITY", "ITEM"} and attacker == target:
            own_actions.append(base | {"name": event.get("inflictor_name")})
        # Strict real-hero presence checks: names alone do not exclude illusions.
        if (
            kind == "DAMAGE"
            and attacker in heroes
            and receiver in heroes
            and all(
                event.get(k) is v
                for k, v in {
                    "attacker_is_hero_present": True,
                    "target_is_hero_present": True,
                    "attacker_is_illusion_present": True,
                    "target_is_illusion_present": True,
                    "attacker_is_hero": True,
                    "target_is_hero": True,
                    "attacker_is_illusion": False,
                    "target_is_illusion": False,
                }.items()
            )
        ):
            combat.append(
                base | {"attacker_hero_id": heroes[attacker], "target_hero_id": heroes[receiver]}
            )
    wards, smoke = [], []
    for i, ward in enumerate(raw.get("wards") or []):
        sec = past(ward)
        if sec is not None and ward.get("team") == team:
            wards.append(
                {
                    "tick": ward["tick"],
                    "time": sec,
                    "type": ward.get("ward_type"),
                    "x": ward.get("x"),
                    "y": ward.get("y"),
                    "source_ref": f"wards[{i}]",
                    "current_vision_coverage": None,
                }
            )
    for i, event in enumerate(raw.get("smoke_events") or []):
        sec = past(event)
        if sec is not None and event.get("team") == team:
            smoke.append(
                {
                    "tick": event["tick"],
                    "time": sec,
                    "source_ref": f"smoke_events[{i}]",
                    "currently_smoked": None,
                }
            )
    short = [r for r in combat if r["time"] >= now - 10]
    participants = Counter()
    for r in short:
        participants.update([r["attacker_hero_id"], r["target_hero_id"]])
    states = [
        (i, s)
        for i, s in enumerate(raw.get("coach_state_snapshots") or [])
        if s["player_id"] == pid and s["tick"] == tick
    ]
    # Numeric diagnostics are NOT action inputs, even for own hero.
    numeric = None
    if len(states) == 1 and decision.get("friendly_state_status") == "same_tick_identity_matched":
        i, s = states[0]
        numeric = {k: s.get(k) for k in ("hp", "max_hp", "mana", "max_mana", "level")}
        numeric["source_ref"] = f"coach_state_snapshots[{i}]"
        numeric["semantic_status"] = "source_values_only_not_cast_readiness"
    return {
        "schema": "decision-source-context/1",
        "admission": "exploratory_appendix_not_model_input",
        "history_game_seconds": history_seconds,
        "cutoff": {"tick": tick, "time": now, "event_tick_rule": "strictly_before"},
        "raw_channel_counts": {
            k: len(raw[k]) if isinstance(raw.get(k), list) else None
            for k in (
                "combat_log",
                "wards",
                "smoke_events",
                "towers",
                "objectives",
                "teamfights",
                "coach_state_snapshots",
            )
        },
        "past_combat_rows": eligible,
        "past_visibility_flags": dict(flags),
        "visible_real_hero_damage": combat,
        "last10s_hero_damage_count": len(short),
        "last10s_participant_hero_ids": sorted(participants),
        "own_action_records": own_actions,
        "own_farming_activity": dict(farming),
        "friendly_recent_ward_placements": wards,
        "friendly_recent_smoke_activations": smoke,
        "own_numeric_diagnostic": numeric,
        "tp_readiness": None,
        "tp_arrival_seconds": None,
        "current_lane_creeps": None,
        "current_neutral_camp_stock": None,
        "enemy_smoke_truth": None,
        "enemy_inventory": None,
        "limitations": [
            "Event side flags require independent semantic certification before admission.",
            "Recent damage records do not define current fight bounds or outcomes.",
            "Placement is not current effective ward vision; enemy wards/smoke withheld.",
            "Finished teamfight/objective summaries are never copied into decision inputs.",
            "Past farming activity is not remaining resource stock or optimal farm value.",
        ],
    }
