"""Build the derived layer from facts v15 and rules v8, through a private copy of the v3 builder.

Rules come from `rules-expanded.json`, where hero-named targets are already listed. Edges whose
hero is an exception only under a condition carry that condition (U100). Retired items follow
`retired-items-v2.json` (U99).

    PYTHONPATH=src python scripts/build_mechanics_derived_v5.py \\
        --output knowledge/mechanics/profiles/derived-v5
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from dota_items.data.mechanics_rules_v8 import mark_conditional_edges

ROOT = Path(__file__).resolve().parents[1]
FACTS = "knowledge/mechanics/extractions/v15/facts-v15.json"
EVALUATION = "knowledge/mechanics/extractions/v15/rules-evaluation.json"
RULES = "knowledge/mechanics/extractions/v15/rules-expanded.json"
STATUS = "knowledge/mechanics/retired-items-v2.json"


def base():
    path = ROOT / "scripts/build_mechanics_derived_v3.py"
    spec = importlib.util.spec_from_file_location("_derived_v5_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = (module.FACTS, module.EVALUATION, module.RULES, module.STATUS)
    module.FACTS, module.EVALUATION, module.RULES, module.STATUS = FACTS, EVALUATION, RULES, STATUS
    module.INPUTS = (FACTS, EVALUATION, RULES, STATUS, *(n for n in module.INPUTS if n not in old))
    rules = json.loads((ROOT / RULES).read_text(encoding="utf-8"))["rules"]
    annotate = module.annotate_graph
    module.annotate_graph = lambda graph, r, doc: mark_conditional_edges(
        annotate(graph, r, doc), rules
    )
    module.IMPLEMENTATION = (
        *module.IMPLEMENTATION,
        "src/dota_items/data/mechanics_rules_v8.py",
        "scripts/build_mechanics_derived_v5.py",
    )
    module.IMPLEMENTATION_AT_IMPORT = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in module.IMPLEMENTATION
    }
    return module


def run(output, repo=ROOT):
    return base().run(output, repo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    result = run(args.output)
    print(len(result["heroes"]), "heroes", len(result["items"]), "items")


if __name__ == "__main__":
    main()
