"""Death-risk samples: will this hero die in the next seconds? (track B, U160)

The label is a fact of the replay (the hero's death), so it needs no human definition.
The features use only what the player could know at that second (U6, U55):

* his own state and position, the standing towers, the game clock;
* his allies' positions (shared team vision);
* enemies his team can see right now, and for the others when and where they were last
  seen. Whether an enemy is alive and every hero's level are public (scoreboard).

Never used: positions of enemies his team cannot see, smoke, enemy cooldowns.

Version 2 (2026-11-17) adds, through the optional `context` of `features`:

* his own save means (save-means-v2, U131) learned or carried, and how many are ready
  now (own cooldowns, charges and mana are on his screen);
* his own team's nearest creep wave (own creeps are always in his team's vision);
* his own team's observer wards covering him (vision 1600, lifetime 360 in the game
  files, snapshot 2026-11-17);
* missing enemies with Valve's "Initiator" role label (hero registry; a public label,
  not a user-approved mechanism).

Enemy wards, enemy creep waves in the fog and enemy cooldowns stay out.

`hit_recent` marks samples where an enemy hero already damaged him in the last
`hit_window` seconds: predicting a death then is easy and is no early warning, so the
evaluation reports those samples apart (docs/b2-death-risk-contract.md).
"""

import math
from bisect import bisect_right

from dota_items.data.gank_depth import depth, standing_towers

PARAMS = {
    "horizons": (10, 15, 20),  # label: death within this many seconds; 20 is U115's window
    "step": 5,  # one sample every this many seconds
    "start": 60,
    "hit_window": 3,
    "near": 1500,
    "mid": 3000,
    "far": 20000,  # stands in for "nobody" in distance features
    "age_cap": 120,  # seconds since an enemy was last seen, capped
    "hp_lookback": 5,
}
FEATURES_V1 = (
    "minute",
    "hp",
    "hp_frac",
    "hp_frac_change",
    "mana_frac",
    "level",
    "level_vs_enemies",
    "depth",
    "own_tower_distance",
    "enemy_tower_distance",
    "allies_alive",
    "allies_near",
    "nearest_ally_distance",
    "enemies_alive",
    "enemies_visible",
    "enemies_visible_near",
    "enemies_visible_mid",
    "nearest_visible_enemy_distance",
    "enemies_missing",
    "missing_shortest_age",
    "missing_longest_age",
    "nearest_missing_last_seen_distance",
    "hit_recent",
)
FEATURES_V2_EXTRA = (
    "saves_owned",
    "saves_ready",
    "own_creeps_distance",
    "ahead_of_own_creeps",
    "own_observers_covering",
    "missing_initiators",
    "visible_initiators_mid",
)
FEATURES = FEATURES_V1 + FEATURES_V2_EXTRA
INVENTORY_SLOTS = {str(slot) for slot in range(6)} | {"15"}  # main inventory and TP slot
LANE_TEAM = {2: "radiant", 3: "dire"}
OBSERVER_VISION = 1600  # item_ward_observer vision_range_tooltip (game files 2026-11-17)


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def vitals_row(hero):
    """What is kept of one hero for one second of the parser-v3 state."""
    return (hero.get("hp"), hero.get("max_hp"), hero.get("mana"), hero.get("max_mana"),
            hero.get("level"))  # fmt: skip


def save_state(hero, means):
    """(owned, ready) save means of one parser-v3 hero row (U131 list, own screen only).

    An ability counts when learned, shown and activated; an item when in the main
    inventory or the TP slot. It is ready when off cooldown (or a charge is left for
    abilities) and, for abilities, affordable with his current mana.
    """
    owned = ready = 0
    mana = hero.get("mana") or 0
    for ability in hero.get("abilities") or ():
        if ability.get("name") not in means or not ability.get("level"):
            continue
        if ability.get("hidden") or not ability.get("activated", True):
            continue
        owned += 1
        off = (ability.get("cd") or 0) <= 0 or (ability.get("charges") or 0) > 0
        ready += off and (ability.get("mana_cost") or 0) <= mana
    for slot, item in (hero.get("items") or {}).items():
        if slot not in INVENTORY_SLOTS or item.get("name") not in means:
            continue
        owned += 1
        ready += (item.get("cd") or 0) <= 0
    return owned, ready


def own_waves(fronts, team):
    """Fronts of his own team's creep waves at one second (always in his team's vision)."""
    prefix = LANE_TEAM[team] + "_"
    return [
        wave["front"]
        for lane, wave in (fronts or {}).items()
        if lane.startswith(prefix) and wave and wave.get("front") and wave.get("count")
    ]


def death_times(combat, hero):
    """Seconds at which the real hero died (illusions left out)."""
    return sorted(
        e["time"]
        for e in combat
        if e["payload"].get("log_type") == "DEATH"
        and e["payload"].get("target_name") == hero
        and not e["payload"].get("target_is_illusion")
        and e.get("time") is not None
    )


def hero_hit_seconds(combat, hero, team):
    """Seconds at which an enemy hero damaged `hero`."""
    return {
        e["time"]
        for e in combat
        if e["payload"].get("log_type") == "DAMAGE"
        and e["payload"].get("target_name") == hero
        and team.get(e["payload"].get("attacker_name")) not in (None, team[hero])
        and not e["payload"].get("attacker_is_illusion")
        and e.get("time") is not None
    }


