"""Hero traits v3 (U105-U107): counts per hero, with and without upgrade-only abilities.

Every hero gets a number for every trait, zero included, because a model reads absence as data
too. A trait may also be a list of heroes the user named (`from_heroes`). `base` counts
abilities that have the mechanism without Aghanim's Scepter or Shard; `with_upgrades` also
counts abilities that only have it with an upgrade. Mana dependence comes from rule R12's hero
exceptions instead of mechanisms.
"""

from dota_items.data.mechanics_graph import build_traits


def _rule(rules, rule_id):
    return next(rule for rule in rules if rule["id"] == rule_id)


def build_traits_v3(mapping, doc, heroes, rules):
    plain = {
        trait_id: spec
        for trait_id, spec in mapping["traits"].items()
        if not spec.get("pending") and not spec.get("from_rule") and not spec.get("from_heroes")
    }
    listed = build_traits({**mapping, "traits": plain}, doc, heroes)["traits"]
    counts = {}
    for trait_id, spec in mapping["traits"].items():
        if spec.get("pending"):
            continue
        per_hero = {hero["hero_id"]: {"base": 0, "with_upgrades": 0} for hero in heroes}
        if spec.get("from_heroes"):
            listed_ids = set(spec["from_heroes"])
            unknown = listed_ids - set(per_hero)
            if unknown:
                raise ValueError(f"{trait_id}: unknown hero ids {sorted(unknown)}")
            for hero_id, value in per_hero.items():
                value["base"] = value["with_upgrades"] = int(hero_id in listed_ids)
        elif spec.get("from_rule"):
            targets = _rule(rules, spec["from_rule"])["target_heroes"]
            conditional = {entry["hero_id"] for entry in targets.get("conditional", [])}
            for hero_id, value in per_hero.items():
                dependent = hero_id not in targets["except"]
                value["base"] = int(dependent)
                value["with_upgrades"] = int(dependent and hero_id not in conditional)
        else:
            for entry in listed[trait_id]["heroes"]:
                with_base = [
                    a for a in entry["abilities"] if any(not e["condition"] for e in a["evidence"])
                ]
                per_hero[entry["hero_id"]] = {
                    "base": len(with_base),
                    "with_upgrades": entry["ability_count"],
                }
        counts[trait_id] = per_hero
    names = {hero["hero_id"]: hero["name_zh"] for hero in heroes}
    return {
        "schema": "hero-traits/3",
        "status": mapping["status"],
        "counting": mapping["counting"],
        "traits": {
            trait_id: {
                "zh": spec["zh"],
                "note": spec.get("note"),
                "pending": spec.get("pending"),
                "heroes": listed.get(trait_id, {}).get("heroes", []),
                "counts": [
                    {"hero_id": hero_id, "name_zh": names[hero_id], **value}
                    for hero_id, value in sorted(counts.get(trait_id, {}).items())
                ],
            }
            for trait_id, spec in mapping["traits"].items()
        },
    }
