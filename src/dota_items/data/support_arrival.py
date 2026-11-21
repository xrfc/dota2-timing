"""Conditional support route timings to a fixed ally position, using decision-time evidence."""

from math import ceil, dist

# Only displacements whose forward distance is identified in the local reference.
DISTANCE_KEYS = {
    "antimage_blink": "AbilityCastRange",
    "slark_pounce": "pounce_distance",
    "faceless_void_time_walk": "range",
    "morphling_waveform": "AbilityCastRange",
}


TP_MANA_COST = 75  # item_tpscroll AbilityManaCost in the 7.41f game snapshot


def _route(distance, speed, setup=0):
    # Direct and 30% longer routes are sensitivity scenarios, not confidence bounds.
    low, high = (ceil(setup + distance * factor / speed) for factor in (1, 1.3))
    return {"now": [low, high], "after_six": [low + 6, high + 6]}


def _label(route):
    low, high = route["now"]
    return f"立即 {low}–{high} 秒，等六秒 {low + 6}–{high + 6} 秒"


def support_comparison(state, ally_pos, towers, mobility):
    """Hold both endpoints and speed fixed to isolate the cost of waiting six seconds."""
    speed, pos = state.get("move_speed"), state.get("pos")
    if not pos or not ally_pos or not speed or speed <= 0:
        return {"summary": "缺少坐标或移速，无法计算支援耗时。", "routes": {}}
    distance = dist(pos, ally_pos)
    routes = {"walk": _route(distance, speed)}
    notes = [f"步行：{_label(routes['walk'])}。"]
    refs = mobility.get("heroes", mobility).get(state.get("hero"), {}).get("abilities", [])
    abilities = {a["name"]: a for a in state.get("abilities") or []}
    for ref in refs:
        name = ref["ability"]
        a = abilities.get(name, {})
        values = ref.get("distance_values", {}).get(DISTANCE_KEYS.get(name), [])
        level = a.get("level") or 0
        if not values or level < 1 or len(values) not in (1,) and level > len(values):
            continue
        if a.get("cd") != 0 or not a.get("activated") or a.get("hidden"):
            continue
        if a.get("mana_cost") is None or (state.get("mana") or 0) < a["mana_cost"]:
            continue
        reach = values[0 if len(values) == 1 else level - 1]
        if reach <= 0:
            continue
        routes[name] = _route(max(0, distance - reach), speed)
        notes.append(f"{ref['name_zh']}：{_label(routes[name])}，另加施法和位移耗时。")
    if len(routes) == 1:
        notes.append("当前缺少可量化的一次主动位移。")
    scroll = (state.get("items") or {}).get("15") or {}
    targets = [b for b in towers if b.get("team") == state.get("team") and "tower" in b["name"]]
    if (
        targets
        and scroll.get("name") == "item_tpscroll"
        and scroll.get("cd") == 0
        and (scroll.get("charges") or 0) > 0
    ):
        mana = state.get("mana")
        if mana is None:
            notes.append("当前魔法未知，传送卷轴能否使用待确认。")
        elif mana < TP_MANA_COST:
            notes.append(f"当前魔法不足 {TP_MANA_COST}，无法立即使用传送卷轴。")
        else:
            target = min(targets, key=lambda b: dist((b["x"], b["y"]), ally_pos))
            routes["tp"] = _route(dist((target["x"], target["y"]), ally_pos), speed, 3)
            notes.append(f"假设能传送到最近己方塔、引导 3 秒：{_label(routes['tp'])}。")
    else:
        notes.append("未检出就绪卷轴与存活己方塔的组合。")
    notes.append(
        "以队友当前位置为目的地，按记录移速估算直线和绕行三成两种情形。控制、落点、耗蓝、引导延长和队友移动仍会改变到场时间。"
    )
    return {"routes": routes, "summary": "".join(notes)}


def support_followup(hits_by_second, ally, t, last):
    """Describe a bounded observed damage sequence; this does not identify fight end."""
    end = min(t + 20, last)
    hits = [sec - t for sec in range(t + 1, end + 1) if ally in hits_by_second.get(sec, ())]
    text = f"随后 {end - t} 秒内该队友"
    if hits:
        text += f"有 {len(hits)} 个秒点受到敌方英雄伤害，最后一次在 +{hits[-1]} 秒。"
    else:
        text += "未记录到敌方英雄再次造成伤害。"
    return {
        "hit_offsets": hits,
        "complete": end == t + 20,
        "summary": text + "交战结束时刻仍未知。",
    }


def observed_approach(track, t, last, target):
    """Check recorded seconds within 400 units of the ally's fixed decision-time spot."""
    radius = 400
    end = min(t + 20, last)
    offsets = range(end - t + 1)
    missing = [s for s in offsets if track.get(t + s) is None]
    first = next(
        (
            s
            for s in offsets
            if track.get(t + s) is not None and dist(track[t + s], target) <= radius
        ),
        None,
    )
    first_entry = first if first is not None and not any(s < first for s in missing) else None
    window_complete = end == t + 20
    if first == 0:
        status, text = "already_near", "决策当秒已在范围内。"
    elif first is not None:
        status = "observed_near"
        text = f"+{first} 秒首次记录到进入范围。"
        if first_entry is None:
            text += "此前缺少位置采样，可能更早进入。"
    elif missing:
        status, text = "missing", "已有位置采样均在范围外，缺失秒点的行踪未知。"
    elif not window_complete:
        status, text = "truncated", "录像结束前的采样均在范围外。"
    else:
        status, text = "outside", "随后二十秒的逐秒位置均在范围外。"
    if not window_complete:
        text += f"可回看的后续时长为 {end - t} 秒。"
    return {
        "radius": radius,
        "window_complete": window_complete,
        "observed_seconds": end - t,
        "missing_samples": len(missing),
        "status": status,
        "first_seen_offset": first,
        "first_entry_offset": first_entry,
        "summary": f"队友决策位置周围 {radius} 单位：{text}实际施救情况需核对交战记录。",
    }
