"""Hero traits v4 (U121): a trait may count some mechanisms only for user-listed abilities.

A trait spec may add `only_subjects: {mechanism: [ability, ...]}`. Rows with those mechanisms
count for that trait only when their ability is listed; other mechanisms count as before.
"Weak-dispellable saves" uses it: escape haste and Windrun's evasion count, other haste does
not. Every listed ability must have an accepted row with that mechanism.
"""

from dota_items.data.mechanics_traits_v3 import build_traits_v3


def _check(trait_id, allowed, doc):
    accepted = {(r["subject"], r["mechanism"]) for r in doc["rows"] if r["decision"] == "accept"}
    for mechanism, subjects in allowed.items():
        missing = [s for s in subjects if (s, mechanism) not in accepted]
        if missing:
            raise ValueError(f"{trait_id}: no accepted {mechanism} row for {missing}")


def build_traits_v4(mapping, doc, heroes, rules):
    restricted = {t: s for t, s in mapping["traits"].items() if s.get("only_subjects")}
    plain_specs = {}
    for trait_id, spec in mapping["traits"].items():
        if trait_id in restricted:
            spec = {k: v for k, v in spec.items() if k != "only_subjects"}
            spec["mechanisms"] = [
                *spec["mechanisms"],
                *sorted(restricted[trait_id]["only_subjects"]),
            ]
        plain_specs[trait_id] = spec
    out = build_traits_v3({**mapping, "traits": plain_specs}, doc, heroes, rules)
    for trait_id, spec in restricted.items():
        allowed = spec["only_subjects"]
        _check(trait_id, allowed, doc)
        rows = [
            r
            for r in doc["rows"]
            if r["mechanism"] not in allowed or r["subject"] in allowed[r["mechanism"]]
        ]
        one = build_traits_v3(
            {**mapping, "traits": {trait_id: plain_specs[trait_id]}},
            {**doc, "rows": rows},
            heroes,
            rules,
        )
        out["traits"][trait_id] = {**one["traits"][trait_id], "only_subjects": allowed}
    return {**out, "schema": "hero-traits/4"}
