"""Review clips for sampled gank episodes (track B, B0 spot check).

A clip is the omniscient 2D playback around one sampled episode: every hero's position,
health and life state per second, whether the other team could see it, whether it was
under Smoke of Deceit, and the hits, casts and deaths in the window. Clips exist only so
the user can judge whether the B0 rule labelled the episode correctly; they are review
material and labels, never model input (they contain omniscient and future information).
"""

SMOKE_MODIFIER = "modifier_smoke_of_deceit"
LEAD_SECONDS = 30
TAIL_SECONDS = 5
SMOKE_LOOKBACK = 30
TICKS_PER_SECOND = 30
WARD_SECONDS = {"observer": 360, "sentry": 420}  # normal lifetimes; match the replays' medians
HIT_SECONDS = 3  # damage from a cast within this many seconds marks who it hit
USE = "review_and_label_only"
# What the user can answer for a clip (U139: attribute the episode to a class).
CATEGORIES = (
    "gank",
    "overextended",
    "high_ground",
    "laning",
    "after_fight",
    "teamfight",
    "other",
    "unsure",
)


def smoke_intervals(combat, last_second):
    """{hero: [(start, end), ...]} seconds a hero itself was under Smoke of Deceit."""
    open_at, result = {}, {}
    for entry in sorted(combat, key=lambda e: e["time"]):
        p = entry["payload"]
        if p.get("inflictor_name") != SMOKE_MODIFIER or p.get("target_is_illusion"):
            continue
        hero = p.get("target_name")
        if p.get("log_type") == "MODIFIER_ADD":
            open_at.setdefault(hero, entry["time"])
        elif p.get("log_type") == "MODIFIER_REMOVE" and hero in open_at:
            result.setdefault(hero, []).append((open_at.pop(hero), entry["time"]))
    for hero, start in open_at.items():
        result.setdefault(hero, []).append((start, last_second))
    return result


def smoked_at(intervals, hero, second):
    return any(start <= second <= end for start, end in intervals.get(hero, ()))


def smoked_attackers(intervals, attackers, t0, lookback=SMOKE_LOOKBACK):
    """Attackers who were under smoke at any second of the `lookback` seconds up to t0."""
    return sorted(
        hero
        for hero in attackers
        if any(start <= t0 and end >= t0 - lookback for start, end in intervals.get(hero, ()))
    )


def ward_spans(wards, ticks_per_second=TICKS_PER_SECOND):
    """Each ward of the collector's `wards` channel with the seconds it stood.

    A ward ends when it expires or is destroyed (the channel fills `expires_tick` or
    `killed_tick`); one that is still up when the replay ends gets its normal lifetime.
    `dewarded` is true when a hero destroyed it before that lifetime ran out. Seconds come
    from ticks, so a pause while the ward stood makes it look a little longer-lived.
    """
    result = []
    for entry in wards:
        p = entry["payload"]
        kind, start = p["ward_type"], entry["time"]
        life = WARD_SECONDS.get(kind)
        last = p.get("expires_tick") or p.get("killed_tick")
        end = start + (last - p["tick"]) / ticks_per_second if last else start + (life or 0)
        result.append(
            {
                "type": kind,
                "team": p["team"],
                "x": round(p["x"]),
                "y": round(p["y"]),
                "start": start,
                "end": round(end),
                "dewarded": bool(p.get("killer")) and life is not None and end - start < life - 2,
            }
        )
    return result


