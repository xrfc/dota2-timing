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
    args = parser.parse_args()
    snapshot = (
        verify_snapshot(args.verify, args.summary) if args.verify else build_snapshot(args.summary)
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
