"""B0: find "被抓" (gank) episodes in one match (U115, U116, U131).

Definition (user): a player is ganked when at least two enemy heroes catch him outside a
big fight, coming from out of his team's sight while he is far from teammates, and he dies
or has to use a save (his own, or a teammate's on him) to get away. Window 20 s, a new
episode needs 10 s without enemy-hero damage. Thresholds are assistant proposals the user
accepted for a first pass (U131); they are parameters, and positions are a parameter too
(U116: evaluate 1 and 5 now, keep 2/3/4 open).

Inputs are omniscient replay data: per-second hero state from parser v3, the combat log,
and per-team hero visibility from the existing parse. Contract: docs/b0-gank-rules.md.
"""

import math
from collections import Counter

from dota_items.sources.gem_capture_v3 import lane_of

SCHEMA = "gank-episodes/1"
SAVE_MEANS_SCHEMA = "save-means/1"

PARAMS = {
    "positions": (1, 5),  # U115/U116; 2/3/4 are a TODO
    "window": 20,  # U115
    "quiet_gap": 10,  # U131 q4
    "min_enemies": 2,  # U115
    "fight_radius": 1600,  # U131 q3
    "fight_max_heroes": 6,
    "fight_max_allies": 2,  # including the victim
    "unseen_lookback": 5,
    "ally_distance": {1: 1500, 2: 1500, 3: 1500, 4: 1500, 5: 1500},  # per position (U116)
    "tp_jump": 2000,  # a TP counts only when the hero actually moved this far
    "tp_wait": 8,
}

# U131: group A all count; from group B haste (a), basic dispel (b), illusions (c) and
# spell block (e) count; damage block (d) does not.
SAVE_MECHANISMS = {
    "self_mobility": "A",
    "invisibility": "A",
    "invulnerable_untargetable": "A",
    "cyclone_banish": "A",
    "debuff_immunity": "A",
    "death_prevention": "A",
    "ethereal": "A",
    "applies_strong_dispel": "A",
    "haste": "B-a",
    "applies_basic_dispel": "B-b",
    "illusions": "B-c",
    "spell_block": "B-e",
}
EXCLUDED_MECHANISMS = {"damage_block": "U131: 护盾/减伤不算"}
# Assistant choice: items whose *active* gives movement speed. Items with only passive
# movement speed (boots, Power Treads toggling, Sange and Yasha...) are not a save cast.
ACTIVE_HASTE_ITEMS = {
    "ancient_janggo",
    "boots_of_bearing",
    "crellas_crozier",
    "disperser",
    "glimmer_cape",
    "invis_sword",
    "mask_of_madness",
    "phase_boots",
    "silver_edge",
    "smoke_of_deceit",
    "solar_crest",
    "swift_blink",
}
TELEPORT_ITEMS = {"item_tpscroll", "item_travel_boots", "item_travel_boots_2"}
TEAM_SAFELANE = {2: "bot", 3: "top"}  # Radiant bottom, Dire top
POSITION_MIN_GAP = 25  # U8: 15-minute last-hit gap below this -> position unknown
LANE_SECONDS = (60, 600)


def build_save_means(kb):
    """Abilities and items that count as a save (U131), keyed by combat-log name."""
    haste_abilities = set(kb.trait_subject_filter("dispellable_save").get("haste", []))
    means = {}
    for mechanism, group in SAVE_MECHANISMS.items():
        for fact in kb.subjects_with(mechanism):
            subject = fact["subject"]
            if fact["is_ability"]:
                targeting = kb.ability_targeting(subject)
                if targeting["passive"] or targeting["target_team"] == 2:
                    continue
                if mechanism == "haste" and subject not in haste_abilities:
                    continue
                name = subject
            else:
                if mechanism == "haste" and subject not in ACTIVE_HASTE_ITEMS:
                    continue
                name = f"item_{subject}"
            entry = means.setdefault(
                name,
                {
                    "name": name,
                    "zh": fact["subject_zh"],
                    "kind": "ability" if fact["is_ability"] else "item",
                    "mechanisms": [],
                    "groups": [],
                },
            )
            if mechanism not in entry["mechanisms"]:
                entry["mechanisms"].append(mechanism)
            if group not in entry["groups"]:
                entry["groups"].append(group)
    return {
        "schema": SAVE_MEANS_SCHEMA,
        "decision": "U131",
        "knowledge": kb.version,
        "mechanisms": SAVE_MECHANISMS,
        "excluded": EXCLUDED_MECHANISMS,
        "active_haste_items": sorted(ACTIVE_HASTE_ITEMS),
        "teleport_items": sorted(TELEPORT_ITEMS),
        "rule_zh": "主动施放（战斗日志有施放记录）；技能排除被动和只能指向敌人的；"
        "加速技能只算U121的16个；装备的加速只算主动效果带加速的；回城要真的传走才算。",
        "means": dict(sorted(means.items())),
    }