def _events(combat, heroes, victim, start, stop):
    team = heroes[victim]["team"]
    damage, events = {}, []
    struck = {}  # (source, ability) -> [(second, hero hit)], to show whom a cast affected
    casts = {}  # hero -> names of what he cast in the window
    for entry in combat:
        p = entry["payload"]
        t = entry.get("time")
        if t is not None and start <= t <= stop and p.get("log_type") in ("ABILITY", "ITEM"):
            if p.get("inflictor_name"):
                casts.setdefault(p.get("attacker_name"), set()).add(p["inflictor_name"])
    for entry in combat:
        p = entry["payload"]
        t, name = entry.get("time"), p.get("inflictor_name")
        if t is None or not start <= t <= stop + HIT_SECONDS or not name:
            continue
        source, target = p.get("attacker_name"), p.get("target_name")
        if p.get("target_is_illusion") or source not in heroes or target not in heroes:
            continue
        if p.get("log_type") == "DAMAGE":
            struck.setdefault((source, name), []).append((t, target))
        elif (
            p.get("log_type") == "MODIFIER_ADD" and heroes[source]["team"] != heroes[target]["team"]
        ):
            # A debuff has its own name (modifier_lich_frost_nova_slow); it belongs to the
            # caster's ability or item whose name it contains. Names that do not follow
            # this habit (modifier_sheepstick_debuff) are missed.
            for cast in casts.get(source, ()):
                if cast.removeprefix("item_") in name:
                    struck.setdefault((source, cast), []).append((t, target))
    for entry in combat:
        t = entry.get("time")
        if t is None or not start <= t <= stop:
            continue
        p = entry["payload"]
        kind, source, target = p.get("log_type"), p.get("attacker_name"), p.get("target_name")
        if p.get("attacker_is_illusion"):
            continue
        if kind == "DAMAGE":
            if target == victim and source in heroes and heroes[source]["team"] != team:
                if not p.get("target_is_illusion"):
                    damage[(t, source)] = damage.get((t, source), 0) + (p.get("value") or 0)
        elif kind in ("ABILITY", "ITEM") and source in heroes:
            name = p.get("inflictor_name")
            events.append(
                {"t": t, "kind": "cast", "source": source, "name": p.get("inflictor_name"),
                 "target": target if target in heroes else None,
                 "target_other": bool(target) and target not in heroes and target != "dota_unknown",
                 "hits": sorted({hero for at, hero in struck.get((source, name), ())
                                 if t <= at <= t + HIT_SECONDS and hero != source})}
            )  # fmt: skip
        elif kind == "DEATH" and target in heroes and not p.get("target_is_illusion"):
            events.append({"t": t, "kind": "death", "source": source, "target": target})
        elif kind == "MODIFIER_ADD" and p.get("inflictor_name") == SMOKE_MODIFIER:
            if target in heroes and not p.get("target_is_illusion"):
                events.append({"t": t, "kind": "smoke", "target": target})
    for (t, source), value in damage.items():
        events.append(
            {"t": t, "kind": "damage", "source": source, "target": victim, "value": value}
        )
    return sorted(events, key=lambda e: (e["t"], e["kind"], e.get("source") or ""))


def build_clip(
    clip_id,
    stratum,
    episode,
    rows,
    combat,
    seen,
    lead=LEAD_SECONDS,
    tail=TAIL_SECONDS,
    towers=(),
    wards=(),
):
    """One review clip. `rows` are parser-v3 seconds, `seen` is gank_events.visibility_table."""
    start, stop = episode["t0"] - lead, episode["end"] + tail
    window = [r for r in rows if start <= r["t"] <= stop]
    heroes = {}
    for row in window:
        for h in row["heroes"]:
            heroes.setdefault(h["hero"], {"team": h["team"], "player_id": h["player_id"]})
    victim = episode["victim"]
    if victim not in heroes:
        raise ValueError(f"{clip_id}: victim {victim} has no state in the clip window")
    order = sorted(heroes, key=lambda name: (heroes[name]["team"], heroes[name]["player_id"]))
    last = rows[-1]["t"]
    smoke = smoke_intervals(combat, last)
    frames = []
    for row in window:
        by_name = {h["hero"]: h for h in row["heroes"]}
        states = []
        for name in order:
            h = by_name.get(name)
            if h is None or not h.get("pos"):
                states.append(None)
                continue
            other = 3 if heroes[name]["team"] == 2 else 2
            states.append(
                [
                    round(h["pos"][0]),
                    round(h["pos"][1]),
                    h.get("hp"),
                    h.get("max_hp"),
                    int(h.get("life_state") == 0),
                    int(row["t"] in seen.get((name, other), ())),
                    int(smoked_at(smoke, name, row["t"])),
                ]
            )
        frames.append({"t": row["t"], "h": states})
    return {
        "id": clip_id,
        "stratum": stratum,
        "use": USE,
        "omniscient": True,
        "episode": episode,
        "start": start,
        "stop": stop,
        "heroes": [{"hero": name, **heroes[name]} for name in order],
        "state_fields": ["x", "y", "hp", "max_hp", "alive", "seen_by_other_team", "smoked"],
        "frames": frames,
        "events": _events(combat, heroes, victim, start, stop),
        "smoked_attackers": smoked_attackers(smoke, episode["attackers"], episode["t0"]),
        "smoke_lookback": SMOKE_LOOKBACK,
        "towers": [[t["team"], t["x"], t["y"]] for t in towers],
        # U152: wards standing at any second of the clip (ward_spans output).
        "wards": [w for w in wards if w["start"] <= stop and w["end"] >= start],
    }


