"""U23: cross-check hero trait labels against situational item rates (M1 training split).

Descriptive statistics only. Writes JSON to a new directory.
"""

import argparse
import hashlib
import importlib.util
from pathlib import Path

from dota_items.data import hero_traits as ht
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.modeling import situational_reference as sr
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
TRAITS = "knowledge/hero-traits/hero-traits-v1.json"
IMPLEMENTATION = (
    "scripts/hero_trait_crosscheck.py",
    "scripts/train_item_timing.py",
    "src/dota_items/data/hero_traits.py",
    "src/dota_items/modeling/situational_items.py",
    "src/dota_items/modeling/situational_reference.py",
)


def _snapshot_loader():
    spec = importlib.util.spec_from_file_location(
        "train_item_timing", Path(__file__).resolve().parent / "train_item_timing.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_snapshot, module.write


def groups(traits):
    """Each trait, plus subtypes and the high-confidence subset where they differ."""
    out = {}
    for trait, labels in traits.items():
        out[trait] = set(labels)
        for sub in sorted({e.get("subtype") for e in labels.values()} - {None}):
            out[f"{trait}:{sub}"] = {h for h, e in labels.items() if e.get("subtype") == sub}
        high = {h for h, e in labels.items() if e["confidence"] == "high"}
        if high and high != out[trait]:
            out[f"{trait}:high"] = high
    return out


def run(snapshot, output, repo=ROOT):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError("Output exists")
    load_snapshot, write = _snapshot_loader()
    inputs = (*IMPLEMENTATION, REGISTRY, TRAITS)
    fingerprints = {name: file_hash(repo / name) for name in inputs}
    _, players, purchases, split = load_snapshot(snapshot)
    registry = parse_source_json(read_source_bytes(repo / REGISTRY))["heroes"]
    traits = ht.load_traits(parse_source_json(read_source_bytes(repo / TRAITS)), registry)
    trait_groups = groups(traits)
    rows = sr.trait_crosscheck(players, purchases, split["train"], trait_groups)
    if {n: file_hash(repo / n) for n in inputs} != fingerprints:
        raise ValueError("Inputs changed during build")
    output.mkdir(parents=True)
    write(
        output / "crosscheck.json",
        {
            "schema": "hero-trait-crosscheck/1",
            "group_sizes": {g: len(h) for g, h in trait_groups.items()},
            "rows": rows,
        },
    )
    write(
        output / "manifest.json",
        {
            "schema": "hero-trait-crosscheck-run/1",
            "snapshot": str(snapshot),
            "snapshot_manifest_sha256": hashlib.sha256(
                read_source_bytes(snapshot / "manifest.json")
            ).hexdigest(),
            "split": "train",
            "decision": "U23",
            "inputs": fingerprints,
            "outputs": {"crosscheck.json": file_hash(output / "crosscheck.json")},
        },
    )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(f"rows={len(run(args.snapshot, args.output))}")


if __name__ == "__main__":
    main()
