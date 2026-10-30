"""M2b-T3/T4: train the first-situational-item model on the M1 snapshot and evaluate once.

Writes JSON only. Output directory must be new. Protocol: docs/m2b-design.md.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.modeling import situational_items as si
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
IMPLEMENTATION = (
    "scripts/train_situational_items.py",
    "scripts/train_item_timing.py",
    "src/dota_items/modeling/situational_items.py",
)


def _snapshot_loader():
    spec = importlib.util.spec_from_file_location(
        "train_item_timing", Path(__file__).resolve().parent / "train_item_timing.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_snapshot, module.write


def run(snapshot, output, repo=ROOT):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError("Output exists")
    load_snapshot, write = _snapshot_loader()
    implementation = {name: file_hash(repo / name) for name in IMPLEMENTATION}
    registry_hash = file_hash(repo / REGISTRY)
    _, players, purchases, split = load_snapshot(snapshot)
    samples = si.build_samples(players, purchases)
    train_ids, valid_ids = set(split["train"]), set(split["validation"])
    train = [s for s in samples if s["match_id"] in train_ids]
    valid = [s for s in samples if s["match_id"] in valid_ids]
    spec = si.feature_spec(parse_source_json(read_source_bytes(repo / REGISTRY))["heroes"])
    model = si.fit(train, spec)
    result = si.evaluate(model, valid, spec)
    result["top_coefficients"] = si.top_coefficients(model)
    if {n: file_hash(repo / n) for n in IMPLEMENTATION} != implementation or file_hash(
        repo / REGISTRY
    ) != registry_hash:
        raise ValueError("Inputs changed during training")
    output.mkdir(parents=True)
    write(output / "model.json", {"schema": "m2b-situational-model/1", **model})
    write(output / "results.json", result)
    write(
        output / "manifest.json",
        {
            "schema": "m2b-situational-run/1",
            "snapshot": str(snapshot),
            "snapshot_manifest_sha256": hashlib.sha256(
                read_source_bytes(snapshot / "manifest.json")
            ).hexdigest(),
            "hero_registry_sha256": registry_hash,
            "train_samples": len(train),
            "validation_samples": len(valid),
            "protocol": "docs/m2b-design.md (frozen 2026-10-31, before training)",
            "implementation": implementation,
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "authorization": "U18 (user 2026-10-31): this run only",
        },
    )
    return {
        "train": len(train),
        "validation": len(valid),
        "C": model["C"],
        "passed": result["passed"],
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--snapshot", required=True)
    cli.add_argument("--output", required=True)
    args = cli.parse_args()
    print(json.dumps(run(args.snapshot, args.output)))
