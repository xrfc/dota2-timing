"""Estimate missed facts: compare accepted rows with two outside lists (MK-T5).

Neither list is ground truth. Hand labels from hero traits v1 can be loose, and keyword
hits can be false alarms; a miss here is a candidate to review, not a proven gap.

    PYTHONPATH=src python scripts/check_mechanics_recall.py \
        --output knowledge/mechanics/reviews/recall-check-001/recall.json
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The current facts come from the single entry point (MK-T6a).
FACTS = json.loads((ROOT / "knowledge/mechanics/current.json").read_text(encoding="utf-8"))[
    "entries"
]["facts"]["path"]
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
TRAITS_V1 = "knowledge/hero-traits/hero-traits-v1.json"
LABEL_MECHANISMS = {
    "mobility": ["self_mobility"],
    "disables": [
        "stun",
        "hex",
        "silence",
        "root",
        "bind",
        "taunt",
        "fear",
        "hypnotize",
        "sleep",
        "cyclone_banish",
    ],
    "illusions_summons": ["illusions", "summons"],
    "evasion": ["evasion", "blind"],
    "sustain": ["healing", "lifesteal"],
}
KEYWORDS = {
    "stun": r"\bstun",
    "silence": r"\bsilence",
    "lifesteal": r"lifesteal",
    "root": r"\b(root|ensnare|entangle)",
    "self_mobility": r"\b(blink|teleport|leap|dash|jump|rushes?|charging|charges? (at|toward))",
}


def check(doc, heroes, traits_v1):
    rows = {}
    for row in doc["rows"]:
        rows.setdefault(row["subject"], []).append(row)
    names = {
        (hero["name_zh"], ability["name_zh"]): ability["name"]
        for hero in heroes
        for ability in hero["abilities"]
    }
    labels = {}
    for trait, mechanisms in LABEL_MECHANISMS.items():
        result = {"accept": 0, "reject": [], "no_row": []}
        for label in traits_v1["labels"][trait]:
            for ability_zh in label["abilities"]:
                subject = names.get((label["hero"], ability_zh))
                found = [r for r in rows.get(subject, []) if r["mechanism"] in mechanisms]
                if any(r["decision"] == "accept" for r in found):
                    result["accept"] += 1
                else:
                    key = "reject" if found else "no_row"
                    result[key].append(f"{label['hero']}·{ability_zh}")
        labels[trait] = result
    keywords = {}
    for mechanism, pattern in KEYWORDS.items():
        hits, missed = 0, []
        for hero in heroes:
            for ability in hero["abilities"]:
                if re.search(pattern, ability.get("description_en") or "", re.I):
                    hits += 1
                    if not any(r["mechanism"] == mechanism for r in rows.get(ability["name"], [])):
                        missed.append(f"{hero['name_zh']}·{ability['name_zh']}")
        keywords[mechanism] = {"hits": hits, "no_row": missed}
    return {
        "schema": "mechanics-recall-check/1",
        "facts": FACTS,
        "note": "候选，不是已证实的漏记",
        "against_traits_v1": labels,
        "against_keywords": keywords,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output already exists; choose a new path")
    load = lambda name: json.loads((ROOT / name).read_text(encoding="utf-8"))  # noqa: E731
    result = check(load(FACTS), load(REGISTRY)["heroes"], load(TRAITS_V1))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