def validate_judgment(value, clip_ids):
    """Checked copy of one judgment posted by the review page."""
    if not isinstance(value, dict) or set(value) != {"id", "verdict", "note"}:
        raise ValueError("judgment must have exactly id, verdict, note")
    if value["id"] not in clip_ids:
        raise ValueError("unknown clip id")
    if value["verdict"] not in (*CATEGORIES, None):
        raise ValueError("verdict must be one of the categories or null")
    if not isinstance(value["note"], str) or len(value["note"]) > 500:
        raise ValueError("note must be text of at most 500 characters")
    return {"id": value["id"], "verdict": value["verdict"], "note": value["note"].strip()}


# --- Acceptance sample and blind second opinion (U143) ---------------------------------
# After the rule is frozen, a fresh sample from matches the user has not reviewed is judged
# by a second reader that never sees the rule's answer; the user then reviews every
# disagreement and a few agreed clips per class.

ACCEPTANCE_QUOTA = {
    "death": 20,
    "save_escape": 20,
    "overextended": 15,
    "laning": 10,
    "after_fight": 10,
    "teamfight": 10,
    "high_ground": 5,
    "near_miss": 10,
}
ANSWERS = tuple(c for c in CATEGORIES if c != "unsure")
TEAM_ZH = {2: "天辉", 3: "夜魇"}


def stratum_of(episode):
    """The class the frozen rule put an episode in, or None when it is not sampled."""
    if episode["is_gank"]:
        return episode["label"]
    return "near_miss" if sum(not v for v in episode["flags"].values()) == 1 else None


def rule_category(episode):
    """The rule's answer in the categories a reviewer picks from."""
    if not episode["is_gank"]:
        return "other"
    return "gank" if episode["label"] in ("death", "save_escape") else episode["label"]


def draw_acceptance(episodes, excluded_matches, quota, seed):
    """([{id, stratum, episode}], population) from matches outside `excluded_matches`.

    Ids are assigned after shuffling, so an id says nothing about the class.
    """
    import random

    rng = random.Random(seed)
    pools = {stratum: [] for stratum in quota}
    for episode in episodes:
        stratum = stratum_of(episode)
        if stratum in pools and episode["match_id"] not in excluded_matches:
            pools[stratum].append(episode)
    picked = [
        (stratum, episode)
        for stratum, size in quota.items()
        for episode in rng.sample(pools[stratum], min(size, len(pools[stratum])))
    ]
    rng.shuffle(picked)
    items = [
        {"id": f"A{number:03d}", "stratum": stratum, "episode": episode}
        for number, (stratum, episode) in enumerate(picked, 1)
    ]
    return items, {stratum: len(pool) for stratum, pool in pools.items()}


def _name(hero):
    return str(hero).replace("npc_dota_hero_", "")


def _gap(a, b):
    return round(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)


