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
