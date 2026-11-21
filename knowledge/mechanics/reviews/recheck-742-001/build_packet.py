"""Build blind batches for the 7.42 recheck (U179, U180). Run from the repo root.

For every changed subject that has fact rows, the packet shows the official 7.41f and 7.42
English text side by side, the numeric and data fields that changed, and the current rows
(mechanism, its definition, condition, decision). Codex judges whether each row still holds.

Subjects whose only change is hero-level (talents, facets text outside the ability; category 1)
are not sent: their own text and values did not change, so their rows are kept as they are.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
MECH = ROOT / "knowledge/mechanics"
PATCH = MECH / "reviews/patch-update-2026-11-19"
OLD_HEROES = ROOT / "knowledge/hero-capabilities/snapshots/2026-11-06/sources"
NEW_HEROES = ROOT / "knowledge/hero-capabilities/snapshots/2026-11-19/sources"
OLD_ITEMS = ROOT / "knowledge/items/sources/itemdata-english-2026-11-06/items.json"
NEW_ITEMS = ROOT / "knowledge/items/sources/itemdata-english-2026-11-19/items.json"
BATCH_SIZE = 20
SENT = ("2_纯数值", "3_说明文字", "4_行为/目标/驱散/免疫/A杖魔晶", "5_增删或退出")
TEXT = ("desc_loc", "notes_loc", "scepter_loc", "shard_loc", "facets_loc")
DATA = (
    "behavior", "target_team", "target_type", "flags", "damage", "immunity", "dispellable",
    "ability_has_scepter", "ability_has_shard", "cast_ranges", "cast_points", "channel_times",
    "cooldowns", "durations", "damages", "mana_costs", "health_costs", "item_cost",
)  # fmt: skip


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean(text):
    if isinstance(text, list):
        return [c for c in (clean(t) for t in text) if c]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def abilities(folder):
    found = {}
    for path in sorted(Path(folder).glob("hero-*-english.json")):
        doc = load(path)
        hero = doc["result"]["data"]["heroes"][0] if "result" in doc else doc
        for ability in hero.get("abilities", []) + hero.get("facet_abilities", []):
            found.setdefault(ability["name"], ability)
    return found


def items(path):
    return {name.removeprefix("item_"): body for name, body in load(path).items()}


def values(entry):
    out = {}
    for value in entry.get("special_values") or []:
        out[value["name"]] = {
            "base": value.get("values_float"),
            "scepter": value.get("values_scepter") or None,
            "shard": value.get("values_shard") or None,
        }
    return out


def changes(old, new):
    out = []
    for key in DATA:
        if old.get(key) != new.get(key):
            out.append({"field": key, "old": old.get(key), "new": new.get(key)})
    old_values, new_values = values(old), values(new)
    for name in sorted(old_values.keys() | new_values.keys()):
        if old_values.get(name) != new_values.get(name):
            out.append({"field": name, "old": old_values.get(name), "new": new_values.get(name)})
    return out


def text(entry):
    return {key: clean(entry.get(key)) for key in TEXT if clean(entry.get(key))}


def main():
    categories = load(PATCH / "categories-draft.json")["by_subject"]
    vocabulary = {m["id"]: m for m in load(MECH / "vocabulary-v15.json")["mechanisms"]}
    facts = load(MECH / "extractions/v26/facts-v26.json")
    rows = {}
    for row in facts["rows"]:
        rows.setdefault(row["subject"], []).append(row)
    old_all = {**abilities(OLD_HEROES), **items(OLD_ITEMS)}
    new_all = {**abilities(NEW_HEROES), **items(NEW_ITEMS)}
    objects, removed, kept = [], [], []
    for subject, category in sorted(categories.items()):
        if subject not in rows:
            continue
        if category not in SENT:
            kept.append({"subject": subject, "category": category, "rows": len(rows[subject])})
            continue
        old, new = old_all.get(subject), new_all.get(subject)
        if new is None:
            removed.append({"subject": subject, "category": category,
                            "review_ids": [r["review_id"] for r in rows[subject]]})  # fmt: skip
            continue
        objects.append(
            {
                "subject": subject,
                "name_zh": rows[subject][0]["subject_zh"],
                "category": category,
                "text_741f": text(old or {}),
                "text_742": text(new),
                "changed_fields": changes(old or {}, new),
                "rows": [
                    {
                        "review_id": r["review_id"],
                        "mechanism": r["mechanism"],
                        "mechanism_zh": vocabulary[r["mechanism"]]["zh"],
                        "definition": vocabulary[r["mechanism"]]["definition"],
                        "condition": r["condition"]["context"],
                        "decision": r["decision"],
                    }
                    for r in rows[subject]
                ],
            }
        )
    (OUT / "batches").mkdir(exist_ok=True)
    for start in range(0, len(objects), BATCH_SIZE):
        name = OUT / "batches" / f"batch-{start // BATCH_SIZE + 1:03d}.json"
        name.write_text(json.dumps(objects[start : start + BATCH_SIZE], ensure_ascii=False) + "\n")
    summary = {
        "sent_objects": len(objects),
        "sent_rows": sum(len(o["rows"]) for o in objects),
        "batches": -(-len(objects) // BATCH_SIZE),
        "kept_category1": kept,
        "removed": removed,
    }
    (OUT / "packet-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print({k: v for k, v in summary.items() if not isinstance(v, list)}, len(kept), len(removed))


if __name__ == "__main__":
    main()
