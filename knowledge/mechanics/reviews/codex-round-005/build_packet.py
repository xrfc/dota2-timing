"""Build blind Codex batches for v4 groups only Claude reviewed (U56). Run from repo root."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
MECH = ROOT / "knowledge/mechanics"
BATCH_SIZE = 30
UPGRADE_KEY = {"scepter": "scepter_loc", "shard": "shard_loc"}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    spec = importlib.util.spec_from_file_location(
        "check_break", ROOT / "scripts/check_break_against_game_files.py"
    )
    breaks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(breaks)
    snapshot = ROOT / "knowledge/game-files/snapshots/2026-11-02/sources/scripts/npc"
    bodies = {}
    for path in [snapshot / "npc_abilities.txt", *sorted((snapshot / "heroes").glob("*.txt"))]:
        tree = breaks.parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
        bodies.update(breaks.iter_abilities(tree))
    items_path = (
        ROOT / "knowledge/game-files/snapshots/2026-11-03-items/sources/scripts/npc/items.txt"
    )
    item_tree = breaks.parse_keyvalues(items_path.read_text(encoding="utf-8", errors="replace"))
    item_bodies = item_tree.get("DOTAAbilities", item_tree)

    doc = load_json(MECH / "extractions/v4/facts-v4.json")
    vocabulary = {m["id"]: m for m in load_json(MECH / "vocabulary-v4.json")["mechanisms"]}
    registry = load_json(ROOT / "knowledge/hero-capabilities/hero-registry.json")
    abilities = {a["name"]: a for h in registry["heroes"] for a in h["abilities"]}
    constants = load_json(ROOT / "knowledge/items/sources/dotaconstants-items.json")
    stale = {
        (row["ability"], UPGRADE_KEY[row["upgrade"]])
        for row in load_json(MECH / "stale-upgrade-text-v1.json")["entries"]
    }

    def hero_context(name):
        ability = abilities[name]
        context = {
            key: ability[key]
            for key in (
                "name_en",
                "name_zh",
                "description_en",
                "description_zh",
                "notes_en",
                "notes_zh",
                "innate",
                "granted_by_scepter",
                "granted_by_shard",
            )
            if ability.get(key) not in (None, "", [], {})
        }
        upgrades = {
            key: text
            for key, text in ability["upgrade_text"].items()
            if (name, key) not in stale and any(text.values())
        }
        if upgrades:
            context["upgrade_text"] = upgrades
        return context

    def item_context(name):
        entry = constants[name]
        return {
            key: entry[key]
            for key in ("dname", "abilities", "notes", "attrib", "hint")
            if entry.get(key) not in (None, "", [], {})
        }

    groups = []
    for row in doc["rows"]:
        if row["basis"] != "claude_only":
            continue
        name = row["subject"]
        mechanism = vocabulary[row["mechanism"]]
        body = bodies.get(name) or item_bodies.get(f"item_{name}") or {}
        fields = {
            key: body[key]
            for key in ("AbilityBehavior", "AbilityUnitTargetTeam", "AbilityUnitTargetType")
            if key in body
        }
        groups.append(
            {
                "review_id": row["review_id"],
                "subject": name,
                "subject_zh": row["subject_zh"],
                "mechanism": row["mechanism"],
                "mechanism_zh": mechanism["zh"],
                "definition": mechanism["definition"],
                "definition_note": mechanism.get("note", ""),
                "condition": row["condition"],
                "evidence": row["quotes"],
                "game_file_fields": fields,
                "context": hero_context(name) if name in abilities else item_context(name),
            }
        )
    (OUT / "batches").mkdir(exist_ok=True)
    for old in (OUT / "batches").glob("*.json"):
        old.unlink()
    for index in range(0, len(groups), BATCH_SIZE):
        path = OUT / "batches" / f"batch-{index // BATCH_SIZE + 1:03d}.json"
        path.write_text(
            json.dumps(groups[index : index + BATCH_SIZE], ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
    print("groups", len(groups), "batches", (len(groups) + BATCH_SIZE - 1) // BATCH_SIZE)


if __name__ == "__main__":
    main()
