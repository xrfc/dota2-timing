"""Build reviewed facts v14 from the frozen v13 package and evaluate rules v7 (U97, U98).

Writes to a new directory only. Every file read is declared and hashed before and after.

    PYTHONPATH=src python scripts/build_mechanics_facts_v14.py \
        --output knowledge/mechanics/extractions/v14
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_mechanics_facts_v4 as v4script  # noqa: E402
import build_mechanics_facts_v7 as v7script  # noqa: E402
import build_mechanics_facts_v13 as v13script  # noqa: E402

from dota_items.data.mechanics import load_enums, load_vocabulary  # noqa: E402
from dota_items.data.mechanics_facts_v14 import build_reviewed  # noqa: E402
from dota_items.data.mechanics_graph_v2 import annotate_evaluation  # noqa: E402
from dota_items.data.mechanics_interactions import evaluate_rule, load_rules  # noqa: E402

ROOT = v4script.ROOT
BASE = f"{v4script.MECH}/extractions/v13/facts-v13.json"
VOCABULARY = v13script.VOCABULARY
RULES = v13script.RULES
REGISTRY = v13script.REGISTRY
ENUMS = v13script.ENUMS
INPUTS_FILE = f"{v4script.REVIEWS}/v14-inputs-001.json"
FEEDBACK = f"{v4script.REVIEWS}/u5-spot-check-002/verdicts-2026-11-06.jsonl"
IMPLEMENTATION = (
    *v13script.IMPLEMENTATION,
    "src/dota_items/data/mechanics_facts_v14.py",
    "scripts/build_mechanics_facts_v14.py",
)


def declared_inputs(repo=ROOT):
    heroes = sorted(
        path.relative_to(repo).as_posix() for path in (repo / v13script.HERO_SCRIPTS).glob("*.txt")
    )
    return (
        BASE,
        INPUTS_FILE,
        FEEDBACK,
        VOCABULARY,
        RULES,
        REGISTRY,
        ENUMS,
        *v13script.GAME_FILES,
        *heroes,
    )


def _digest_all(repo, names):
    return {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in names}


IMPLEMENTATION_AT_IMPORT = _digest_all(ROOT, IMPLEMENTATION)


def load_json(repo, name):
    return json.loads((repo / name).read_text(encoding="utf-8"))


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    before = _digest_all(repo, declared_inputs(repo))
    feedback = [{**row, "file": FEEDBACK} for row in v4script.read_jsonl(repo, FEEDBACK)]
    doc = build_reviewed(load_json(repo, BASE), load_json(repo, INPUTS_FILE), feedback)
    registry = load_json(repo, REGISTRY)
    enums = load_enums(load_json(repo, ENUMS), registry["heroes"])
    terms = load_vocabulary(load_json(repo, VOCABULARY), enums)
    rules = load_rules(load_json(repo, RULES), terms)
    fields = {"ROOT_DISABLES": v7script.root_disabled_subjects(repo)}
    evaluation = annotate_evaluation(
        {
            "schema": "mechanics-rules-evaluation/1",
            "rules": [
                {"id": rule["id"], "zh": rule["zh"], **evaluate_rule(rule, doc, fields)}
                for rule in rules
            ],
        },
        rules,
    )
    changed = v13script._changed(before, _digest_all(repo, declared_inputs(repo)))
    changed += v13script._changed(IMPLEMENTATION_AT_IMPORT, _digest_all(repo, IMPLEMENTATION))
    if changed:
        raise ValueError(f"Inputs changed during the build: {changed}")
    output.mkdir(parents=True)
    for name, value in (("facts-v14.json", doc), ("rules-evaluation.json", evaluation)):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": doc["extractor_version"],
        "patch_verified": False,
        "input_sha256": before,
        "implementation_sha256": IMPLEMENTATION_AT_IMPORT,
        "output_sha256": _digest_all(output, ("facts-v14.json", "rules-evaluation.json")),
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
