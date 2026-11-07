"""M2b-T6d/T8: user-defined triggers for Juggernaut's situational items (U123).

Pregame triggers read enemy heroes only (hero trait base counts, or heroes that own a
rule's target abilities). In-game triggers read enemy items bought before a given second.
Validation is descriptive: buy rates with and without a trigger on the training split.
"""

from dota_items.modeling import situational_items as si
from dota_items.modeling.situational_reference import _diff


def trait_sums(trait_counts):
    """{trait: {hero_id: base}} from hero traits; pregame uses base counts (U104)."""
    return {
        trait: {c["hero_id"]: c["base"] for c in spec["counts"]}
        for trait, spec in trait_counts.items()
        if not spec.get("pending")
    }


def rule_heroes(evaluation, registry_heroes):
    """{rule_id: hero ids that own one of the rule's target abilities}."""
    owner = {a["name"]: h["hero_id"] for h in registry_heroes for a in h["abilities"]}
    return {
        rule["id"]: {owner[t] for t in rule["targets"] if t in owner}
        for rule in evaluation["rules"]
    }


def pregame_fires(item, enemies, sums, heroes_by_rule):
    """Whether one item's pregame trigger fires for these enemy hero ids."""
    condition = item["pregame"]
    if "trait" in condition:
        return sum(sums[condition["trait"]].get(h, 0) for h in enemies) >= condition["min_sum"]
    wanted = set().union(*(heroes_by_rule[r] for r in condition["rule_heroes"]))
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


def validate(spec, players, purchases, match_ids, sums, heroes_by_rule):
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
        pre = [pregame_fires(item, s["enemies"], sums, heroes_by_rule) for s in samples]
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
