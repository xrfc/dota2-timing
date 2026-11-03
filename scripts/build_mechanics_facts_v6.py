"""Build MK-T3 reviewed facts v6: v5 inputs plus Codex round 7 (U65).

Writes to a new directory only; earlier packages are untouched.

    PYTHONPATH=src python scripts/build_mechanics_facts_v6.py \
        --output knowledge/mechanics/extractions/v6
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_mechanics_facts_v4 as v4script  # noqa: E402
import build_mechanics_facts_v5 as v5script  # noqa: E402

from dota_items.data.mechanics_facts_v6 import build_reviewed  # noqa: E402

ROOT = v4script.ROOT
ROUND7 = f"{v4script.REVIEWS}/codex-round-007/codex-review.jsonl"
VOCABULARY = f"{v4script.MECH}/vocabulary-v6.json"
INPUTS = (
    *(name for name in v5script.INPUTS if not name.endswith("vocabulary-v5.json")),
    VOCABULARY,
    ROUND7,
)
IMPLEMENTATION = (
    *v5script.IMPLEMENTATION,
    "src/dota_items/data/mechanics_facts_v6.py",
    "scripts/build_mechanics_facts_v6.py",
)
UPGRADE_TAGS = {"scepter_upgrade": "scepter", "shard_upgrade": "shard"}


def cooldown_field_values(body, context):
    """Cooldown numbers an upgrade changes, read from the game-file ability block."""
    tag = UPGRADE_TAGS[context]
    found = {}
    cooldown = body.get("AbilityCooldown")
    if isinstance(cooldown, dict):
        found["AbilityCooldown"] = {k: v for k, v in cooldown.items() if tag in k.lower()}
    values = body.get("AbilityValues")
    for key, value in (values if isinstance(values, dict) else {}).items():
        if "cooldown" not in key.lower():
            continue
        if isinstance(value, dict):
            bonus = {k: v for k, v in value.items() if tag in k.lower()}
            if bonus:
                found[key] = bonus
        elif tag in key.lower():
            found[key] = value
    return {key: value for key, value in found.items() if value} or None


def load_ability_bodies(repo):
    path = repo / "scripts/check_break_against_game_files.py"
    module = v4script.importlib.util.module_from_spec(
        v4script.importlib.util.spec_from_file_location("check_break", path)
    )
    module.__spec__.loader.exec_module(module)
    npc = repo / "knowledge/game-files/snapshots/2026-11-02/sources/scripts/npc"
    bodies = {}
    for file in [npc / "npc_abilities.txt", *sorted((npc / "heroes").glob("*.txt"))]:
        tree = module.parse_keyvalues(file.read_text(encoding="utf-8", errors="replace"))
        bodies.update(module.iter_abilities(tree))
    return bodies


def load_sources(repo):
    sources = v5script.load_sources(repo)
    rows = v4script.read_jsonl(repo, ROUND7)
    sources["audit"].extend(rows)
    rulings = sources["rulings"].values()
    sources["numeric_ids"] = {row["review_id"] for row in rulings if row.get("numeric_upgrade")}
    sources["extra_rows"] = [
        {
            "review_id": row["review_id"],
            "origin": "user_added",
            "subject": row["subject"],
            "subject_zh": row["subject_zh"],
            "mechanism": row["mechanism"],
            "condition": v4script.BASE,
            "decision": row["decision"],
            "basis": f"user:{row['decision_ref']}",
            "claude": None,
            "codex": None,
            "notes_zh": [row["note_zh"]],
            "break_conditions_en": [],
            "quotes": [row["source_quote"]],
            "item_status": None,
        }
        for row in rulings
        if row.get("extra_base")
    ]
    bodies = load_ability_bodies(repo)
    sources["numeric_fields"] = {
        (row["subject"], row["condition"]["context"]): cooldown_field_values(
            bodies.get(row["subject"], {}), row["condition"]["context"]
        )
        for row in rows
        if row["mechanism"] == "cooldown_reduction" and row["condition"]["context"] in UPGRADE_TAGS
    }
    return sources


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    doc = build_reviewed(load_sources(repo))
    output.mkdir(parents=True)
    for name, value in (("facts-v6.json", doc), ("delta-vs-v3.json", v4script.delta_of(doc))):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": doc["extractor_version"],
        "patch_verified": False,
        "input_sha256": {name: digest(repo / name) for name in INPUTS},
        "implementation_sha256": {name: digest(repo / name) for name in IMPLEMENTATION},
        "output_sha256": {path.name: digest(path) for path in sorted(output.iterdir())},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    print(json.dumps(run(args.output)["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
