"""Offline whole-source-log 11-item relabeling of the frozen random-v2 cohort."""

import argparse
from pathlib import Path

from dota_items.data.whole_log_snapshot import build_whole_log_bundle, load
from dota_items.modeling.batch import adapt_snapshot
from dota_items.storage import file_hash, json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify and (args.output.exists() or args.output.is_symlink()):
        parser.error("Refusing to overwrite output")
    snapshot, sources, protected = build_whole_log_bundle(args.parent)
    shapes = {}
    for split in ("train", "validation"):
        batch = adapt_snapshot(snapshot, split)
        shapes[split] = {
            "X": list(batch.x.shape),
            "y": list(batch.y.shape),
            "mask": list(batch.mask.shape),
        }
    payloads = {
        "snapshot.json": snapshot,
        "sources.json": sources,
        "split.json": {
            "policy": snapshot["split_policy"],
            "members": snapshot["splits"],
            "sha256": snapshot["membership_sha256"],
        },
        "report.json": {
            "task_contract": snapshot["task"]["contract"],
            "candidate_count": len(snapshot["samples"]),
            "split_counts": {k: len(v) for k, v in snapshot["splits"].items()},
            "membership_sha256": snapshot["membership_sha256"],
            "consumer_shapes": shapes,
            "support": snapshot["support"],
            "old_five_label_replay": "all_samples_equal",
            "training_executed": False,
            "features_and_membership": "copied_unchanged_from_parent",
        },
        "protection.json": {"files": protected, "unchanged": True},
    }
    for path, sha in protected.items():
        if file_hash(Path(path)) != sha:
            raise ValueError("Protected input changed")
    if args.verify:
        receipt = load(args.output / "complete.json")
        if receipt.get("schema_version") != "whole-log-cohort-complete/1" or set(
            receipt.get("sha256", {})
        ) != set(payloads):
            raise ValueError("Invalid completion receipt")
        for name, value in payloads.items():
            path = args.output / name
            if path.read_bytes() != json_bytes(value) or file_hash(path) != receipt["sha256"][name]:
                raise ValueError(f"Replay or hash mismatch: {name}")
        print("Whole-log replay and bundle hashes verified; no training")
        return
    args.output.mkdir(parents=False, exist_ok=False)
    for name, value in payloads.items():
        with (args.output / name).open("xb") as stream:
            stream.write(json_bytes(value))
    for path, sha in protected.items():
        if file_hash(Path(path)) != sha:
            raise ValueError("Protected input changed before completion")
    with (args.output / "complete.json").open("xb") as stream:
        stream.write(
            json_bytes(
                {
                    "schema_version": "whole-log-cohort-complete/1",
                    "sha256": {name: file_hash(args.output / name) for name in payloads},
                    "training_executed": False,
                }
            )
        )
    print(json_bytes(payloads["report.json"]).decode())


if __name__ == "__main__":
    main()
