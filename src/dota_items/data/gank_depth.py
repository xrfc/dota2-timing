"""Is this episode a gank at all? Classes on top of the four conditions (U137-U140).

The user reviews sampled episodes and names what the four-condition rule gets wrong. Four
classes are taken out of "ganked", in this order:

* high_ground   the episode starts inside either base: within the quarter circle around
                the fountain that reaches the furthest tier-3 tower plus its attack range
                (U138, redefined by the user in U140). Not considered.
* laning        before `laning_end` and every attacker belongs to the victim's own lane, so
                nobody came from another lane (U140). Not considered.
* after_fight   the episode follows a skirmish he was part of (U141): in the `fight_lookback`
                seconds before t0 he traded damage with an enemy hero and either a hero
                died near him or heroes of both sides stood around him. The winners
                running down a straggler is "keeping", not a gank. Not considered.
                Two exceptions (U142): with `teamfight_heroes` or more heroes around him
                it is "teamfight" (he died in a team fight, not considered); and if he
                closed the distance himself inside the enemy's area it is overextended
                whether or not he could see them (the fight was over and he pressed on).
* overextended  he could see them and went anyway (U137, rule revised after 23 judgments):
                at least one attacker was visible to his team for `visible_share` of the
                `lookback` seconds, and he either closed most of the distance himself or
                was in the enemy's area (nearest standing tower is theirs, or enemy jungle).
                Attackers nobody could see make it a gank however deep he stood.
                During the laning minutes only attackers from other lanes count as
                "seen": the lane opponent is always visible, the rotation is the gank (U141).

Seven signals are recorded for every episode, at its start (t0) or the seconds before:

* enemy_tower_area   the nearest standing tower belongs to the enemy
* enemy_jungle       within `camp_radius` of a neutral camp on the enemy's side
* victim_approached  in the `lookback` seconds before t0 the victim closed more of the
                     distance to the attackers than the attackers closed to him
* saw_attackers      an attacker was visible to the victim's team most of that time
* struck_first       the victim attacked or targeted an enemy hero before being hit
* beyond_creeps      further toward the enemy base than his own nearest creep wave
* alone_ahead        further toward the enemy base than every living ally, by a margin

The last three are recorded and shown but do not decide the class: on the judged episodes
they did not separate ganks from overextension. "Toward the enemy base" is measured along
the fountain-to-fountain diagonal, which grows monotonically along all three lanes.
Thresholds and the combination are the assistant's, tuned on non-holdout matches only.
"""

import math
from bisect import bisect_left, bisect_right

SIGNALS = (
    "enemy_tower_area",
    "enemy_jungle",
    "victim_approached",
    "saw_attackers",
    "struck_first",
    "beyond_creeps",
    "alone_ahead",
)
PARAMS = {
    "lookback": 10,  # seconds before t0 for approach and first strike
    "camp_radius": 1200,
    "approach_share": 0.5,
    "creep_margin": 300,
    "ally_margin": 1500,
    "visible_share": 0.5,  # of the lookback seconds an attacker was visible to his team
    "tower_range": 700,  # tier-3 attack range, added to the high-ground radius (U140)
    "laning_end": 600,  # U140: first ten minutes
    "fight_lookback": 30,  # U141: seconds before t0 searched for an earlier skirmish
    "fight_radius": 1600,  # heroes this close to the victim are in the skirmish
    "fight_death_radius": 2500,
    "fight_heroes": 4,  # victim included, with at least two enemies
    "teamfight_heroes": 6,  # U142: this many around him before t0 make it a team fight
}
TERRITORY_SIGNALS = ("enemy_tower_area", "enemy_jungle")
TOWER_PREFIXES = ("npc_dota_goodguys_tower", "npc_dota_badguys_tower")
LANE_TEAM = {2: "radiant", 3: "dire"}


def depth(pos, team):
    """Distance past the map's centre line toward the enemy base (negative: own side)."""
    along = (pos[0] + pos[1] - 32768) / math.sqrt(2)
    return along if team == 2 else -along


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def high_ground_side(pos, zones, params=PARAMS):
    """Team (2 or 3) whose base `pos` is inside, or None (U140).

    A base is the quarter circle around the fountain whose radius reaches the furthest
    tier-3 tower of that side plus the tower's attack range.
    """
    for fountain in zones["fountains"]:
        centre = (fountain["x"], fountain["y"])
        reach = max(
            _distance(centre, (tower["x"], tower["y"]))
            for tower in zones["towers"]
            if tower["team"] == fountain["team"] and "tower3" in tower["name"]
        )
        if _distance(pos, centre) <= reach + params["tower_range"]:
            return fountain["team"]
    return None


