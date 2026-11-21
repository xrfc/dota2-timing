"""Conditional contact scenarios using only the player's team-visible snapshot."""

from math import ceil, dist

WALK_SPEED = 350
LOOKBACK = 15
HORIZON = 6

CONTROL = {
    "item_orchid": "沉默",
    "item_bloodthorn": "沉默",
    "item_basher": "攻击可能触发眩晕",
    "item_abyssal_blade": "近身控制",
    "item_sheepstick": "变形",
}
RESPONSES = {
    "item_black_king_bar": "黑皇杖",
    "item_manta": "幻影斧",
    "slark_dark_pact": "黑暗契约",
    "antimage_blink": "闪烁",
    "slark_pounce": "突袭",
    "item_satanic": "撒旦之邪力",
}


def catch_comparison(evidence, names=None):
    """Compare walking to the carry's present point under an explicit reference speed."""
    names = names or {}
    frame = evidence["history"][-1]
    origin = next(m["pos"] for m in frame["markers"] if m["side"] == "self")
    inventories = {r["hero"]: r for r in frame["equipment"] if not r["ally"]}
    candidates = []
    excluded = []
    for e in frame["enemies"]:
        if e.get("dead"):
            continue
        seen = e["last_seen"]
        age = frame["t"] - seen if seen is not None else None
        if age is None or not 0 <= age <= LOOKBACK:
            excluded.append(e["hero"])
            continue
        distance = e["distance"] if age == 0 else None
        if distance is None:
            trail = e.get("trail") or []
            if not trail or trail[-1][0] != seen:
                excluded.append(e["hero"])
                continue
            distance = dist(origin, trail[-1][1:])
        row = inventories.get(e["hero"], {})
        items = row.get("items") if row.get("observed") == seen else None
        controls = [
            name for slot, name in (items or {}).items() if 0 <= int(slot) < 6 and name in CONTROL
        ]
        eta = max(0, ceil(distance / WALK_SPEED - age))
        candidates.append(
            dict(hero=e["hero"], age=age, seconds=eta, controls=controls, distance=round(distance))
        )
    candidates.sort(key=lambda c: (c["seconds"], c["age"], c["distance"], c["hero"]))
    in_range = [c for c in candidates if c["seconds"] <= HORIZON]
    pair = [c["hero"] for c in in_range[:2]] if len(in_range) >= 2 else []
    response = [n for n in evidence.get("ready_names", []) if n in RESPONSES]
    details = []
    for c in in_range[:2]:
        items = "、".join(names.get(n, n) + "（" + CONTROL[n] + "）" for n in c["controls"])
        details.append(
            f"{names.get(c['hero'], c['hero'])}（{c['age']} 秒前露头，"
            f"条件到点约 {c['seconds']} 秒）" + (f"曾见 {items}" if items else "")
        )
    summary = "假设自己留在原地，敌人从最后露头位置以 350 单位/秒直线持续靠近。"
    if details:
        summary += "六秒内可到点的候选：" + "；".join(details) + "。"
        if pair:
            summary += "两人分别有接近条件，是否协同未知。"
    else:
        summary += "近期位置记录中未找到六秒内能走到此点的敌人。"
    ally = frame.get("ally")
    if ally:
        summary += f"最近队友相距 {ally[0]}，实际接应取决于路线和控制范围。"
    if response:
        summary += (
            "就绪估计含" + "、".join(RESPONSES[n] for n in response) + "，能否出手取决于先手顺序。"
        )
    summary += "超过十五秒未定位、位移切入、技能施法距离及伤害均未计入。"
    return dict(
        candidates=candidates,
        pair=pair,
        self_response=response,
        ally=ally,
        excluded=excluded,
        summary=summary,
    )
