"""Build or verify the grouped source-purchase-log modeling snapshot offline."""

import argparse
from pathlib import Path

from dota_items.data.purchase_snapshot import build_snapshot, verify_snapshot
from dota_items.storage import json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    parser.add_argument(
        "--allow-producer-migration",
        action="store_true",
        help="Explicit public-reader/1 compatibility replay; not ignore-hashes",
    )
    args = parser.parse_args()
    options = {"allow_producer_migration": True} if args.allow_producer_migration else {}
    snapshot = (
        verify_snapshot(args.verify, args.summary, **options)
        if args.verify
        else build_snapshot(args.summary, **options)
    )
    if args.output:
        with args.output.open("xb") as stream:
            stream.write(json_bytes(snapshot))
    print(
        {
            "samples": len(snapshot["samples"]),
            "splits": {k: len(v) for k, v in snapshot["splits"].items()},
            "player_disjoint": snapshot["player_overlap"]["player_disjoint_verified"],
            "train_model_items": snapshot["train_model_items"],
            "training_executed": False,
        }
    )


if __name__ == "__main__":
    main()
