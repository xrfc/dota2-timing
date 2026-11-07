"""Build the derived layer from facts v14, through a private copy of the v3 builder.

    PYTHONPATH=src python scripts/build_mechanics_derived_v4.py \
        --output knowledge/mechanics/profiles/derived-v4
"""

import argparse
import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTS = "knowledge/mechanics/extractions/v14/facts-v14.json"
EVALUATION = "knowledge/mechanics/extractions/v14/rules-evaluation.json"


def base():
    path = ROOT / "scripts/build_mechanics_derived_v3.py"
    spec = importlib.util.spec_from_file_location("_derived_v4_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = (module.FACTS, module.EVALUATION)
    module.FACTS, module.EVALUATION = FACTS, EVALUATION
    module.INPUTS = (FACTS, EVALUATION, *(n for n in module.INPUTS if n not in old))
    module.IMPLEMENTATION = (*module.IMPLEMENTATION, "scripts/build_mechanics_derived_v4.py")
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
