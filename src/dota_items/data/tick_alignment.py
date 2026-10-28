"""Conservative tick joins. Omniscient evidence and observer outputs stay separate."""

from bisect import bisect_right
from collections import Counter, defaultdict


def entity(row):
    return row.get("entity_index"), row.get("entity_serial")


def align_player(positions, states, visibility, accepted_refs, pauses=()):
    """Yield (omniscient, observer rows), never interpolate or choose duplicate states.

    Positions carry source_ref/source_tick/time/x/y. States/visibility are raw
    payloads with source_ref. Accepted refs come from unchanged existing cleaning.
    Visible snapshots only disclose positions with a unique same-tick state,
    a matching visibility entity and a retained, unique position sample.
    """
    by_tick = defaultdict(list)
    for row in states:
        by_tick[row["tick"]].append(row)
    vis = defaultdict(list)
    for row in visibility:
        vis[row["tick"]].append(row)
    ticks = sorted(vis)
    counts = Counter(p["source_tick"] for p in positions)
    seconds = Counter(p["time"] for p in positions)
    last = {team: None for team in ("radiant", "dire")}
    for pos in sorted(positions, key=lambda p: p["source_tick"]):
        tick = pos["source_tick"]
        ss = by_tick[tick]
        state = ss[0] if len(ss) == 1 else None
        i = bisect_right(ticks, tick) - 1
        events = vis[ticks[i]] if i >= 0 else []
        signatures = {(entity(e), e.get("radiant_state"), e.get("dire_state")) for e in events}
        event = events[0] if len(signatures) == 1 else None
        flags = []
        if pos["source_ref"] not in accepted_refs:
            flags.append("not_retained_by_existing_cleaning")
        if len(ss) != 1:
            flags.append("state_missing" if not ss else "state_ambiguous")
        if counts[tick] > 1:
            flags.append("duplicate_position_tick")
        if seconds[pos["time"]] > 1:
            flags.append("repeated_game_second")
        paused = any(
            p["start_tick"] <= tick and (p["end_tick"] is None or tick < p["end_tick"])
            for p in pauses
        )
        if paused:
            flags.append("pause")
        matched = (
            state is not None
            and event is not None
            and None not in entity(state)
            and entity(state) == entity(event)
        )
        if not matched:
            flags.append("visibility_identity_unknown_or_ambiguous")
        visibility_states = {
            team: event.get(team + "_state", "unknown") if matched else "unknown" for team in last
        }
        ready = (
            pos["source_ref"] in accepted_refs
            and state is not None
            and counts[tick] == 1
            and state.get("life_state") == 0
            and matched
        )
        omni = {
            **pos,
            "life_state": state.get("life_state") if state else None,
            "state_refs": [r["source_ref"] for r in ss],
            "visibility_refs": [r["source_ref"] for r in events],
            "visibility": visibility_states,
            "quality_flags": flags,
            "state_entity": list(entity(state)) if state else None,
        }
        observers = []
        for team in last:
            current = None
            if ready and visibility_states[team] == "visible":
                current = {"x": pos["x"], "y": pos["y"]}
                last[team] = {"position": dict(current), "source_tick": tick, "time": pos["time"]}
            old = last[team]
            # Do not disclose hidden life state, true position, identity or quality flags.
            observers.append(
                {
                    "match_id": pos["match_id"],
                    "player_slot": pos["player_slot"],
                    "hero_id": pos["hero_id"],
                    "observer_team": team,
                    "source_tick": tick,
                    "time": pos["time"],
                    "visibility": visibility_states[team],
                    "current_position": current,
                    "visible_life_state": state.get("life_state")
                    if matched and visibility_states[team] == "visible"
                    else None,
                    "last_seen": old,
                    "seconds_since_last_seen": pos["time"] - old["time"]
                    if old and pos["time"] is not None and old["time"] is not None
                    else None,
                    "ticks_since_last_seen": tick - old["source_tick"] if old else None,
                }
            )
        yield omni, observers