def clip_text(clip, zones, base_radius):
    """A clip as plain text for a reader that must not see the rule's answer.

    Only observations are written: positions turned into distances, visibility, smoke,
    health, casts, hits and deaths. No flag, signal or label of the rule appears.
    `base_radius` is {team: radius of that side's high-ground quarter circle}.
    """
    episode = clip["episode"]
    victim, t0 = episode["victim"], episode["t0"]
    order = [h["hero"] for h in clip["heroes"]]
    team = {h["hero"]: h["team"] for h in clip["heroes"]}
    own = team[victim]
    fountain = {f["team"]: (f["x"], f["y"]) for f in zones["fountains"]}
    other_lanes = (episode.get("depth") or {}).get("attackers_from_other_lanes")
    lines = [
        f"## {clip['id']}",
        f"被评价的1号位：{_name(victim)}（{TEAM_ZH[own]}）。起点：比赛第{t0}秒"
        f"（{t0 // 60}:{t0 % 60:02d}），片段从起点前{t0 - clip['start']}秒"
        f"到第{clip['stop'] - t0}秒。",
        "起点后20秒内对他造成伤害的敌方英雄：" + "、".join(map(_name, episode["attackers"])),
    ]
    if other_lanes is not None:
        same = [a for a in episode["attackers"] if a not in other_lanes]
        lines.append(
            "这些敌人在1–10分钟主要待的路：和他同路："
            + ("、".join(map(_name, same)) or "无")
            + "；别的路："
            + ("、".join(map(_name, other_lanes)) or "无")
        )
    saves = [*episode.get("self_saves", ()), *episode.get("ally_saves", ())]
    lines.append(
        "片段内用掉的保命手段："
        + ("、".join(f"{s['name']}@{s['t'] - t0:+d}" for s in saves) or "无")
    )
    lines.append(f"高地范围：距天辉泉水≤{base_radius[2]}，或距夜魇泉水≤{base_radius[3]}。")
    lines.append(
        "每秒状态（秒相对起点）：秒 | 血量% | 距己方泉水 | 距敌方泉水 | 最近未倒的塔 | "
        "最近的活着的队友 | 1600内队友数/敌人数 | 4000内的敌人：名字 距离 "
        "对他这方可见(见/不见) [雾]"
    )
    for frame in clip["frames"]:
        rel = frame["t"] - t0
        if rel < -10 and rel % 3:
            continue
        state = dict(zip(order, frame["h"], strict=True))
        me = state[victim]
        if me is None:
            continue
        here = (me[0], me[1])
        if not me[4]:
            lines.append(f"{rel:+d} | 已死亡")
            continue
        allies, enemies = [], []
        for hero, s in state.items():
            if hero == victim or s is None or not s[4]:
                continue
            distance = _gap(here, (s[0], s[1]))
            if team[hero] == own:
                allies.append(distance)
            else:
                enemies.append((distance, hero, s))
        tower = min(clip["towers"], key=lambda t: _gap(here, (t[1], t[2])), default=None)
        tower_text = (
            f"{'己方' if tower[0] == own else '敌方'}塔{_gap(here, (tower[1], tower[2]))}"
            if tower
            else "无"
        )
        shown = "；".join(
            f"{_name(hero)} {distance} {'见' if s[5] else '不见'}{' 雾' if s[6] else ''}"
            for distance, hero, s in sorted(enemies)
            if distance <= 4000
        )
        lines.append(
            f"{rel:+d} | {round(100 * me[2] / me[3]) if me[3] else '?'} | "
            f"{_gap(here, fountain[own])} | {_gap(here, fountain[5 - own])} | {tower_text} | "
            f"{min(allies) if allies else '无'} | "
            f"{sum(d <= 1600 for d in allies)}/{sum(d <= 1600 for d, _, _ in enemies)} | "
            f"{shown or '无'}"
        )
    lines.append("事件（秒相对起点）：")
    for event in clip["events"]:
        rel = event["t"] - t0
        if event["kind"] == "damage":
            text = f"{_name(event['source'])} 对他造成伤害 {event['value']}"
        elif event["kind"] == "death":
            side = TEAM_ZH[team[event["target"]]]
            text = f"{_name(event['target'])}（{side}）死亡"
        elif event["kind"] == "smoke":
            text = f"{_name(event['target'])} 进入诡计之雾"
        else:
            side = TEAM_ZH[team[event["source"]]]
            text = f"{_name(event['source'])}（{side}）用 {event['name']}"
            if event.get("target") and event["target"] != event["source"]:
                text += f" → {_name(event['target'])}"
            elif event.get("target_other"):
                text += " → 非英雄单位"
            if event.get("hits"):
                text += "（打中 " + "、".join(map(_name, event["hits"])) + "）"
        lines.append(f"{rel:+d} {text}")
    return "\n".join(lines)