def labels(t, deaths, horizons):
    """{horizon: 1 if he dies in (t, t + horizon]} for a sorted list of death seconds."""
    index = bisect_right(deaths, t)
    nxt = deaths[index] if index < len(deaths) else None
    return {h: int(nxt is not None and nxt - t <= h) for h in horizons}


def features(
    hero, t, tracks, vitals, seen_sorted, zones, tower_deaths, hits, params=PARAMS, context=None
):
    """The feature dict of one living hero at second t, or None when data is missing.

    `seen_sorted` is {(enemy, own team): sorted seconds the team saw him}. `context`
    (version 2, optional) is {"kit": {t: (owned, ready)}, "fronts": {t: lane fronts},
    "wards": own team's observer spans, "initiators": set of hero names}.
    """
    own = tracks[hero]["team"]
    here = tracks[hero]["pos"].get(t)
    mine = vitals[hero].get(t)
    if here is None or mine is None or not mine[1]:
        return None
    hp, max_hp, mana, max_mana, level = mine
    earlier = vitals[hero].get(t - params["hp_lookback"])
    towers = standing_towers(zones, tower_deaths, t)
    tower_distance = {
        side: min(
            (_distance(here, (tw["x"], tw["y"])) for tw in towers if (tw["team"] == own) == side),
            default=params["far"],
        )
        for side in (True, False)
    }
    allies, visible, missing_age, missing_distance, enemy_levels = [], [], [], [], []
    initiators = (context or {}).get("initiators", ())
    missing_initiators = visible_initiators_mid = 0
    for other, track in tracks.items():
        if other == hero:
            continue
        there = track["pos"].get(t)  # None while dead; deaths are public
        if track["team"] == own:
            if there is not None:
                allies.append(_distance(here, there))
            continue
        other_vitals = vitals[other].get(t)
        if other_vitals and other_vitals[4]:
            enemy_levels.append(other_vitals[4])
        if there is None:
            continue
        times = seen_sorted.get((other, own), ())
        index = bisect_right(times, t)
        if index and times[index - 1] == t:
            visible.append(_distance(here, there))
            visible_initiators_mid += other in initiators and visible[-1] <= params["mid"]
            continue
        missing_initiators += other in initiators
        last = times[index - 1] if index else None
        missing_age.append(params["age_cap"] if last is None else min(params["age_cap"], t - last))
        spot = track["pos"].get(last) if last is not None else None
        if spot is not None and t - last <= params["age_cap"]:
            missing_distance.append(_distance(here, spot))
    row = {
        "minute": t / 60,
        "hp": hp,
        "hp_frac": hp / max_hp,
        "hp_frac_change": hp / max_hp - earlier[0] / earlier[1] if earlier and earlier[1] else 0.0,
        "mana_frac": mana / max_mana if max_mana else 0.0,
        "level": level,
        "level_vs_enemies": level - sum(enemy_levels) / len(enemy_levels) if enemy_levels else 0.0,
        "depth": depth(here, own),
        "own_tower_distance": tower_distance[True],
        "enemy_tower_distance": tower_distance[False],
        "allies_alive": len(allies),
        "allies_near": sum(d <= params["near"] for d in allies),
        "nearest_ally_distance": min(allies, default=params["far"]),
        "enemies_alive": len(visible) + len(missing_age),
        "enemies_visible": len(visible),
        "enemies_visible_near": sum(d <= params["near"] for d in visible),
        "enemies_visible_mid": sum(d <= params["mid"] for d in visible),
        "nearest_visible_enemy_distance": min(visible, default=params["far"]),
        "enemies_missing": len(missing_age),
        "missing_shortest_age": min(missing_age, default=0),
        "missing_longest_age": max(missing_age, default=0),
        "nearest_missing_last_seen_distance": min(missing_distance, default=params["far"]),
        "hit_recent": int(any(s in hits for s in range(t - params["hit_window"] + 1, t + 1))),
    }
    if context is None:
        return row
    owned, ready = context["kit"].get(t, (0, 0))
    waves = own_waves(context["fronts"].get(t), own)
    wave = min(waves, key=lambda w: _distance(here, w)) if waves else None
    return row | {
        "saves_owned": owned,
        "saves_ready": ready,
        "own_creeps_distance": _distance(here, wave) if wave else params["far"],
        "ahead_of_own_creeps": depth(here, own) - depth(wave, own) if wave else 0.0,
        "own_observers_covering": sum(
            w["start"] <= t <= w["end"] and _distance(here, (w["x"], w["y"])) <= OBSERVER_VISION
            for w in context["wards"]
        ),
        "missing_initiators": missing_initiators,
        "visible_initiators_mid": visible_initiators_mid,
    }


def samples(
    match_id, hero, tracks, vitals, seen, combat, zones, tower_deaths, last, params=PARAMS,
    context=None,
):  # fmt: skip
    """Rows for one hero of one match: ids, features and one label per horizon."""
    team = {name: track["team"] for name, track in tracks.items()}
    own = team[hero]
    seen_sorted = {
        key: sorted(times) for key, times in seen.items() if key[1] == own and key[0] in team
    }
    deaths = death_times(combat, hero)
    hits = hero_hit_seconds(combat, hero, team)
    rows = []
    for t in range(params["start"], last + 1, params["step"]):
        row = features(
            hero, t, tracks, vitals, seen_sorted, zones, tower_deaths, hits, params, context
        )
        if row is None:
            continue
        found = labels(t, deaths, params["horizons"])
        rows.append(
            {"match_id": match_id, "hero": hero, "t": t, **row}
            | {f"dies_{h}": value for h, value in found.items()}
        )
    return rows
