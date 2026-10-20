"""Run the proposed train/validation comparison after approving its research protocol."""

import argparse
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

from dota_items.data.purchase_snapshot import verify_snapshot
from dota_items.modeling.purchase_sensitivity import compare
from dota_items.storage import file_hash, json_bytes


def code_state():
    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError:
        return {"revision": None, "dirty": None}
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "dirty": bool(status.stdout) if status.returncode == 0 else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("summary", "snapshot", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument(
        "--allow-producer-migration",
        action="store_true",
        help="Explicit public-reader/1 compatibility replay; not training authorization",
    )
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Refusing to overwrite experiment evidence")
    options = {"allow_producer_migration": True} if args.allow_producer_migration else {}
    snapshot = verify_snapshot(args.snapshot, args.summary, **options)
    result = compare(snapshot)
    result["provenance"] = {
        "code": code_state(),
        "versions": {
            "python": platform.python_version(),
            "numpy": version("numpy"),
            "scikit_learn": version("scikit-learn"),
        },
        "summary_sha256": file_hash(args.summary),
        "snapshot_sha256": file_hash(args.snapshot),
        "source_reconstruction_verified": True,
        "producer_migration": "public-reader/1" if args.allow_producer_migration else None,
        "reconstruction_mode": (
            "registered-producer-compatible" if args.allow_producer_migration else "strict"
        ),
        "implementation": {
            str(p): file_hash(p)
            for p in [
                Path(__file__),
                Path("src/dota_items/modeling/purchase_sensitivity.py"),
                Path("src/dota_items/modeling/purchase_baseline.py"),
                Path("src/dota_items/data/purchase_snapshot.py"),
                Path("src/dota_items/data/producer_migration.py"),
            ]
        },
    }
    with args.output.open("xb") as stream:
        stream.write(json_bytes(result))
    print(args.output)


if __name__ == "__main__":
    main()
