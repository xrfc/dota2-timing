"""Retrospective event associations, never causal labels or training admission."""

from collections import Counter, defaultdict

from dota_items.data.observer import player_id

# Inspection shortlist, not a patch-certified exhaustive ability ontology.
MOVEMENT = {
    "queenofpain_blink",
    "phantom_assassin_phantom_strike",
    "earthshaker_enchant_totem",
    "magnataur_skewer",
    "vengefulspirit_nether_swap",
    "disruptor_glimpse",
    "pudge_meat_hook",
    "slark_pounce",
    "juggernaut_omni_slash",
    "juggernaut_swift_slash",
    "life_stealer_infest",
    "tinker_warp_grenade",
    "ringmaster_whoopee_cushion",
    "roshan_grab_and_throw",
    "item_blink",
    "item_overwhelming_blink",
    "item_arcane_blink",
    "item_swift_blink",
    "item_force_staff",
    "item_hurricane_pike",
}
CHANNELLED = {"item_tpscroll", "tinker_keen_teleport", "twin_gate_portal_warp"}
TYPES = {"ABILITY", "ITEM", "MODIFIER_ADD", "MODIFIER_REMOVE", "DEATH", "BUYBACK"}


def alias(name):
    return name.replace("_", "")


def roles(event, hero, pid):
    """Require explicit real-hero flags; do not borrow events from illusions."""
    result = []
    for role in ("attacker", "target"):
        if (
            alias(event.get(role + "_name", "")) == alias(hero)
            and event.get(role + "_is_hero") is True
            and event.get(role + "_is_illusion") is False
        ):
            result.append(role)
    if event["log_type"] == "BUYBACK" and event["value"] == pid:
        result.append("buyback_player_id")
    return result


