"""Reconstruct the snapshot and diagnose a hash-bound baseline without refitting."""

import argparse
import json
from pathlib import Path

from dota_items.data.purchase_snapshot import verify_snapshot
from dota_items.modeling.purchase_diagnostics import diagnose
from dota_items.storage import file_hash, json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("summary", "snapshot", "baseline", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite existing diagnostic evidence")
    baseline = json.loads(args.baseline.read_text())
    for name in ("snapshot", "summary"):
        if baseline["provenance"][f"{name}_sha256"] != file_hash(getattr(args, name)):
            parser.error(f"Baseline {name} hash mismatch")
    snapshot = verify_snapshot(args.snapshot, args.summary)
    result = diagnose(snapshot, baseline)
    result["provenance"] = {
        "inputs": {
            name: file_hash(getattr(args, name)) for name in ("summary", "snapshot", "baseline")
        },
        "source_reconstruction_verified": True,
        "implementation": {
            str(p): file_hash(p)
            for p in (Path(__file__), Path("src/dota_items/modeling/purchase_diagnostics.py"))
        },
    }
    with args.output.open("xb") as stream:
        stream.write(json_bytes(result))
    print(json.dumps({i: r["validation"]["brier_delta"] for i, r in result["items"].items()}))


if __name__ == "__main__":
    main()
