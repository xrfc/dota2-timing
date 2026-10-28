"""Read-only source replay, separate from fitting and experiment execution."""

from pathlib import Path

from dota_items.data.whole_log_snapshot import build_whole_log_bundle, load
from dota_items.modeling.batch import adapt_snapshot
from dota_items.storage import file_hash, json_bytes

from .io import check_unchanged


def verify_inputs(parent, cohort):
    """Rebuild every cohort payload, not just its self-declared digest."""
    cohort = Path(cohort)
    receipt_path = cohort / "complete.json"
    receipt_sha = file_hash(receipt_path)
    receipt = load(receipt_path)
    snapshot, sources, protected = build_whole_log_bundle(parent)
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
    if (
        receipt.get("schema_version") != "whole-log-cohort-complete/1"
        or set(receipt.get("sha256", {})) != set(payloads)
        or receipt.get("training_executed") is not False
    ):
        raise ValueError("Invalid cohort completion receipt")
    protected = dict(protected)
    protected[str(receipt_path)] = receipt_sha
    for name, value in payloads.items():
        path = cohort / name
        if path.read_bytes() != json_bytes(value) or file_hash(path) != receipt["sha256"][name]:
            raise ValueError(f"Cohort replay or hash mismatch: {name}")
        protected[str(path)] = receipt["sha256"][name]
    check_unchanged(protected, message="Protected input or implementation changed")
    return snapshot, sources, protected
