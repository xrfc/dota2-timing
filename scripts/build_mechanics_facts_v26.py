"""Build reviewed facts v26 from the frozen v25 package; U126 Huskar rows and wording.

Writes to a new directory only. Every file read is declared and hashed before and after.

    PYTHONPATH=src python scripts/build_mechanics_facts_v26.py \
        --output knowledge/mechanics/extractions/v26
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
from dota_items.data.mechanics_conditions import add_conditions  # noqa: E402
from dota_items.data.mechanics_facts_v19 import add_not_computed  # noqa: E402
from dota_items.data.mechanics_facts_v26 import build_reviewed  # noqa: E402
from dota_items.data.mechanics_graph_v2 import annotate_evaluation  # noqa: E402
from dota_items.data.mechanics_interactions import evaluate_rule  # noqa: E402
from dota_items.data.mechanics_rules_v8 import expand_rules  # noqa: E402
from dota_items.data.mechanics_rules_v11 import load_rules_v11  # noqa: E402

ROOT = v4script.ROOT
BASE = f"{v4script.MECH}/extractions/v25/facts-v25.json"
VOCABULARY = f"{v4script.MECH}/vocabulary-v15.json"
RULES = f"{v4script.MECH}/rules-v13.json"
REGISTRY = v13script.REGISTRY
ENUMS = f"{v4script.MECH}/enums-v2.json"
INPUTS_FILE = f"{v4script.REVIEWS}/v26-inputs-001.json"
IMPLEMENTATION = (
    *v13script.IMPLEMENTATION,
    "src/dota_items/data/mechanics_facts_v15.py",
    "src/dota_items/data/mechanics_rules_v8.py",
    "src/dota_items/data/mechanics_facts_v16.py",
    "src/dota_items/data/mechanics_feedback.py",
    "src/dota_items/data/mechanics_facts_v17.py",
    "src/dota_items/data/mechanics_conditions.py",
    "scripts/build_mechanics_facts_v17.py",
    "src/dota_items/data/mechanics_facts_v18.py",
    "scripts/build_mechanics_facts_v18.py",
    "src/dota_items/data/mechanics_rules_v11.py",
    "src/dota_items/data/mechanics_facts_v19.py",
    "scripts/build_mechanics_facts_v19.py",
    "src/dota_items/data/mechanics_facts_v20.py",
    "scripts/build_mechanics_facts_v20.py",
    "src/dota_items/data/mechanics_facts_v21.py",
    "scripts/build_mechanics_facts_v21.py",
    "src/dota_items/data/mechanics_facts_v22.py",
    "scripts/build_mechanics_facts_v22.py",
    "src/dota_items/data/mechanics_facts_v23.py",
    "scripts/build_mechanics_facts_v23.py",
    "src/dota_items/data/mechanics_facts_v21.py",
    "src/dota_items/data/mechanics_facts_v26.py",
    "scripts/build_mechanics_facts_v26.py",
)


def declared_inputs(repo=ROOT):
    heroes = sorted(
        path.relative_to(repo).as_posix() for path in (repo / v13script.HERO_SCRIPTS).glob("*.txt")
    )
    return (
        BASE,
        INPUTS_FILE,
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
    registry = load_json(repo, REGISTRY)
    enums = load_enums(load_json(repo, ENUMS), registry["heroes"])
    terms = load_vocabulary(load_json(repo, VOCABULARY), enums)
    doc = build_reviewed(load_json(repo, BASE), load_json(repo, INPUTS_FILE))
    rules = expand_rules(load_rules_v11(load_json(repo, RULES), terms), registry["heroes"], doc)
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
    evaluation = add_conditions(evaluation, rules, doc, registry["heroes"])
    evaluation = add_not_computed(evaluation, rules)
    changed = v13script._changed(before, _digest_all(repo, declared_inputs(repo)))
    changed += v13script._changed(IMPLEMENTATION_AT_IMPORT, _digest_all(repo, IMPLEMENTATION))
    if changed:
        raise ValueError(f"Inputs changed during the build: {changed}")
    output.mkdir(parents=True)
    expanded = {"schema": "mechanics-rules/1", "source": RULES, "rules": rules}
    for name, value in (
        ("facts-v26.json", doc),
        ("rules-evaluation.json", evaluation),
        ("rules-expanded.json", expanded),
    ):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": doc["extractor_version"],
        "patch_verified": False,
        "input_sha256": before,
        "implementation_sha256": IMPLEMENTATION_AT_IMPORT,
        "output_sha256": _digest_all(
            output, ("facts-v26.json", "rules-evaluation.json", "rules-expanded.json")
        ),
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
