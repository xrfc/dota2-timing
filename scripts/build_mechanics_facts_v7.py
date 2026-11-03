"""Build MK-T3 reviewed facts v7 and evaluate MK-T4 rules on them (U70).

Writes to a new directory only; earlier packages are untouched.

    PYTHONPATH=src python scripts/build_mechanics_facts_v7.py \
        --output knowledge/mechanics/extractions/v7
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_mechanics_facts_v4 as v4script  # noqa: E402
import build_mechanics_facts_v6 as v6script  # noqa: E402

from dota_items.data.mechanics import load_enums, load_vocabulary  # noqa: E402
from dota_items.data.mechanics_facts_v7 import build_reviewed  # noqa: E402
from dota_items.data.mechanics_interactions import evaluate_rule, load_rules  # noqa: E402

ROOT = v4script.ROOT
VOCABULARY = f"{v4script.MECH}/vocabulary-v7.json"
NOTES = f"{v4script.MECH}/skill-notes-v1.json"
RULES = f"{v4script.MECH}/rules-v1.json"
INPUTS = (
    *(name for name in v6script.INPUTS if not name.endswith("vocabulary-v6.json")),
    VOCABULARY,
    NOTES,
    RULES,
)
IMPLEMENTATION = (
    *v6script.IMPLEMENTATION,
    "src/dota_items/data/mechanics_facts_v7.py",
    "src/dota_items/data/mechanics_interactions.py",
    "scripts/build_mechanics_facts_v7.py",
)
ITEMS_TXT = "knowledge/game-files/snapshots/2026-11-03-items/sources/scripts/npc/items.txt"


def root_disabled_subjects(repo):
    subjects = {
        name
        for name, body in v6script.load_ability_bodies(repo).items()
        if "ROOT_DISABLES" in str(body.get("AbilityBehavior", ""))
    }
    spec_path = repo / "scripts/check_break_against_game_files.py"
    module = v4script.importlib.util.module_from_spec(
        v4script.importlib.util.spec_from_file_location("check_break", spec_path)
    )
    module.__spec__.loader.exec_module(module)
    tree = module.parse_keyvalues((repo / ITEMS_TXT).read_text(encoding="utf-8", errors="replace"))
    for name, body in tree.get("DOTAAbilities", tree).items():
        if isinstance(body, dict) and "ROOT_DISABLES" in str(body.get("AbilityBehavior", "")):
            subjects.add(name.removeprefix("item_"))
    return subjects


def load_json(repo, name):
    return json.loads((repo / name).read_text(encoding="utf-8"))


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    sources = v6script.load_sources(repo)
    sources["skill_notes"] = load_json(repo, NOTES)["notes"]
    doc = build_reviewed(sources)
    registry = load_json(repo, "knowledge/hero-capabilities/hero-registry.json")
    enums = load_enums(load_json(repo, f"{v4script.MECH}/enums-v1.json"), registry["heroes"])
    terms = load_vocabulary(load_json(repo, VOCABULARY), enums)
    rules = load_rules(load_json(repo, RULES), terms)
    fields = {"ROOT_DISABLES": root_disabled_subjects(repo)}
    evaluation = {
        "schema": "mechanics-rules-evaluation/1",
        "rules": [
            {"id": rule["id"], "zh": rule["zh"], **evaluate_rule(rule, doc, fields)}
            for rule in rules
        ],
    }
    output.mkdir(parents=True)
    for name, value in (
        ("facts-v7.json", doc),
        ("delta-vs-v3.json", v4script.delta_of(doc)),
        ("rules-evaluation.json", evaluation),
    ):
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
    return doc, evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    print(json.dumps(run(args.output)[0]["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