# Per-match tables ----------------------------------------------------------------------
def hero_tracks(rows):
    """{hero: {"team", "player_id", "pos": {t: (x, y)}}} for living heroes per second."""
    tracks = {}
    for row in rows:
        for h in row["heroes"]:
            track = tracks.setdefault(
                h["hero"], {"team": h["team"], "player_id": h["player_id"], "pos": {}}
            )
            if h.get("life_state") == 0 and h.get("pos"):
                track["pos"][row["t"]] = tuple(h["pos"])
    return tracks


def visibility_table(events, last_second):
    """{(hero, team): set of seconds the team could see the hero} from state-change events."""
    seen = {}
    changes = sorted(events, key=lambda e: e["time"])
    state = {}
    by_time = {}
    for e in changes:
        by_time.setdefault(e["time"], []).append(e["payload"])
    times = sorted(by_time)
    index = 0
    start = times[0] if times else 0
    for t in range(start, last_second + 1):
        while index < len(times) and times[index] <= t:
            for p in by_time[times[index]]:
                state[(p["hero_name"], 2)] = p["radiant_state"] == "visible"
                state[(p["hero_name"], 3)] = p["dire_state"] == "visible"
            index += 1
        for key, visible in state.items():
            if visible:
                seen.setdefault(key, set()).add(t)
    return seen


def infer_positions(tracks, last_hits_15):
    """U8 safelane rule on replay data: the two heroes of a team who spent most of 1-10 min
    in their safelane; more 15-minute last hits is position 1, fewer is 5, gap >= 25."""
    positions = {hero: None for hero in tracks}
    by_team = {}
    for hero, track in tracks.items():
        lanes = Counter(
            lane_of(*p) for t, p in track["pos"].items() if LANE_SECONDS[0] <= t <= LANE_SECONDS[1]
        )
        if lanes and lanes.most_common(1)[0][0] == TEAM_SAFELANE.get(track["team"]):
            by_team.setdefault(track["team"], []).append(hero)
    for heroes in by_team.values():
        if len(heroes) != 2 or any(last_hits_15.get(h) is None for h in heroes):
            continue
        high, low = sorted(heroes, key=lambda h: -last_hits_15[h])
        if last_hits_15[high] - last_hits_15[low] >= POSITION_MIN_GAP:
            positions[high], positions[low] = 1, 5
    return positions


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _teleported(track, t, params):
    """True when the hero jumped at least tp_jump within tp_wait seconds after t."""
    before = track["pos"].get(t)
    if before is None:
        return False
    for s in range(t + 1, t + params["tp_wait"] + 1):
        after = track["pos"].get(s)
        if after is not None and _distance(before, after) >= params["tp_jump"]:
            return True
    return False


def detect_ganks(match_id, tracks, combat, seen, positions, save_means, params=PARAMS):
    """Every candidate episode for evaluated positions, with each condition as a flag."""
    team = {h: tr["team"] for h, tr in tracks.items()}
    hits, deaths, casts = {}, {}, []
    for e in combat:
        p = e["payload"]
        kind = p.get("log_type")
        if kind == "DAMAGE" and p.get("attacker_is_hero") and not p.get("attacker_is_illusion"):
            victim, attacker = p.get("target_name"), p.get("attacker_name")
            if (
                victim in team
                and attacker in team
                and not p.get("target_is_illusion")
                and team[attacker] != team[victim]
            ):
                hits.setdefault(victim, []).append((e["time"], attacker))
        elif kind == "DEATH" and p.get("target_name") in team and not p.get("target_is_illusion"):
            deaths.setdefault(p["target_name"], []).append(e["time"])
        elif kind in ("ABILITY", "ITEM") and p.get("inflictor_name") in save_means:
            if p.get("attacker_name") in team and not p.get("attacker_is_illusion"):
                casts.append(
                    (e["time"], p["attacker_name"], p.get("target_name") or "", p["inflictor_name"])
                )
    episodes = []
    for victim, events in hits.items():
        position = positions.get(victim)
        if position not in params["positions"]:
            continue
        events.sort()
        last = None
        for t0, _ in events:
            if last is not None and t0 - last < params["quiet_gap"]:
                last = t0
                continue
            last = t0
            episodes.append(
                _episode(
                    match_id,
                    victim,
                    position,
                    t0,
                    events,
                    deaths.get(victim, []),
                    casts,
                    tracks,
                    team,
                    seen,
                    params,
                )
            )
    return sorted(episodes, key=lambda e: (e["t0"], e["victim"]))


