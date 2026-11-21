"""Each hero's own mobility abilities with cooldowns and distances (gap list item 11, U154).

    PYTHONPATH=src .venv/bin/python scripts/build_hero_mobility.py

Writes `knowledge/awareness/hero-mobility-v1.json` (refuses to overwrite). Which abilities
count as mobility comes from the mechanics knowledge base (accepted `self_mobility`
facts; their basis is kept, most are `two_ai`, i.e. not user approved). Cooldowns, cast
ranges and the special values whose names look like a distance are copied from the
hero capability files (official data). They are not reviewed: a value named `range`
may be a search radius rather than how far the hero moves, so read `distance_values`
with the ability text. Items (Blink Dagger, Force Staff, ...) are listed by name only.
"""

import json
import re
from pathlib import Path

from dota_items.data.mechanics_api import Knowledge

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "knowledge/awareness/hero-mobility-v1.json"
DISTANCE = re.compile(r"(range|distance|dist|leap|jump|blink|hop|charge)", re.IGNORECASE)
NOT_DISTANCE = re.compile(r"(speed|duration|time|height|attack|radius|bonus|pct|percent|threshold)")


def main():
    if TARGET.exists():
        raise SystemExit(f"{TARGET} exists; make a new version instead of overwriting")
    abilities = {}
    for path in sorted((ROOT / "knowledge/hero-capabilities/heroes").glob("*.json")):
        hero = json.loads(path.read_text(encoding="utf-8"))
        for ability in hero["abilities"]:
            abilities[ability["name"]] = (hero, ability)
    facts = {}
    for row in Knowledge(ROOT).subjects_with("self_mobility"):
        facts.setdefault(row["subject"], []).append(row)
    heroes, items = {}, []
    for subject, rows in sorted(facts.items()):
        conditions = sorted({r["condition"] for r in rows})
        bases = sorted({r["basis"] for r in rows})
        if subject not in abilities:
            items.append({"item": subject, "name_zh": rows[0]["subject_zh"], "basis": bases})
            continue
        hero, ability = abilities[subject]
        distances = {
            v["name"]: v["values_float"]
            for v in ability["special_values"]
            if DISTANCE.search(v["name"])
            and not NOT_DISTANCE.search(v["name"])
            and v["values_float"]
        }
        heroes.setdefault(hero["npc_name"], {"name_zh": hero["name_zh"], "abilities": []})[
            "abilities"
        ].append(
            {
                "ability": subject,
                "name_zh": ability["name_zh"],
                "condition": conditions,
                "mechanism_basis": bases,
                "cooldowns": ability["cooldowns"],
                "cast_ranges": ability["cast_ranges"],
                "distance_values": distances,
            }
        )
    value = {
        "schema": "hero-mobility/1",
        "decision": "U154 (gap list item 11)",
        "use": "reference for review pages and later features; not reviewed by the user",
        "sources": {
            "which_abilities": "knowledge/mechanics/current.json facts, mechanism self_mobility",
            "numbers": "knowledge/hero-capabilities/heroes/*.json (official data)",
        },
        "caution": "distance_values are picked by name and not reviewed",
        "heroes": heroes,
        "items": items,
    }
    TARGET.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    count = sum(len(h["abilities"]) for h in heroes.values())
    print(f"{len(heroes)} heroes, {count} abilities, {len(items)} items -> {TARGET}")


if __name__ == "__main__":
    main()
