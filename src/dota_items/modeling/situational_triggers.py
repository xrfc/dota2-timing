"""M2b-T6d/T8: user-defined triggers for Juggernaut's situational items (U123).

Pregame triggers read enemy heroes only, through the knowledge API (hero trait base counts,
heroes owning named abilities, or heroes owning a rule's target abilities). In-game
triggers read enemy items bought before a given second.
Validation is descriptive: buy rates with and without a trigger on the training split.
"""

from dota_items.modeling import situational_items as si
from dota_items.modeling.situational_reference import _diff


def pregame_fires(item, enemies, kb):
    """Whether one item's pregame trigger fires for these enemy hero ids.

    `kb` is a `dota_items.data.mechanics_api.Knowledge` (or anything with the same three
    methods): pregame uses base trait counts (U104); unknown heroes or abilities raise.
    """
    condition = item["pregame"]
    if "abilities_any" in condition:
        owners = set().union(*(kb.heroes_owning(a) for a in condition["abilities_any"].values()))
        return bool(set(enemies) & owners)
    if "trait" in condition:
        return kb.team_trait_sum(enemies, condition["trait"], "base") >= condition["min_sum"]
    wanted = set().union(*(kb.rule_target_heroes(r) for r in condition["rule_heroes"]))
    return bool(set(enemies) & wanted)


def ingame_fires(item, enemy_items_before):
    """Whether any listed enemy item was bought before the decision moment."""
    return bool(set(item["ingame_items"]) & set(enemy_items_before))


def _juggernauts(players, match_ids):
    match_ids = set(match_ids)
    return {
        (r["match_id"], r["player_slot"]): r
        for r in players
        if r["match_id"] in match_ids
        and (r["hero_id"], r["position"]) == si.HERO
        and not r["collapsed_carry"]
    }


def validate(spec, players, purchases, match_ids, kb):
    """Per item: pregame and in-game trigger rates and Juggernaut's buy rates with/without."""
    targets = _juggernauts(players, match_ids)
    by_match = {}
    for r in players:
        if r["match_id"] in {k[0] for k in targets}:
            by_match.setdefault(r["match_id"], []).append(r)
    bought, first, logs = {}, {}, {}
    for order, p in enumerate(purchases):
        key = (p["match_id"], p["player_slot"])
        logs.setdefault(key, []).append((p["time_s"], order, p["item"]))
        if key in targets and p["item"] in si.ITEM_CLASS:
            cls = si.ITEM_CLASS[p["item"]]
            bought.setdefault(key, set()).add(cls)
            if key not in first or (p["time_s"], order) < first[key][:2]:
                first[key] = (p["time_s"], order, cls)
    samples = []
    for key, row in targets.items():
        enemies = [e for e in by_match[row["match_id"]] if e["is_radiant"] != row["is_radiant"]]
        # In-game: enemy items bought before Juggernaut's first situational item (or the end).
        cutoff = first[key][0] if key in first else float("inf")
        seen = {
            item
            for e in enemies
            for t, _, item in logs.get((e["match_id"], e["player_slot"]), [])
            if t < cutoff
        }
        samples.append(
            {
                "enemies": [e["hero_id"] for e in enemies],
                "seen": seen,
                "bought": bought.get(key, set()),
                "first": first[key][2] if key in first else None,
            }
        )
    out = []
    for item in spec["items"]:
        cls = item["id"]
        pre = [pregame_fires(item, s["enemies"], kb) for s in samples]
        row = {
            "item": cls,
            "zh": item["zh"],
            "n": len(samples),
            "pregame_rate": sum(pre) / len(pre),
        }
        hit = [s for s, f in zip(samples, pre, strict=True) if f]
        miss = [s for s, f in zip(samples, pre, strict=True) if not f]
        row["pregame_bought"] = _diff(
            sum(cls in s["bought"] for s in hit),
            len(hit),
            sum(cls in s["bought"] for s in miss),
            len(miss),
        )
        row["pregame_first"] = _diff(
            sum(s["first"] == cls for s in hit),
            len(hit),
            sum(s["first"] == cls for s in miss),
            len(miss),
        )
        if item["ingame_items"]:
            ing = [ingame_fires(item, s["seen"]) for s in samples]
            hit = [s for s, f in zip(samples, ing, strict=True) if f]
            miss = [s for s, f in zip(samples, ing, strict=True) if not f]
            row["ingame_rate"] = sum(ing) / len(ing)
            row["ingame_first"] = _diff(
                sum(s["first"] == cls for s in hit),
                len(hit),
                sum(s["first"] == cls for s in miss),
                len(miss),
            )
        out.append(row)
    return {
        "samples": len(samples),
        "with_any_situational": sum(s["first"] is not None for s in samples),
        "items": out,
    }


