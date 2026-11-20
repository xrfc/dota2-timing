"""Exploratory position-one lane review. Keep decision evidence separate from later observations."""

from bisect import bisect_right
from itertools import pairwise
from math import dist

from dota_items.data.death_risk import LANE_TEAM, save_state
from dota_items.data.gank_depth import depth
from dota_items.data.unit_state import decode

ACTION_SECONDS = 6
OUTCOME_SECONDS = 20
REPEAT_SECONDS = 120
START_SECOND = 900  # Position inference uses last hits through minute 15.


def farm_seconds(events, hero, team):
    """Seconds of own non-illusion last hits on opposing melee/ranged/flagbearer lane creeps."""
    prefix = "npc_dota_creep_badguys_" if team == 2 else "npc_dota_creep_goodguys_"
    seconds = []
    for event in events:
        p = event["payload"]
        if p.get("log_type") != "DEATH" or p.get("attacker_name") != hero:
            continue
        target = p.get("target_name") or ""
        if (
            not p.get("attacker_is_illusion")
            and target.startswith(prefix)
            and target[len(prefix) :].split("_")[0] in {"melee", "ranged", "flagbearer"}
        ):
            seconds.append(event["time"])
    return sorted(seconds)


def lane_at(fronts, team, point):
    waves = [
        (dist(point, wave["front"]), lane.split("_", 1)[1], wave["front"])
        for lane, wave in fronts.items()
        if lane.startswith(LANE_TEAM[team] + "_")
        and wave
        and wave.get("count")
        and wave.get("front")
    ]
    if waves:
        distance, lane, front = min(waves)
        if distance <= 1000:
            return lane, front
    return None


def evidence_at(tracks, visibility, hero, t):
    """Only read enemy coordinates at seconds when visible to the player's team."""
    own = tracks[hero]
    here = own["pos"].get(t)
    if here is None:
        return None
    enemies, allies, markers = [], [], [{"hero": hero, "side": "self", "pos": here}]
    for name, track in sorted(tracks.items()):
        if name == hero:
            continue
        if track["team"] == own["team"]:
            if t in track["pos"]:
                allies.append((round(dist(here, track["pos"][t])), name))
                markers.append({"hero": name, "side": "ally", "pos": track["pos"][t]})
            continue
        times = visibility.get((name, own["team"]), ())
        i = bisect_right(times, t)
        last = times[i - 1] if i else None
        location = track["pos"].get(t) if last == t else None
        if location is not None:
            markers.append({"hero": name, "side": "enemy", "pos": location})
        enemies.append(
            {
                "hero": name,
                "last_seen": last,
                "distance": round(dist(here, location)) if location is not None else None,
            }
        )
    return {"t": t, "markers": markers, "enemies": enemies, "ally": min(allies) if allies else None}


def assess(frame, state):
    """Provisional rubric for staying at the wave; returns reasons available at decision time."""
    states = decode(state.get("unit_state_raw"))
    if states is None or {"stunned", "hexed", "rooted"} & set(states):
        return "unknown", "移动状态缺失或受到控制，无法确认可以安全转身。"
    nearby = [e for e in frame["enemies"] if e["distance"] is not None and e["distance"] <= 1600]
    missing = sum(
        e["last_seen"] is None or frame["t"] - e["last_seen"] >= 10 for e in frame["enemies"]
    )
    ally = frame["ally"]
    if nearby and (not ally or ally[0] >= 1500):
        return (
            "retreat",
            "己方视野内有敌人距你不超过 1600，最近的存活队友也在 1500 以外或没有队友在场。"
            "继续补兵会延长暴露时间。",
        )
    if missing >= 2 and (not ally or ally[0] >= 1500):
        return (
            "retreat",
            "至少两名敌人已超过 10 秒没有露头或从未被看到，身边 1500 内没有存活队友。"
            "下一次补刀需要承担敌人可能靠近的风险。",
        )
    if (
        ally
        and ally[0] <= 1000
        and not nearby
        and len(frame["enemies"]) == 5
        and all(e["distance"] is not None for e in frame["enemies"])
    ):
        return (
            "farm",
            "1000 内有存活队友，五名敌人当前都有可见位置，当前没有看到 1600 内的敌人。"
            "短留收线有视野和支援依据。",
        )
    return "unknown", "当前可见敌情和队友距离不足以区分短留与后撤的收益。"