def hero_lanes(tracks):
    """{hero: lane he spent most of the laning minutes in} (gank_events.lane_of)."""
    from collections import Counter

    from dota_items.data.gank_events import LANE_SECONDS, lane_of

    lanes = {}
    for hero, track in tracks.items():
        seen = Counter(
            lane_of(*pos)
            for t, pos in track["pos"].items()
            if LANE_SECONDS[0] <= t <= LANE_SECONDS[1]
        )
        lanes[hero] = seen.most_common(1)[0][0] if seen else None
    return lanes


def tower_deaths(combat):
    """{combat-log tower name: sorted death times}."""
    result = {}
    for entry in combat:
        p = entry["payload"]
        name = p.get("target_name") or ""
        if p.get("log_type") == "DEATH" and name.startswith(TOWER_PREFIXES):
            result.setdefault(name, []).append(entry["time"])
    return {name: sorted(times) for name, times in result.items()}


def standing_towers(zones, deaths, second):
    """Towers still standing at `second`. Tier-4 pairs share one log name (see zones notes)."""
    fallen = {}
    standing = []
    for tower in zones["towers"]:
        log_name = tower["name"]
        if "tower4" in log_name:
            log_name = log_name.rsplit("_", 1)[0]
        dead = [t for t in deaths.get(log_name, ()) if t <= second]
        used = fallen.get(log_name, 0)
        if used < len(dead):
            fallen[log_name] = used + 1
            continue
        standing.append(tower)
    return standing + list(zones.get("forts", ()))


def _first_strike(combat, victim, team, t0, lookback):
    """The victim's first attack or targeted cast on an enemy hero before he was hit."""
    first_hit = None
    strikes = []
    for entry in combat:
        t = entry.get("time")
        if t is None or not t0 - lookback <= t <= t0:
            continue
        p = entry["payload"]
        tick = p.get("tick", 0)
        source, target = p.get("attacker_name"), p.get("target_name")
        if p.get("attacker_is_illusion") or p.get("target_is_illusion"):
            continue
        kind = p.get("log_type")
        if kind == "DAMAGE" and target == victim and team.get(source, team[victim]) != team[victim]:
            if t == t0 and p.get("attacker_is_hero") and (first_hit is None or tick < first_hit):
                first_hit = tick
        elif source == victim and target in team and team[target] != team[victim]:
            # A plain attack has no inflictor; damage with one may be a passive reflecting a
            # hit he took, so only attacks and deliberate casts count as striking.
            if (kind == "DAMAGE" and not p.get("inflictor_name")) or kind in ("ABILITY", "ITEM"):
                strikes.append((tick, t, p.get("inflictor_name") or "attack", target))
    strikes = sorted(s for s in strikes if first_hit is None or s[0] < first_hit)
    if not strikes:
        return None
    _, t, name, target = strikes[0]
    return {"t": t, "name": name, "target": target}