def inspect_jumps(raw, audit, tolerance=60, channel_lookback=300):
    """Join all nearby events and recovery episodes without selecting a winner.

    The core interval is (previous_tick, current_tick]; extended windows are
    explicitly marked and include future context, so outputs are offline only.
    """
    if raw["match_id"] != audit["match_id"]:
        raise ValueError("Match identity mismatch")
    if tolerance < 0 or channel_lookback < 0:
        raise ValueError("Negative window")
    players = {p["player_id"]: p for p in raw["players"]}
    if len(players) != len(raw["players"]):
        raise ValueError("Duplicate player ID")
    if len({alias(p["hero_name"]) for p in players.values()}) != len(players):
        raise ValueError("Ambiguous hero alias")
    events = defaultdict(list)
    for i, event in enumerate(raw["combat_log"]):
        if event["log_type"] not in TYPES:
            continue
        for pid, player in players.items():
            matched = roles(event, player["hero_name"], pid)
            if matched:
                events[pid].append({**event, "source_ref": f"combat_log[{i}]", "roles": matched})
    for rows in events.values():
        rows.sort(key=lambda e: e["tick"])
    recoveries = []
    for i, tr in enumerate(audit["life_transitions"]):
        prev, curr = tr["previous"], tr["current"]
        if (
            tr["kind"] != "life_state_change"
            or prev["life_state"] not in (1, 2)
            or curr["life_state"] != 0
        ):
            continue
        pid = player_id(tr["player_slot"])
        start, end = prev["tick"], curr["tick"]
        # Prior sampled death transition bounds the current episode, not any old death.
        death_states = [
            t
            for t in audit["life_transitions"]
            if t["player_slot"] == tr["player_slot"]
            and t["previous"]["life_state"] == 0
            and t["current"]["life_state"] in (1, 2)
            and t["current"]["tick"] <= start
        ]
        death_state = (
            max(death_states, key=lambda t: t["current"]["tick"]) if death_states else None
        )
        deaths = [
            e
            for e in events[pid]
            if e["log_type"] == "DEATH"
            and "target" in e["roles"]
            and death_state is not None
            and abs(e["tick"] - death_state["current"]["tick"]) <= tolerance
            and e["tick"] <= end
        ]
        buybacks = [
            e
            for e in events[pid]
            if e["log_type"] == "BUYBACK" and start - tolerance <= e["tick"] <= end + tolerance
        ]
        category = (
            "buyback_near_recovery"
            if buybacks
            else "reincarnation_flag_near_prior_death"
            if any(e.get("will_reincarnate") is True for e in deaths)
            else "recovery_mechanism_unresolved"
        )
        recoveries.append(
            dict(
                player_slot=tr["player_slot"],
                transition_ref=f"life_transitions[{i}]",
                previous=prev,
                current=curr,
                deaths=deaths,
                buybacks=buybacks,
                category=category,
            )
        )
    result = []
    usage = Counter()
    for i, jump in enumerate(audit["jumps"]):
        pid = player_id(jump["player_slot"])
        start, end = jump["previous"]["source_tick"], jump["current"]["source_tick"]
        if start >= end:
            raise ValueError("Non-increasing jump ticks")
        nearby = []
        for event in events[pid]:
            tick = event["tick"]
            channel = event["inflictor_name"] in CHANNELLED and "attacker" in event["roles"]
            if not (
                start - tolerance <= tick <= end + tolerance
                or channel
                and start - channel_lookback <= tick <= end
            ):
                continue
            scope = (
                "core"
                if start < tick <= end
                else "future_context"
                if tick > end
                else "preceding_context"
            )
            name = event["inflictor_name"]
            required_role = (
                "target" if name in {"disruptor_glimpse", "roshan_grab_and_throw"} else None
            )
            self_only = name in {
                "queenofpain_blink",
                "item_blink",
                "item_overwhelming_blink",
                "item_arcane_blink",
                "item_swift_blink",
                "earthshaker_enchant_totem",
            }
            movement = (
                event["log_type"] in ("ABILITY", "ITEM")
                and name in MOVEMENT
                and (required_role is None or required_role in event["roles"])
                and (not self_only or "attacker" in event["roles"])
            )
            # Modifier removal is evidence of ending, NOT successful teleport completion.
            teleport_end = (
                event["log_type"] == "MODIFIER_REMOVE"
                and name in {"modifier_teleporting", "modifier_twin_gate_warp_channel"}
                and "target" in event["roles"]
            )
            candidate = (movement or teleport_end) and scope == "core"
            boundary_candidate = (movement or teleport_end) and tick == start
            preceding_candidate = (movement or teleport_end) and start - tolerance <= tick < start
            nearby.append(
                {
                    **event,
                    "scope": scope,
                    "tick_delta_from_end": tick - end,
                    "movement_shortlist": movement,
                    "channelled_use": channel,
                    "teleport_modifier_end": teleport_end,
                    "core_candidate": candidate,
                    "boundary_candidate": boundary_candidate,
                    "preceding_candidate": preceding_candidate,
                }
            )
            if candidate:
                usage[event["source_ref"]] += 1
        life = [
            r
            for r in recoveries
            if r["player_slot"] == jump["player_slot"] and start < r["current"]["tick"] <= end
        ]
        candidates = [e for e in nearby if e["core_candidate"]]
        states = [
            jump[k][0]["life_state"] if len(jump[k]) == 1 else None
            for k in ("previous_states", "current_states")
        ]
        category = (
            "recovery_interval"
            if life
            else "nonliving_endpoint"
            if any(s in (1, 2) for s in states)
            else "core_movement_event"
            if candidates
            else "previous_tick_boundary_event"
            if any(e["boundary_candidate"] for e in nearby)
            else "preceding_movement_context"
            if any(e["preceding_candidate"] for e in nearby)
            else "unresolved"
        )
        result.append(
            dict(
                jump_ref=f"jumps[{i}]",
                player_slot=jump["player_slot"],
                hero_name=players[pid]["hero_name"],
                previous=jump["previous"],
                current=jump["current"],
                distance_native_units=jump["distance_native_units"],
                endpoint_states=states,
                category=category,
                events=nearby,
                recovery_refs=[r["transition_ref"] for r in life],
                candidate_count=len(candidates),
                causal_mechanism_confirmed=False,
            )
        )
    return dict(
        schema_version="replay-jump-events/1",
        match_id=raw["match_id"],
        training_admission=False,
        independent_gameplay_verification=False,
        configuration=dict(
            tolerance_ticks=tolerance,
            channel_lookback_ticks=channel_lookback,
            core_interval="(previous_tick,current_tick]",
            movement_shortlist=sorted(MOVEMENT),
            channelled_shortlist=sorted(CHANNELLED),
        ),
        counts=dict(Counter(r["category"] for r in result)),
        recovery_counts=dict(Counter(r["category"] for r in recoveries)),
        event_types=dict(Counter(e["log_type"] for e in raw["combat_log"])),
        reused_candidate_events={ref: n for ref, n in usage.items() if n > 1},
        multiple_candidate_jumps=sum(r["candidate_count"] > 1 for r in result),
        jumps=result,
        recoveries=recoveries,
    )