def observe_action(track, hits, team, t, front):
    """Short movement/last-hit window; a proxy for action, not player intent."""
    stop = t + ACTION_SECONDS
    path = [track.get(s) for s in range(t, stop + 1)]
    farmed = any(t < sec <= stop for sec in hits)
    if any(p is None for p in path) or any(dist(a, b) > 700 for a, b in pairwise(path)):
        return "unknown", "窗口内位置中断或突变，无法确认走位。"
    pulled_back = (
        depth(path[0], team) - depth(path[-1], team) >= 350
        and dist(path[-1], front) - dist(path[0], front) >= 250
    )
    if pulled_back and farmed:
        return "unknown", "期间既有线上补刀又有后撤位移，不能归为单一动作。"
    if pulled_back:
        return "retreat", "向己方一侧移动至少 350，并与起点时的己方兵线前沿拉开至少 250。"
    if farmed:
        return "farm", "随后 6 秒内再次补到了敌方线上小兵。"
    return "unknown", "未观察到再次补刀或足够明确的后撤位移。"


def make_cases(match, mid, hero, hits, visibility, states, means, deaths):
    team = match["tracks"][hero]["team"]
    track = match["tracks"][hero]["pos"]
    recent_hits = {
        e["time"]
        for e in match["combat"]
        if e["payload"].get("log_type") == "DAMAGE"
        and e["payload"].get("target_name") == hero
        and e["payload"].get("attacker_is_hero")
        and not e["payload"].get("target_is_illusion")
    }
    next_time = START_SECOND
    for t in hits:
        if t < next_time or t not in track or t not in states:
            continue
        if any(s in recent_hits for s in range(t - 4, t + 1)):
            continue
        wave = lane_at(match["fronts"].get(t) or {}, team, track[t])
        if wave is None:
            continue
        next_time = t + REPEAT_SECONDS
        lane, front = wave
        history = [
            frame
            for sec in (t - 10, t - 5, t)
            if (frame := evidence_at(match["tracks"], visibility, hero, sec)) is not None
        ]
        for frame in history:
            waves = match["fronts"].get(frame["t"]) or {}
            own_wave = waves.get(f"{LANE_TEAM[team]}_{lane}") or {}
            frame["wave"] = own_wave.get("front")
        state = states[t]
        owned, ready = save_state(state, means)
        abilities = (a["name"] for a in state.get("abilities") or [] if a.get("name"))
        items = (i["name"] for i in (state.get("items") or {}).values() if i.get("name"))
        ready_names = [
            name
            for name in sorted(set(abilities) | set(items))
            if name in means and save_state(state, {name})[1]
        ]
        lean, reason = assess(history[-1], state)
        evidence = {
            "match": mid,
            "hero": hero,
            "t": t,
            "lane": lane,
            "history": history,
            "hp": [state.get("hp"), state.get("max_hp")],
            "ready_names": ready_names,
            "front": front,
            "mana": state.get("mana"),
            "saves": [owned, ready],
            "front_distance": round(dist(track[t], front)),
        }
        action, detail = observe_action(track, hits, team, t, front)
        later = {
            "lane_last_hits": bisect_right(hits, t + OUTCOME_SECONDS) - bisect_right(hits, t),
            "death_seconds": [s for s in deaths if t < s <= t + OUTCOME_SECONDS],
            "complete": match["last"] >= t + OUTCOME_SECONDS,
        }
        yield evidence, {"action": action, "detail": detail, "lean": lean, "reason": reason}, later