def recent_fight(victim, t0, tracks, combat, params=PARAMS):
    """The skirmish the victim was in shortly before t0, or None (U141).

    He must have traded damage with an enemy hero in the `fight_lookback` seconds before
    t0, and in those seconds either a hero died within `fight_death_radius` of him or at
    least `fight_heroes` heroes (he included, two or more of them enemies) stood within
    `fight_radius` of him.
    """
    team = {hero: track["team"] for hero, track in tracks.items()}
    own = team[victim]
    start = t0 - params["fight_lookback"]
    traded, deaths = [], []
    for entry in combat:
        t = entry.get("time")
        if t is None or not start <= t < t0:
            continue
        p = entry["payload"]
        source, target = p.get("attacker_name"), p.get("target_name")
        if p.get("attacker_is_illusion") or p.get("target_is_illusion"):
            continue
        kind = p.get("log_type")
        if kind == "DAMAGE" and victim in (source, target):
            other = target if source == victim else source
            if other in team and team[other] != own:
                traded.append(t)
        elif kind == "DEATH" and target in team and target != victim:
            here, there = tracks[victim]["pos"].get(t), tracks[target]["pos"].get(t)
            if here and there and _distance(here, there) <= params["fight_death_radius"]:
                deaths.append({"t": t, "hero": target})
    if not traded:
        return None
    crowd = 0
    for t in range(start, t0):
        here = tracks[victim]["pos"].get(t)
        if here is None:
            continue
        near = [
            hero
            for hero, track in tracks.items()
            if hero != victim
            and t in track["pos"]
            and _distance(here, track["pos"][t]) <= params["fight_radius"]
        ]
        enemies = sum(team[hero] != own for hero in near)
        if enemies >= 2 and len(near) + 1 >= params["fight_heroes"]:
            crowd = max(crowd, len(near) + 1)
    if not deaths and not crowd:
        return None
    return {"first_trade": min(traded), "deaths": deaths, "most_heroes": crowd}


def depth_signals(
    episode, tracks, combat, fronts, zones, deaths, seen=None, lanes=None, params=PARAMS
):
    """The signals and the numbers behind them for one episode.

    `tracks` is gank_events.hero_tracks, `fronts` the parser-v3 lane fronts at t0 (may be
    None), `deaths` is tower_deaths(combat), `seen` is gank_events.visibility_table and
    `lanes` is hero_lanes(tracks). A signal is None when it cannot be computed.
    """
    victim, t0 = episode["victim"], episode["t0"]
    team = {hero: track["team"] for hero, track in tracks.items()}
    own = team[victim]
    here = tracks[victim]["pos"].get(t0)
    if here is None:
        return {
            "signals": dict.fromkeys(SIGNALS),
            "count": None,
            "high_ground": None,
            "laning": None,
            "after_fight": None,
        }
    numbers = {"depth": round(depth(here, own))}
    numbers["after_fight"] = recent_fight(victim, t0, tracks, combat, params)
    numbers["high_ground"] = high_ground_side(here, zones, params)
    if lanes is None or lanes.get(victim) is None:
        numbers["laning"] = None
    else:
        numbers["attackers_from_other_lanes"] = sorted(
            a for a in episode["attackers"] if lanes.get(a) != lanes[victim]
        )
        numbers["laning"] = t0 < params["laning_end"] and not numbers["attackers_from_other_lanes"]
    signals = {}

    if seen is None:
        signals["saw_attackers"] = None
    else:
        span = range(t0 - params["lookback"], t0)
        visible = {
            attacker: sum(t in seen.get((attacker, own), ()) for t in span) / len(span)
            for attacker in episode["attackers"]
        }
        numbers["attackers_visible"] = sorted(
            a for a, share in visible.items() if share >= params["visible_share"]
        )
        counted = numbers["attackers_visible"]
        if t0 < params["laning_end"] and numbers.get("attackers_from_other_lanes"):
            # U141: in lane the opponent is always in sight; what matters is the rotation.
            counted = [a for a in counted if a in numbers["attackers_from_other_lanes"]]
        signals["saw_attackers"] = bool(counted)

    towers = standing_towers(zones, deaths, t0)
    nearest = min(towers, key=lambda tw: _distance(here, (tw["x"], tw["y"])), default=None)
    if nearest is None:
        signals["enemy_tower_area"] = None
    else:
        signals["enemy_tower_area"] = nearest["team"] != own
        numbers["nearest_tower"] = nearest["name"]
        numbers["nearest_tower_distance"] = round(_distance(here, (nearest["x"], nearest["y"])))

    camp = min(zones["camps"], key=lambda c: _distance(here, (c["x"], c["y"])))
    camp_distance = _distance(here, (camp["x"], camp["y"]))
    signals["enemy_jungle"] = camp["team"] != own and camp_distance <= params["camp_radius"]
    numbers["nearest_camp"] = {
        "id": camp["id"],
        "team": camp["team"],
        "distance": round(camp_distance),
    }

    before = t0 - params["lookback"]
    start = tracks[victim]["pos"].get(before)
    victim_closed = attackers_closed = 0.0
    measured = 0
    for attacker in episode["attackers"]:
        a0, a1 = tracks[attacker]["pos"].get(before), tracks[attacker]["pos"].get(t0)
        if start is None or a0 is None or a1 is None:
            continue
        measured += 1
        victim_closed += max(0.0, _distance(start, a0) - _distance(here, a0))
        attackers_closed += max(0.0, _distance(a0, start) - _distance(a1, start))
    if measured and victim_closed + attackers_closed > 0:
        share = victim_closed / (victim_closed + attackers_closed)
        signals["victim_approached"] = share > params["approach_share"]
        numbers["victim_closing_share"] = round(share, 2)
    else:
        signals["victim_approached"] = None

    strike = _first_strike(combat, victim, team, t0, params["lookback"])
    signals["struck_first"] = strike is not None
    numbers["first_strike"] = strike

    prefix = LANE_TEAM[own] + "_"
    waves = [
        wave["front"]
        for lane, wave in (fronts or {}).items()
        if lane.startswith(prefix) and wave and wave.get("front")
    ]
    if waves:
        wave = min(waves, key=lambda w: _distance(here, w))
        ahead = depth(here, own) - depth(wave, own)
        signals["beyond_creeps"] = ahead > params["creep_margin"]
        numbers["beyond_creeps"] = round(ahead)
        numbers["creep_wave_distance"] = round(_distance(here, wave))
    else:
        signals["beyond_creeps"] = None

    allies = [
        track["pos"][t0]
        for hero, track in tracks.items()
        if hero != victim and track["team"] == own and t0 in track["pos"]
    ]
    if allies:
        ahead = depth(here, own) - max(depth(pos, own) for pos in allies)
        signals["alone_ahead"] = ahead > params["ally_margin"]
        numbers["ahead_of_allies"] = round(ahead)
    else:
        signals["alone_ahead"] = None

    return {
        "signals": {name: signals[name] for name in SIGNALS},
        "count": sum(bool(signals[name]) for name in SIGNALS),
        **numbers,
    }


