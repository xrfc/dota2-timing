"""Pick about a quarter of the heroes for the hero-trait spot check and gather what to show.

Run from the repo root:
    PYTHONPATH=src python knowledge/mechanics/reviews/traits-check-001/build_sample.py

Choice (assistant's implementation, the user asked for about 1/4 and the relations):
the user's four heroes; for every settled trait the hero with the highest count and the
hero whose count grows most with upgrades; two heroes from each user-named list (R12
exceptions, magic burst); then a fixed hash order fills up to 32 heroes. Everything shown is
read through knowledge/mechanics/current.json.
"""

import hashlib
import json
from pathlib import Path

from dota_items.data.mechanics_current import load_current, read_current

OUT = Path(__file__).resolve().parent
TARGET = 32
USER_HEROES = (8, 30, 87, 111)  # Juggernaut, Witch Doctor, Disruptor, Oracle (user profile)


def _order(hero_id):
    return hashlib.sha256(f"traits-check-001:{hero_id}".encode()).hexdigest()


def pick(traits, heroes, rules):
    chosen, why = [], {}

    def add(hero_id, reason):
        if hero_id not in why:
            chosen.append(hero_id)
            why[hero_id] = []
        if reason not in why[hero_id]:
            why[hero_id].append(reason)

    for hero_id in USER_HEROES:
        add(hero_id, "你常玩的英雄")
    for trait in traits.values():
        counts = trait["counts"]
        top = max(counts, key=lambda c: (c["with_upgrades"], -c["hero_id"]))
        if top["with_upgrades"] > 1:
            add(top["hero_id"], f"{trait['zh']}最多")
        gap = max(counts, key=lambda c: (c["with_upgrades"] - c["base"], -c["hero_id"]))
        if gap["with_upgrades"] - gap["base"] > 0:
            add(gap["hero_id"], f"{trait['zh']}升级后增加最多")
    r12 = next(rule for rule in rules if rule["id"] == "R12")
    exceptions = sorted(r12["target_heroes"]["except"], key=_order)
    for hero_id in exceptions[:2]:
        add(hero_id, "法力依赖例外名单")
    burst = [c["hero_id"] for c in traits["magic_burst"]["counts"] if c["base"]]
    for hero_id in sorted(burst, key=_order)[:2]:
        add(hero_id, "魔法爆发名单")
    for hero_id in sorted((h["hero_id"] for h in heroes), key=_order):
        if len(chosen) >= TARGET:
            break
        add(hero_id, "随机补足")
    return chosen, why


def _evidence(trait, hero_id):
    entry = next((h for h in trait.get("heroes", []) if h["hero_id"] == hero_id), None)
    if not entry:
        return []
    out = []
    for ability in entry["abilities"]:
        out.append(
            {
                "name": ability["name_zh"],
                "via": sorted({e["via"] for e in ability["evidence"]}),
                "condition": next(
                    (e["condition"] for e in ability["evidence"] if e["condition"]), ""
                ),
                "confirmed": any(e["confirmed"] for e in ability["evidence"]),
            }
        )
    return out


def main():
    current = load_current()
    traits = read_current("hero_traits")["traits"]
    mapping = read_current("trait_mapping")["traits"]
    rules = read_current("rules_expanded")["rules"]
    registry = json.loads(Path("knowledge/hero-capabilities/hero-registry.json").read_text())
    heroes = registry["heroes"]
    names = {h["hero_id"]: h["name_zh"] for h in heroes}
    profiles = {p["hero_id"]: p for p in read_current("hero_profiles")["profiles"]}
    previous = OUT / "sample.json"
    if previous.exists():  # keep the heroes the user is already reviewing
        old = json.loads(previous.read_text(encoding="utf-8"))["rows"]
        chosen, why = [r["hero_id"] for r in old], {r["hero_id"]: r["why"] for r in old}
    else:
        chosen, why = pick(traits, heroes, rules)
    rows = []
    for hero_id in chosen:
        hero_traits = []
        for key, trait in traits.items():
            count = next(c for c in trait["counts"] if c["hero_id"] == hero_id)
            source = mapping[key].get("mechanisms") or (
                f"规则{mapping[key]['from_rule']}"
                if mapping[key].get("from_rule")
                else "你给的名单"
            )
            hero_traits.append(
                {
                    "id": f"t-{hero_id}-{key}",
                    "key": key,
                    "zh": trait["zh"],
                    "base": count["base"],
                    "up": count["with_upgrades"],
                    "source": source,
                    "abilities": _evidence(trait, hero_id),
                }
            )
        abilities = [
            {
                "id": f"a-{ability['subject']}",
                "name": ability["name_zh"],
                "dispellable": ability.get("dispellable"),
                "damage_type": ability.get("damage_type"),
                "mechanisms": [
                    {
                        "zh": m["zh"],
                        "condition": m.get("condition") or "",
                        "confirmed": m.get("confirmed", False),
                    }
                    for m in ability["mechanisms"]
                ],
            }
            for ability in profiles[hero_id]["abilities"]
        ]
        relations = profiles[hero_id]["candidate_relations"]
        rows.append(
            {
                "hero_id": hero_id,
                "name": names[hero_id],
                "why": why[hero_id],
                "traits": hero_traits,
                "abilities": abilities,
                "rel_id": f"r-{hero_id}",
                "targeted_by": [
                    {
                        "rule": e["rule"],
                        "zh": e["zh"],
                        "status": e["status"],
                        "own": [f"{zh}" for zh in e["own_zh"]],
                        "items": e["item_zh"],
                        "ability_sources": e["ability_sources"],
                        "conditional": e.get("conditional", False),
                    }
                    for e in relations["targeted_by"]
                ],
                "targeting": [
                    {"rule": e["rule"], "zh": e["zh"], "status": e["status"], "own": e["own_zh"]}
                    for e in relations["targeting"]
                ],
            }
        )
    sample = {
        "schema": "traits-spot-check-sample/1",
        "facts": current["entries"]["facts"]["path"],
        "hero_traits": current["entries"]["hero_traits"]["path"],
        "heroes": len(rows),
        "of": len(heroes),
        "trait_mapping": {
            k: (v.get("mechanisms") or v.get("from_rule") or "from_heroes")
            for k, v in mapping.items()
        },
        "rows": rows,
    }
    (OUT / "sample.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=1) + "\n", "utf-8"
    )
    print(len(rows), [r["name"] for r in rows])


if __name__ == "__main__":
    main()