def _episode(match_id, victim, position, t0, events, deaths, casts, tracks, team, seen, params):
    window_end = t0 + params["window"]
    died = next((d for d in deaths if t0 <= d <= window_end), None)
    end = died if died is not None else window_end
    attackers = sorted({a for t, a in events if t0 <= t <= end})
    own_team = team[victim]
    self_saves, ally_saves = [], []
    for t, caster, target, name in casts:
        if not t0 <= t <= end:
            continue
        if name in TELEPORT_ITEMS and not _teleported(tracks[caster], t, params):
            continue
        if caster == victim and (not target or team.get(target, own_team) == own_team):
            self_saves.append({"t": t, "name": name})
        elif caster != victim and team[caster] == own_team and target == victim:
            ally_saves.append({"t": t, "name": name, "by": caster})
    if died is not None:
        outcome = "death"
    elif self_saves and ally_saves:
        outcome = "self_and_ally_save"
    elif self_saves:
        outcome = "self_save"
    elif ally_saves:
        outcome = "ally_save"
    else:
        outcome = "none"
    victim_pos = tracks[victim]["pos"]
    most_heroes = most_allies = 0
    for t in range(t0, end + 1):
        centre = victim_pos.get(t)
        if centre is None:
            continue
        near = [
            h
            for h, tr in tracks.items()
            if t in tr["pos"] and _distance(tr["pos"][t], centre) <= params["fight_radius"]
        ]
        most_heroes = max(most_heroes, len(near))
        most_allies = max(most_allies, sum(team[h] == own_team for h in near))
    unseen = sorted(
        a
        for a in attackers
        if any(
            t not in seen.get((a, own_team), ()) for t in range(t0 - params["unseen_lookback"], t0)
        )
    )
    start = victim_pos.get(t0)
    ally_gap = (
        min(
            (
                _distance(tr["pos"][t0], start)
                for h, tr in tracks.items()
                if h != victim and team[h] == own_team and t0 in tr["pos"]
            ),
            default=math.inf,
        )
        if start
        else None
    )
    flags = {
        "enough_enemies": len(attackers) >= params["min_enemies"],
        "not_big_fight": most_heroes <= params["fight_max_heroes"]
        and most_allies <= params["fight_max_allies"],
        "from_unseen": bool(unseen),
        "far_from_allies": ally_gap is not None and ally_gap >= params["ally_distance"][position],
        "paid": outcome != "none",
    }
    return {
        "match_id": match_id,
        "victim": victim,
        "player_id": tracks[victim]["player_id"],
        "position": position,
        "t0": t0,
        "end": end,
        "attackers": attackers,
        "unseen_attackers": unseen,
        "outcome": outcome,
        "self_saves": self_saves,
        "ally_saves": ally_saves,
        "most_heroes_near": most_heroes,
        "most_allies_near": most_allies,
        "nearest_ally": None if ally_gap in (None, math.inf) else round(ally_gap),
        "flags": flags,
        "is_gank": all(flags.values()),
    }


def summarize(episodes, matches):
    ganks = [e for e in episodes if e["is_gank"]]
    failing = Counter(k for e in episodes for k, v in e["flags"].items() if not v)
    return {
        "schema": SCHEMA,
        "matches": matches,
        "episodes": len(episodes),
        "ganks": len(ganks),
        "ganks_per_player_match": round(len(ganks) / max(1, 2 * 2 * matches), 2),
        "by_position": dict(Counter(e["position"] for e in ganks)),
        "by_outcome": dict(Counter(e["outcome"] for e in ganks)),
        "condition_failures": dict(failing),
        "only_one_failure": dict(
            Counter(
                next(k for k, v in e["flags"].items() if not v)
                for e in episodes
                if sum(not v for v in e["flags"].values()) == 1
            )
        ),
    }
