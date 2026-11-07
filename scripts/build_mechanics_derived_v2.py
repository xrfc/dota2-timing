"""Build the derived layer from facts v12, vocabulary v11, rules v5 and trait mapping v3 (U83, U88).

Reuses the v1 builder through a private copy of its module, so derived-v1 stays reproducible.

    PYTHONPATH=src python scripts/build_mechanics_derived_v2.py \
        --output knowledge/mechanics/profiles/derived-v2
"""

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTS = "knowledge/mechanics/extractions/v12/facts-v12.json"
EVALUATION = "knowledge/mechanics/extractions/v12/rules-evaluation.json"
VOCABULARY = "knowledge/mechanics/vocabulary-v11.json"
RULES = "knowledge/mechanics/rules-v5.json"
MAPPING = "knowledge/hero-traits/trait-mapping-v3.json"


def _base():
    path = ROOT / "scripts/build_mechanics_derived.py"
    spec = importlib.util.spec_from_file_location("_derived_v2_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FACTS, module.EVALUATION, module.VOCABULARY = FACTS, EVALUATION, VOCABULARY
    module.RULES, module.MAPPING = RULES, MAPPING
    module.INPUTS = (
        FACTS,
        EVALUATION,
        module.RULES,
        VOCABULARY,
        module.REGISTRY,
        module.STATUS,
        module.ITEM_NAMES,
        module.TRAITS_V1,
        module.MAPPING,
    )
    module.IMPLEMENTATION = (*module.IMPLEMENTATION, "scripts/build_mechanics_derived_v2.py")
    return module


def run(output, repo=ROOT):
    return _base().run(output, repo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    result = run(args.output)
    print(len(result["heroes"]), "heroes", len(result["items"]), "items")


if __name__ == "__main__":
    main()
