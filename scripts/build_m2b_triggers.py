"""M2b-T8: validate the U123 triggers on the M1 training split (descriptive, no model).

    PYTHONPATH=src python scripts/build_m2b_triggers.py \
        --snapshot reports/m1-match-table-2026-10-30-v1 --output reports/m2b-triggers-<date>-v1
"""

import argparse
import json
from pathlib import Path

from dota_items.data.match_snapshot import load_snapshot
from dota_items.data.match_snapshot import write_new_json as write
from dota_items.data.mechanics_current import load_current, read_current
from dota_items.modeling import situational_triggers as st
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
SPEC = "knowledge/situational-items/triggers-v2.json"
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
IMPLEMENTATION = (
    "scripts/build_m2b_triggers.py",
    "src/dota_items/modeling/situational_triggers.py",
    "src/dota_items/modeling/situational_items.py",
    "src/dota_items/modeling/situational_reference.py",
)


def run(snapshot, output, repo=ROOT):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError("Output exists")
    before = {name: file_hash(repo / name) for name in (*IMPLEMENTATION, SPEC)}
    spec = json.loads((repo / SPEC).read_text(encoding="utf-8"))
    registry = json.loads((repo / REGISTRY).read_text(encoding="utf-8"))["heroes"]
    current = load_current(repo)
    sums = st.trait_sums(read_current("hero_traits", repo)["traits"])
    heroes_by_rule = st.rule_heroes(read_current("rules_evaluation", repo), registry, spec)
    _, players, purchases, split = load_snapshot(snapshot)
    # Training split only; the validation split stays untouched for M4.
    result = st.validate(spec, players, purchases, split["train"], sums, heroes_by_rule)
    if {n: file_hash(repo / n) for n in before} != before:
        raise ValueError("Inputs changed during build")
    output.mkdir(parents=True)
    write(output / "triggers-validation.json", {"schema": "m2b-triggers-validation/1", **result})
    write(
        output / "manifest.json",
        {
            "schema": "m2b-triggers-run/1",
            "decision": spec["decision"],
            "snapshot": str(snapshot),
            "split": "train",
            "knowledge": {
                k: current["entries"][k]["sha256"] for k in ("hero_traits", "rules_evaluation")
            },
            "inputs": before,
            "outputs": {"triggers-validation.json": file_hash(output / "triggers-validation.json")},
        },
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.snapshot, args.output)
    for row in result["items"]:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
