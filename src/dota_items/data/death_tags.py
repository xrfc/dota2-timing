"""Tags for one death: features that can all hold at once (U155, draft for U139).

The frozen B0 rule gives an episode one class, and only after it passes the four gank
conditions. A death can be in the laning minutes, after a skirmish, on the high ground,
by attackers who came unseen and by teleport, all at once. These tags show every
feature that holds, for any death, from what the episode already records plus the
teleports, smoke and map region worked out elsewhere. They describe; they are not the
frozen rule and do not change it.
"""

TAGS = {
    "laning": "对线期（10分钟前）",
    "other_lane": "别路来人",
    "teleported": "有人传送来",
    "smoked": "有人开雾来",
    "from_unseen": "至少一个敌人从视野外来",
    "seen_coming": "至少一个敌人之前10秒多数时间看得见",
    "single": "只有一个敌人",
    "far_from_allies": "离队友远（≥1500）",
    "big_fight": "大团战（身边>6个英雄或队友>2个）",
    "teamfight": "团战中（之前30秒身边≥6个英雄）",
    "after_fight": "打完小团战后",
    "approached": "他走向敌人",
    "struck_first": "他先动手",
    "enemy_area": "在敌方控制区（最近的塔或野区是敌方的）",
    "high_ground": "在高地上",
    "used_save": "交了保命",
}


def death_tags(episode, teleported=(), region=None, params=None):
    """[(tag, name_zh)] in TAGS order for one episode.

    `teleported` are the attackers who teleported in (data.teleports.arrived_near),
    `region` the map region at the start ({name_zh, ...} from data.map_api) or None.
    """
    from dota_items.data.gank_depth import PARAMS

    params = params or PARAMS
    flags, depth = episode["flags"], episode.get("depth") or {}
    signals = depth.get("signals") or {}
    fight = depth.get("after_fight")
    on = {
        "laning": episode["t0"] < params["laning_end"],
        "other_lane": episode["t0"] < params["laning_end"]
        and bool(depth.get("attackers_from_other_lanes")),
        "teleported": bool(teleported),
        "smoked": bool(episode.get("smoked_attackers")),
        "from_unseen": flags.get("from_unseen", False),
        "seen_coming": bool(signals.get("saw_attackers")),
        "single": not flags.get("enough_enemies", True),
        "far_from_allies": flags.get("far_from_allies", False),
        "big_fight": not flags.get("not_big_fight", True),
        "teamfight": bool(fight) and fight["most_heroes"] >= params["teamfight_heroes"],
        "after_fight": bool(fight) and fight["most_heroes"] < params["teamfight_heroes"],
        "approached": bool(signals.get("victim_approached")),
        "struck_first": bool(signals.get("struck_first")),
        "enemy_area": bool(signals.get("enemy_tower_area") or signals.get("enemy_jungle")),
        "high_ground": bool(depth.get("high_ground")),
        "used_save": bool(episode.get("self_saves") or episode.get("ally_saves")),
    }
    tags = [(tag, name) for tag, name in TAGS.items() if on[tag]]
    if region is not None:
        tags.append(("region", f"位置：{region['name_zh']}"))
    return tags


# The main reason of a death: the first row whose condition holds (U156). The order and
# the conditions are the assistant's draft for the user to change; they follow the user's
# earlier decisions where there are some (U138, U141, U142). Being on high ground is a tag,
# not a reason: U140 only said such deaths are not ganks (U157), so the gank row needs it off.
PRIMARY = (
    ("teamfight", "团战中", lambda t: t["big_fight"] or t["teamfight"]),
    ("laning", "对线期对拼", lambda t: t["laning"] and not t["other_lane"]),
    (
        "pressed_on",
        "打完架又深入",
        lambda t: t["after_fight"] and t["approached"] and t["enemy_area"],
    ),
    ("after_fight", "团战后被留", lambda t: t["after_fight"]),
    (
        "overextended",
        "自己深入",
        lambda t: t["seen_coming"] and (t["approached"] or t["enemy_area"]),
    ),
    (
        "ganked",
        "被抓",
        lambda t: (
            t["from_unseen"] and t["far_from_allies"] and not t["single"] and not t["high_ground"]
        ),
    ),
    ("skirmish", "队友在旁的小规模交战打输", lambda t: not t["far_from_allies"]),
    ("solo", "被单杀", lambda t: t["single"]),
    ("other", "其他", lambda t: True),
)


def primary_reason(tags):
    """(id, name_zh) of the main reason, from death_tags output."""
    on = dict.fromkeys(TAGS, False)
    on.update({tag: True for tag, _ in tags if tag in TAGS})
    return next((key, name) for key, name, holds in PRIMARY if holds(on))
