"""Run the proposed train/validation comparison after approving its research protocol."""

import argparse
from pathlib import Path

from dota_items.data.purchase_snapshot import verify_snapshot
from dota_items.modeling.purchase_sensitivity import compare
from dota_items.storage import file_hash, json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("summary", "snapshot", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite experiment evidence")
    snapshot = verify_snapshot(args.snapshot, args.summary)
    result = compare(snapshot)
    result["provenance"] = {
        "summary_sha256": file_hash(args.summary),
        "snapshot_sha256": file_hash(args.snapshot),
        "source_reconstruction_verified": True,
        "implementation": {
            str(p): file_hash(p)
            for p in [
                Path(__file__),
                Path("src/dota_items/modeling/purchase_sensitivity.py"),
                Path("src/dota_items/modeling/purchase_baseline.py"),
            ]
        },
    }
    with args.output.open("xb") as stream:
        stream.write(json_bytes(result))
    print(args.output)


if __name__ == "__main__":
    main()