def review_list(items, second_opinions, agreed_per_class, seed):
    """Which clips the user reviews: every disagreement plus a few agreed ones per class.

    `second_opinions` is {id: category}. Returns (ids in id order, comparison rows).
    """
    import random

    rng = random.Random(seed)
    rows, agreed = [], {}
    for item in items:
        rule, second = rule_category(item["episode"]), second_opinions.get(item["id"])
        same = rule == second
        rows.append({"id": item["id"], "rule": rule, "second": second, "agree": same})
        if same:
            agreed.setdefault(rule, []).append(item["id"])
    ids = {row["id"] for row in rows if not row["agree"]}
    for _, pool in sorted(agreed.items()):
        ids.update(rng.sample(pool, min(agreed_per_class, len(pool))))
    for row in rows:
        row["user_reviews"] = row["id"] in ids
    return sorted(ids), rows


def acceptance_score(rows, judgments):
    """Per rule category, how often the user sides with the rule on gank-or-not (U143).

    `rows` are the comparison rows of review_list, `judgments` is {id: {"verdict": ...}}.
    Disagreements were all put before the user; of the agreed clips only a sample was, so
    the user's rate on that sample stands in for the rest. With a handful of agreed clips
    per category the estimate is coarse; `agreed_judged` says how coarse.
    """
    result = {}
    for category in sorted({row["rule"] for row in rows}):
        mine = [row for row in rows if row["rule"] == category]
        parts = {}
        for agree in (False, True):
            part = [row for row in mine if row["agree"] is agree]
            verdicts = [
                (judgments.get(row["id"]) or {}).get("verdict")
                for row in part
                if row["user_reviews"]
            ]
            judged = [v for v in verdicts if v and v != "unsure"]
            same = sum((v == "gank") == (category == "gank") for v in judged)
            parts[agree] = (len(part), len(judged), same, sum(v == category for v in judged))
        (d_n, d_judged, d_same, d_class), (a_n, a_judged, a_same, a_class) = (
            parts[False],
            parts[True],
        )
        estimate = None
        if (d_judged or not d_n) and (a_judged or not a_n):
            right = (d_n * d_same / d_judged if d_n else 0) + (
                a_n * a_same / a_judged if a_n else 0
            )
            estimate = round(right / len(mine), 3)
        result[category] = {
            "clips": len(mine),
            "disagreed": d_n,
            "disagreed_judged": d_judged,
            "disagreed_user_sides_with_rule": d_same,
            "agreed": a_n,
            "agreed_judged": a_judged,
            "agreed_user_sides_with_rule": a_same,
            "user_picked_same_class": d_class + a_class,
            "estimated_share_rule_right_on_gank_or_not": estimate,
        }
    return result


def cohen_kappa(pairs):
    """Chance-corrected agreement of two raters on [(label_a, label_b)]; None when undefined.

    Plain agreement flatters raters who mostly use one label; kappa takes out what two
    raters with these label frequencies would agree on by chance.
    """
    pairs = list(pairs)
    if not pairs:
        return None
    total = len(pairs)
    observed = sum(a == b for a, b in pairs) / total
    labels = {label for pair in pairs for label in pair}
    expected = sum(
        (sum(a == label for a, _ in pairs) / total) * (sum(b == label for _, b in pairs) / total)
        for label in labels
    )
    return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def agreement(pairs):
    """{pairs, agreement, kappa} on the full labels and on gank-or-not."""
    pairs = [(a, b) for a, b in pairs if a and b and "unsure" not in (a, b)]
    binary = [(a == "gank", b == "gank") for a, b in pairs]
    return {
        "pairs": len(pairs),
        "class_agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None,
        "class_kappa": cohen_kappa(pairs),
        "gank_or_not_agreement": round(sum(a == b for a, b in binary) / len(binary), 3)
        if binary
        else None,
        "gank_or_not_kappa": cohen_kappa(binary),
    }