def _verdict(diff, more, less):
    """Plain-language data conclusion from a with/without difference and its 95% interval.

    `more`/`less` complete the sentence, e.g. "更常出这件" / "更少出这件".
    """
    if not diff:
        return {"kind": "none", "text": "没有数据"}
    low, high = diff["ci95"]
    detail = (
        f"{round(diff['diff'] * 100):+d}%，区间 {round(low * 100):+d}%～{round(high * 100):+d}%"
    )
    if low > 0:
        return {"kind": "support", "text": f"数据支持：触发时高分段{more}（{detail}）"}
    if high < 0:
        return {"kind": "against", "text": f"触发时高分段反而{less}（{detail}）"}
    return {"kind": "unclear", "text": f"高分段数据看不出差别（{detail}）"}


def _pregame_reason(item, enemies, kb):
    condition = item["pregame"]
    if "trait" in condition:
        parts = [
            (kb.hero_name(h), kb.trait_count(h, condition["trait"]))
            for h in enemies
            if kb.trait_count(h, condition["trait"])
        ]
        total = sum(n for _, n in parts)
        listed = "、".join(f"{name}{n}" for name, n in parts) or "无"
        zh = kb.traits()[condition["trait"]]
        return f"敌方{zh}合计 {total}（{listed}），条件≥{condition['min_sum']}"
    if "abilities_any" in condition:
        hits = [
            f"{kb.hero_name(kb.ability_owner(a))}·{kb.ability_name(a)}"
            for names in condition["abilities_any"].values()
            for a in names
            if kb.ability_owner(a) in set(enemies)
        ]
        return "敌方有：" + ("、".join(hits) if hits else "无")
    heroes = set(enemies) & set().union(
        *(kb.rule_target_heroes(r) for r in condition["rule_heroes"])
    )
    return "敌方有：" + ("、".join(kb.hero_name(h) for h in sorted(heroes)) or "无")


def trigger_view(spec, validation, kb, enemies, seen, item_names):
    """Page rows for one lineup (U124 option A): every item, fired or not, with its reason,
    the mechanism rules behind it and the data conclusion from the training split."""
    data = {row["item"]: row for row in validation["items"]}
    rows = []
    for item in spec["items"]:
        pre = pregame_fires(item, enemies, kb)
        seen_hits = sorted(set(item["ingame_items"]) & set(seen))
        stats = data[item["id"]]
        rows.append(
            {
                "item": item["id"],
                "name": item["zh"],
                "pregame": pre,
                "pregame_reason": _pregame_reason(item, enemies, kb),
                "ingame": bool(seen_hits),
                "ingame_items": [item_names.get(i, i) for i in seen_hits],
                "rules": [kb.rule(r)["zh"] for r in item["rules"]],
                "pregame_verdict": _verdict(
                    stats.get("pregame_bought"), "更常出这件", "更少出这件"
                ),
                "ingame_verdict": _verdict(
                    stats.get("ingame_first"), "更常第一件选它", "更少第一件选它"
                )
                if item["ingame_items"]
                else None,
                "pregame_rate": stats["pregame_rate"],
                "note": item.get("note_zh"),
            }
        )
    rows.sort(key=lambda r: (not (r["pregame"] or r["ingame"]), not r["ingame"]))
    return {
        "enemies": [{"id": h, "name": kb.hero_name(h)} for h in enemies],
        "items": rows,
        "samples": validation["samples"],
        "knowledge": {"patch": kb.version["patch"], "api": kb.version["api"]},
    }
