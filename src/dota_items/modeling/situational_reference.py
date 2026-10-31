"""M2b-T5 baseline 针对装 reference (U20, U21). Descriptive counts only, no fitting.

Kept apart from situational_items so the frozen M2b run's source fingerprint holds.
"""

from dota_items.modeling import situational_items as si

# U21: support 针对装 shown as appearance rates only (U17: not modeled).
SUPPORTS = ((30, 5), (87, 5), (111, 5))
SUPPORT_ITEMS = (
    "spirit_vessel",
    "glimmer_cape",
    "force_staff",
    "cyclone",
    "lotus_orb",
    "pipe",
    "aeon_disk",
    "solar_crest",
    "holy_locket",
)


def reference(players, purchases, match_ids):
    """Counts on the given matches only; each player counts once per item/class.

    Juggernaut: games, games with any situational item, first-item class counts
    (si.build_samples rule) and per-class "bought at all". Supports: per-item
    "bought at all".
    """
    match_ids = set(match_ids)
    players = [r for r in players if r["match_id"] in match_ids]
    purchases = [p for p in purchases if p["match_id"] in match_ids]
    jugg = [r for r in players if (r["hero_id"], r["position"]) == si.HERO]
    jugg = [r for r in jugg if not r["collapsed_carry"]]
    samples = si.build_samples(players, purchases)
    bought = {}
    for p in purchases:
        bought.setdefault((p["match_id"], p["player_slot"]), set()).add(p["item"])

    def items_of(row):
        return bought.get((row["match_id"], row["player_slot"]), set())

    jugg_classes = [{si.ITEM_CLASS[i] for i in items_of(r) if i in si.ITEM_CLASS} for r in jugg]
    supports = []
    for spec in SUPPORTS:
        sets = [items_of(r) for r in players if (r["hero_id"], r["position"]) == spec]
        supports.append(
            {
                "spec": list(spec),
                "games": len(sets),
                "bought_counts": {i: sum(i in s for s in sets) for i in SUPPORT_ITEMS},
            }
        )
    return {
        "juggernaut": {
            "spec": list(si.HERO),
            "games": len(jugg),
            "games_with_any": len(samples),
            "first_counts": {c: sum(s["label"] == c for s in samples) for c in si.CLASSES},
            "bought_counts": {c: sum(c in s for s in jugg_classes) for c in si.CLASSES},
        },
        "supports": supports,
    }


# U23 expected pairs: trait -> situational items it should raise (draft mapping).
EXPECTED = {
    "evasion": ("monkey_king_bar",),
    "sustain": ("skadi", "spirit_vessel"),
    "mobility": ("basher", "force_staff"),
    "disables": ("sange_and_yasha", "cyclone", "aeon_disk"),
    "dispellable_save": ("nullifier",),
    "illusions_summons": ("diffusal",),
    "mana_dependent": ("diffusal",),
    "magic_burst": ("glimmer_cape", "pipe"),
    "targeted_spells": ("lotus_orb",),
}


def _diff(a, n_a, b, n_b):
    """Difference of proportions a/n_a - b/n_b with a normal-approximation 95% CI."""
    if not n_a or not n_b:
        return None
    p, q = a / n_a, b / n_b
    se = (p * (1 - p) / n_a + q * (1 - q) / n_b) ** 0.5
    return {"with": p, "without": q, "diff": p - q, "ci95": [p - q - 1.96 * se, p - q + 1.96 * se]}


def trait_crosscheck(players, purchases, match_ids, trait_heroes):
    """Per hero spec, trait (and subgroup) and item: bought rate with vs without the trait.

    trait_heroes: {group: set(hero_id)}; "with" = at least one enemy hero in the group.
    Descriptive only; enemy items and timing are not considered here.
    """
    match_ids = set(match_ids)
    players = [r for r in players if r["match_id"] in match_ids]
    bought = {}
    for p in purchases:
        if p["match_id"] in match_ids:
            bought.setdefault((p["match_id"], p["player_slot"]), set()).add(p["item"])
    by_match = {}
    for r in players:
        by_match.setdefault(r["match_id"], []).append(r)
    specs = {si.HERO: si.CLASSES, **{s: SUPPORT_ITEMS for s in SUPPORTS}}
    out = []
    for spec, items in specs.items():
        rows = [r for r in players if (r["hero_id"], r["position"]) == spec]
        if spec == si.HERO:
            rows = [r for r in rows if not r["collapsed_carry"]]
        targets = []
        for r in rows:
            own = bought.get((r["match_id"], r["player_slot"]), set())
            if spec == si.HERO:
                own = {si.ITEM_CLASS[i] for i in own if i in si.ITEM_CLASS}
            enemies = {
                e["hero_id"] for e in by_match[r["match_id"]] if e["is_radiant"] != r["is_radiant"]
            }
            targets.append((enemies, own))
        for group, heroes in trait_heroes.items():
            hit = [own for enemies, own in targets if enemies & heroes]
            miss = [own for enemies, own in targets if not enemies & heroes]
            for item in items:
                a, b = sum(item in o for o in hit), sum(item in o for o in miss)
                out.append(
                    {
                        "spec": list(spec),
                        "group": group,
                        "item": item,
                        "n_with": len(hit),
                        "n_without": len(miss),
                        "bought_with": a,
                        "bought_without": b,
                        "expected": item in EXPECTED.get(group.split(":")[0], ()),
                        **(_diff(a, len(hit), b, len(miss)) or {"diff": None}),
                    }
                )
    return out
