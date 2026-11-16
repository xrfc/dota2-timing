"""Teleports from the combat log and hero tracks (shared base, gap list item 9, U154).

The combat log records the Town Portal Scroll or Boots of Travel cast but not where the
hero arrives. Parser-v3 positions show it: a teleporting hero jumps far in one second,
usually 4 to 6 seconds after the cast. A cast with no such jump within `MAX_WAIT` seconds
was cancelled or interrupted and is kept with `landed: None`.
"""

import math

TELEPORT_ITEMS = ("item_tpscroll", "item_travel_boots", "item_travel_boots_2")
MAX_WAIT = 10
MIN_JUMP = 1500


def teleports(tracks, combat, max_wait=MAX_WAIT, min_jump=MIN_JUMP):
    """[{hero, team, cast, landed, start, end}] in cast order; `landed` is None if cancelled.

    `tracks` is gank_events.hero_tracks, `combat` the combat log (full or slimmed).
    """
    result = []
    for entry in combat:
        p = entry["payload"]
        hero = p.get("attacker_name")
        if p.get("log_type") != "ITEM" or p.get("inflictor_name") not in TELEPORT_ITEMS:
            continue
        if hero not in tracks or p.get("attacker_is_illusion"):
            continue
        pos, t = tracks[hero]["pos"], entry["time"]
        landed = None
        for step in range(1, max_wait + 1):
            before, after = pos.get(t + step - 1), pos.get(t + step)
            if before and after and math.dist(before, after) >= min_jump:
                landed = t + step
                break
        result.append(
            {
                "hero": hero,
                "team": tracks[hero]["team"],
                "cast": t,
                "landed": landed,
                "start": pos.get(t),
                "end": pos.get(landed) if landed is not None else None,
            }
        )
    return sorted(result, key=lambda r: (r["cast"], r["hero"]))


def arrived_near(teleport_list, hero, place, start, stop, radius):
    """The teleports of `hero` that landed between `start` and `stop` within `radius`."""
    return [
        r
        for r in teleport_list
        if r["hero"] == hero
        and r["landed"] is not None
        and start <= r["landed"] <= stop
        and math.dist(r["end"], place) <= radius
    ]
