"""Build MK-T3 reviewed facts v5: v4 inputs plus Codex rounds 5-6 (U60).

Writes to a new directory only; earlier packages are untouched.

    PYTHONPATH=src python scripts/build_mechanics_facts_v5.py \
        --output knowledge/mechanics/extractions/v5
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_mechanics_facts_v4 as v4script  # noqa: E402

from dota_items.data.mechanics_facts_v5 import build_reviewed  # noqa: E402

ROOT = v4script.ROOT
ROUND5 = f"{v4script.REVIEWS}/codex-round-005/codex-review.jsonl"
ROUND6 = f"{v4script.REVIEWS}/codex-round-006/codex-review.jsonl"
VOCABULARY = f"{v4script.MECH}/vocabulary-v5.json"
INPUTS = (
    *(name for name in v4script.INPUTS if not name.endswith("vocabulary-v4.json")),
    VOCABULARY,
    ROUND5,
    ROUND6,
)
IMPLEMENTATION = (
    *v4script.IMPLEMENTATION,
    "src/dota_items/data/mechanics_facts_v5.py",
    "scripts/build_mechanics_facts_v5.py",
)


def load_sources(repo):
    sources = v4script.load_sources(repo)
    for row in v4script.read_jsonl(repo, ROUND5):
        sources["codex"][row["review_id"]] = row["decision"]
    registry = json.loads(
        (repo / "knowledge/hero-capabilities/hero-registry.json").read_text(encoding="utf-8")
    )
    abilities = {a["name"]: a for h in registry["heroes"] for a in h["abilities"]}
    for row in v4script.read_jsonl(repo, ROUND6):
        ability = abilities.get(row["subject"])
        condition = v4script.ability_condition(ability) if ability else v4script.ITEM
        sources["audit"].append({**row, "condition": condition})
    return sources


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    doc = build_reviewed(load_sources(repo))
    output.mkdir(parents=True)
    for name, value in (("facts-v5.json", doc), ("delta-vs-v3.json", v4script.delta_of(doc))):
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
