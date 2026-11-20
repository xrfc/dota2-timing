"""Exploratory position-one lane review. Keep decision evidence separate from later observations."""

from bisect import bisect_left, bisect_right
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


def visible_trail(track, times, last):
    """Last uninterrupted visible segment, ending at the last sighting."""
    end = bisect_right(times, last)
    points = []
    for second in reversed(times[max(0, end - 12) : end]):
        pos = track.get(second)
        if pos is None or (points and points[-1][0] != second + 1):
            break
        points.append([second, *pos])
    return points[::-1]


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


def _context(match, mid, hero, t, visibility, state, means):
    team = match["tracks"][hero]["team"]
    history = [
        frame
        for sec in (t - 10, t - 5, t)
        if (frame := evidence_at(match["tracks"], visibility, hero, sec)) is not None
    ]
    for frame in history:
        frame["wards"] = [
            {"type": w["type"], "pos": [w["x"], w["y"]]}
            for w in match.get("wards", ())
            if w["team"] == team and w["start"] <= frame["t"] <= w["end"]
        ]
        for enemy in frame["enemies"]:
            name, last = enemy["hero"], enemy["last_seen"]
            enemy["trail"] = (
                visible_trail(match["tracks"][name]["pos"], visibility[name, team], last)
                if last is not None
                else []
            )
    owned, ready = save_state(state, means)
    abilities = (a["name"] for a in state.get("abilities") or [] if a.get("name"))
    items = (i["name"] for i in (state.get("items") or {}).values() if i.get("name"))
    ready_names = [
        name
        for name in sorted(set(abilities) | set(items))
        if name in means and save_state(state, {name})[1]
    ]
    return {
        "match": mid,
        "hero": hero,
        "t": t,
        "history": history,
        "hp": [state.get("hp"), state.get("max_hp")],
        "ready_names": ready_names,
        "mana": state.get("mana"),
        "saves": [owned, ready],
    }


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
        evidence = _context(match, mid, hero, t, visibility, states[t], means)
        evidence.update(lane=lane, front=front, front_distance=round(dist(track[t], front)))
        for frame in evidence["history"]:
            waves = match["fronts"].get(frame["t"]) or {}
            own_wave = waves.get(f"{LANE_TEAM[team]}_{lane}") or {}
            frame["wave"] = own_wave.get("front")
        lean, reason = assess(evidence["history"][-1], states[t])
        action, detail = observe_action(track, hits, team, t, front)
        later = {
            "lane_last_hits": bisect_right(hits, t + OUTCOME_SECONDS) - bisect_right(hits, t),
            "death_seconds": [s for s in deaths if t < s <= t + OUTCOME_SECONDS],
            "complete": match["last"] >= t + OUTCOME_SECONDS,
        }
        yield evidence, {"action": action, "detail": detail, "lean": lean, "reason": reason}, later


def jungle_seconds(events, hero):
    """Own non-illusion last hits on neutral-prefixed units, including duplicate seconds."""
    return sorted(
        e["time"]
        for e in events
        if e["payload"].get("log_type") == "DEATH"
        and e["payload"].get("attacker_name") == hero
        and not e["payload"].get("attacker_is_illusion")
        and (e["payload"].get("target_name") or "").startswith("npc_dota_neutral_")
    )


def _jungle_reason(frame):
    missing = sum(e["distance"] is None for e in frame["enemies"])
    ally = frame["ally"]
    support = f"最近队友相距 {ally[0]}。" if ally else "当前没有存活队友的位置记录。"
    markers = frame["markers"]
    contact = min(
        (
            dist(a["pos"], b["pos"])
            for a in markers
            if a["side"] == "ally"
            for b in markers
            if b["side"] == "enemy"
        ),
        default=None,
    )
    if contact is None:
        help_text = "缺少队友与可见敌人的相对位置，支援需求待定。"
    else:
        help_text = f"队友与可见敌人的最短距离为 {round(contact)}，支援还取决于自己能否及时到场。"
    return (
        f"留区可继续获取野区资源；{missing} 名敌人当前没有可见位置。"
        + support
        + "若来路已暴露，可考虑换区；对方是否获知下一站尚不确定。"
        + help_text
    )


def route_from_lane(track, lane_hits, t, camps):
    """Straight-line alternatives from the last lane hit in [t-45,t), using only own track.

    lane_hits is sorted. The count includes the nearest camp to the hero at t and all
    camp centres as close or closer to the lane anchor. It measures geometric choice,
    without estimating pathing, camp occupancy or whether opponents saw the lane hit.
    """
    previous = bisect_left(lane_hits, t) - 1
    if previous < 0 or t - lane_hits[previous] > 45 or not camps:
        return None
    lane_t = lane_hits[previous]
    origin, here = track.get(lane_t), track.get(t)
    if origin is None or here is None:
        return None
    camp = min(camps, key=lambda c: dist(here, (c["x"], c["y"])))
    centre = [camp["x"], camp["y"]]
    radius = dist(origin, centre)
    return {
        "lane_t": lane_t,
        "lane_pos": list(origin),
        "camp_id": camp["id"],
        "camp_pos": centre,
        "radius": round(radius),
        "candidate_count": sum(dist(origin, (c["x"], c["y"])) <= radius for c in camps),
    }


def make_jungle_cases(match, mid, hero, hits, visibility, states, means, deaths, camps):
    track = match["tracks"][hero]["pos"]
    next_time = START_SECOND
    for t in hits:
        if t < next_time or t not in track or t not in states:
            continue
        next_time = t + REPEAT_SECONDS
        evidence = _context(match, mid, hero, t, visibility, states[t], means)
        here = track[t]
        camp = min(camps, key=lambda c: dist(here, (c["x"], c["y"])))
        point = [camp["x"], camp["y"]]
        evidence.update(kind="jungle", camp_id=camp["id"], camp_distance=round(dist(here, point)))
        evidence["history"][-1]["camp"] = point
        count = bisect_right(hits, t + ACTION_SECONDS) - bisect_right(hits, t)
        detail = f"随后六秒内记录到 {count} 次野怪补刀。"
        if match["last"] < t + ACTION_SECONDS:
            detail = "录像结束，六秒动作窗不完整。"
        action = {
            "action": "unknown",
            "lean": "unknown",
            "detail": detail,
            "reason": _jungle_reason(evidence["history"][-1]),
        }
        outcome = {
            "jungle_last_hits": bisect_right(hits, t + OUTCOME_SECONDS) - bisect_right(hits, t),
            "death_seconds": [s for s in deaths if t < s <= t + OUTCOME_SECONDS],
            "complete": match["last"] >= t + OUTCOME_SECONDS,
        }
        yield evidence, action, outcome