def classify(result, params=PARAMS):
    """The class that takes an episode out of "ganked", or None."""
    if result.get("high_ground"):
        return "high_ground"
    if result.get("laning"):
        return "laning"
    signals = result["signals"]
    fight = result.get("after_fight")
    if fight:
        if fight["most_heroes"] >= params["teamfight_heroes"]:
            return "teamfight"  # U142: he died in or right out of a team fight
        if signals["victim_approached"] and any(signals[name] for name in TERRITORY_SIGNALS):
            return "overextended"  # U142: the fight was over and he pressed on (D19)
        return "after_fight"
    if signals["saw_attackers"] and (
        signals["victim_approached"] or any(signals[name] for name in TERRITORY_SIGNALS)
    ):
        return "overextended"
    return None


def annotate(
    episodes, tracks, combat, fronts_by_second, zones, smoke=None, seen=None, params=PARAMS
):
    """Add depth signals to each episode and move ganks that are not ganks to their class.

    `rule_label` keeps the four-condition label (U115); `label` becomes "high_ground",
    "laning", "teamfight", "after_fight" or "overextended" where classify says so. `smoke` is
    gank_review.smoke_intervals output, `seen` is gank_events.visibility_table.
    """
    from dota_items.data.gank_review import smoked_attackers

    deaths = tower_deaths(combat)
    lanes = hero_lanes(tracks)
    # The signals only read the seconds before t0; slicing once per episode instead of
    # scanning the whole log keeps a rule change cheap to rerun.
    timed = sorted((e for e in combat if e.get("time") is not None), key=lambda e: e["time"])
    times = [e["time"] for e in timed]
    reach = max(params["lookback"], params["fight_lookback"])
    for episode in episodes:
        t0 = episode["t0"]
        fronts = fronts_by_second.get(t0)
        window = timed[bisect_left(times, t0 - reach) : bisect_right(times, t0)]
        result = depth_signals(episode, tracks, window, fronts, zones, deaths, seen, lanes, params)
        episode["depth"] = result
        episode["rule_label"] = episode["label"]
        if episode["is_gank"]:
            episode["label"] = classify(result, params) or episode["label"]
        if smoke is not None:
            episode["smoked_attackers"] = smoked_attackers(
                smoke, episode["attackers"], episode["t0"]
            )
    return episodes
