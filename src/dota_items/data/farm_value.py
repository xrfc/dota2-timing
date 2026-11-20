"""Review local farming opportunities using only the team's information at the anchor."""

from bisect import bisect_right
from math import dist

from dota_items.data.death_risk import LANE_TEAM


def _counts(lane_hits, jungle_hits, start, end):
    """Count individual last hits in (start, end], preserving simultaneous kills."""
    return {
        name: bisect_right(times, end) - bisect_right(times, start)
        for name, times in (("lane", lane_hits), ("neutral", jungle_hits))
    }


def farm_comparison(match, hero, t, lane_hits, jungle_hits, camps):
    track = match["tracks"][hero]
    point = track["pos"][t]
    sides = LANE_TEAM[track["team"]] + "_"
    waves = sorted(
        (round(dist(point, row["front"])), lane[len(sides) :])
        for lane, row in (match["fronts"].get(t) or {}).items()
        if lane.startswith(sides) and row and row.get("count") and row.get("front")
    )
    wave = {"distance": waves[0][0], "lane": waves[0][1]} if waves else None
    nearby = sorted((round(dist(point, (camp["x"], camp["y"]))), camp["id"]) for camp in camps)[:2]
    history = _counts(lane_hits, jungle_hits, t - 20, t)
    lane_name = {"bot": "下路", "top": "上路", "mid": "中路"}
    wave_text = (
        f"最近己方兵线在{lane_name.get(wave['lane'], wave['lane'])}，前沿距你 {wave['distance']}。"
        if wave
        else "缺少己方兵线位置。"
    )
    camp_text = "、".join(f"{cid}号（{distance}）" for distance, cid in nearby)
    evidence = {
        "recent_20s": history,
        "nearest_allied_wave": wave,
        "camp_options": [{"id": cid, "distance": distance} for distance, cid in nearby],
        "target_item": None,
        "target_gold_gap": None,
        "summary": (
            f"过去 20 秒亲自补了 {history['lane']} 个线上兵、{history['neutral']} 个野怪。"
            + wave_text
            + (f"附近营地及直线距离：{camp_text}。" if nearby else "附近营地位置未知。")
            + "继续刷的增量取决于剩余可补单位；营地是否有野、计划买的装备及金币缺口未知。"
        ),
    }
    outcome = {}
    summaries = []
    for seconds in (6, 20):
        end = min(match["last"], t + seconds)
        counts = _counts(lane_hits, jungle_hits, t, end)
        outcome[f"next_{seconds}s"] = {**counts, "observed_seconds": end - t}
        summaries.append(
            f"随后 {end - t} 秒内，线上兵 {counts['lane']} 个、野怪 {counts['neutral']} 个"
        )
    outcome["summary"] = (
        "；".join(summaries) + "。均为实际补刀记录。每刀金币未核实，离开会损失多少仍未知。"
    )
    return evidence, outcome
