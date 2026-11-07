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
