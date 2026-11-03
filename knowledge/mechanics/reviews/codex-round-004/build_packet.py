"""Build blind Codex batches for game-file audit candidates (U49). Run from repo root."""

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
AUDIT = ROOT / "knowledge/mechanics/reviews/game-files-audit-001"
BATCH_SIZE = 30
SKIP_MECHANISMS = {"illusions"}


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_id(subject, mechanism):
    return hashlib.sha256(f"{subject}|{mechanism}|audit-001".encode()).hexdigest()[:20]


def main():
    breaks = load_script("check_break_against_game_files")
    snapshots = ROOT / "knowledge/game-files/snapshots"
    heroes_dir = snapshots / "2026-11-02/sources/scripts/npc"
    bodies = {}
    for path in [heroes_dir / "npc_abilities.txt", *sorted((heroes_dir / "heroes").glob("*.txt"))]:
        tree = breaks.parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
        bodies.update(breaks.iter_abilities(tree))
    items_path = snapshots / "2026-11-03-items/sources/scripts/npc/items.txt"
    item_tree = breaks.parse_keyvalues(items_path.read_text(encoding="utf-8", errors="replace"))
    items = {
        name.removeprefix("item_"): body
        for name, body in item_tree.get("DOTAAbilities", item_tree).items()
        if name.startswith("item_") and isinstance(body, dict)
    }
    localization = breaks.load_localization(snapshots / "2026-11-02")
    registry = json.loads(
        (ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text(encoding="utf-8")
    )
    abilities = {a["name"]: (h, a) for h in registry["heroes"] for a in h["abilities"]}
    constants = json.loads(
        (ROOT / "knowledge/items/sources/dotaconstants-items.json").read_text(encoding="utf-8")
    )
    vocabulary = {
        m["id"]: m
        for m in json.loads(
            (ROOT / "knowledge/mechanics/vocabulary-v3.json").read_text(encoding="utf-8")
        )["mechanisms"]
    }

    wanted = []
    triage = json.loads((AUDIT / "keyword-triage.json").read_text(encoding="utf-8"))
    for mechanism, row in triage.items():
        if mechanism in SKIP_MECHANISMS:
            continue
        for hit in row["keyword_no_group"]:
            if hit["has_base_value"]:
                keys = [k for k, kind in hit["keys"].items() if kind == "base"]
                wanted.append((hit["subject"], mechanism, keys, "field_name"))
    strict = json.loads((AUDIT / "strict-field-checks.json").read_text(encoding="utf-8"))
    for hit in strict["unit_target_spell"]["present_without_accepted_group"]:
        team = bodies[hit["subject"]].get("AbilityUnitTargetTeam")
        if team is None or "FRIENDLY" not in team:
            wanted.append((hit["subject"], "unit_target_spell", [], "behavior_unit_target"))
    for hit in strict["channeled"]["present_without_accepted_group"]:
        wanted.append((hit["subject"], "channeled", [], "behavior_channelled"))
    for group in strict["channeled"]["groups"]:
        if group["result"] == "accept_but_absent":
            wanted.append((group["subject"], "channeled", [], "text_without_channelled_field"))

    groups, seen = [], set()
    for subject, mechanism, keys, reason in wanted:
        if (subject, mechanism) in seen:
            continue
        seen.add((subject, mechanism))
        body = bodies.get(subject) or items.get(subject) or {}
        values = body.get("AbilityValues") if isinstance(body.get("AbilityValues"), dict) else {}
        fields = {
            "AbilityBehavior": body.get("AbilityBehavior"),
            "AbilityUnitTargetTeam": body.get("AbilityUnitTargetTeam"),
            "AbilityUnitTargetType": body.get("AbilityUnitTargetType"),
            "AbilityChannelTime": body.get("AbilityChannelTime"),
        }
        group = {
            "review_id": candidate_id(subject, mechanism),
            "subject": subject,
            "mechanism": mechanism,
            "mechanism_zh": vocabulary[mechanism]["zh"],
            "definition": vocabulary[mechanism]["definition"],
            "definition_note": vocabulary[mechanism].get("note", ""),
            "lead": reason,
            "game_file_values": {key: values.get(key) for key in keys},
            "game_file_labels": {
                key: localization.get(f"DOTA_Tooltip_ability_{subject}_{key}")
                or localization.get(f"DOTA_Tooltip_ability_item_{subject}_{key}")
                for key in keys
            },
            "game_file_fields": {k: v for k, v in fields.items() if v is not None},
        }
        if subject in abilities:
            hero, ability = abilities[subject]
            group["subject_zh"] = f"{hero['name_zh']}·{ability['name_zh']}"
            group["context"] = {
                key: ability[key]
                for key in (
                    "description_en",
                    "description_zh",
                    "notes_en",
                    "notes_zh",
                    "upgrade_text",
                    "innate",
                    "granted_by_scepter",
                    "granted_by_shard",
                )
                if ability.get(key) not in (None, "", [], {})
            }
        else:
            entry = constants[subject]
            group["subject_zh"] = entry.get("dname", subject)
            group["context"] = {
                key: entry[key]
                for key in ("abilities", "notes", "attrib", "tier", "hint")
                if entry.get(key) not in (None, "", [], {})
            }
        groups.append(group)
    for old in (OUT / "batches").glob("*.json"):
        old.unlink()
    (OUT / "batches").mkdir(exist_ok=True)
    for index in range(0, len(groups), BATCH_SIZE):
        path = OUT / "batches" / f"batch-{index // BATCH_SIZE + 1:03d}.json"
        path.write_text(
            json.dumps(groups[index : index + BATCH_SIZE], ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
    print("groups", len(groups), "batches", (len(groups) + BATCH_SIZE - 1) // BATCH_SIZE)


if __name__ == "__main__":
    main()
