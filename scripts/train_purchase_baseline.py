"""Verify frozen sources, then run the offline exploratory baseline protocol."""

import argparse
import platform
from pathlib import Path

import numpy as np
import sklearn

from dota_items.data.purchase_snapshot import verify_snapshot
from dota_items.modeling.purchase_baseline import run_experiment
from dota_items.storage import file_hash, json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=500)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite existing experiment evidence")
    snapshot = verify_snapshot(args.snapshot, args.summary)
    result = run_experiment(snapshot, repeats=args.bootstrap)
    result["provenance"] = {
        "snapshot_sha256": file_hash(args.snapshot),
        "summary_sha256": file_hash(args.summary),
        "source_reconstruction_verified": True,
        "implementation_sha256": {
            str(p): file_hash(p)
            for p in (Path(__file__), Path("src/dota_items/modeling/purchase_baseline.py"))
        },
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }
    with args.output.open("xb") as stream:
        stream.write(json_bytes(result))
    print(result["macro"]["test"]["all"])


if __name__ == "__main__":
    main()
