"""Read-only whole-log handoff: source replay, baseline binding, frozen input identity."""

from pathlib import Path

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS, WHOLE_LOG_TASK_ID
from dota_items.modeling.artifacts import load_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.storage import digest, file_hash, now

from .diagnostics import verify as verify_baseline
from .inputs import verify_inputs
from .io import check_unchanged, load, write_exclusive

SCHEMA = "whole-log-input-handoff/1"


def input_identity(snapshot):
    """Row order, label/mask and encoding are part of comparison identity."""
    if (
        snapshot["task"]["contract"]["task_id"] != WHOLE_LOG_TASK_ID
        or snapshot["splits"].get("test") != []
        or any(row["split"] not in ("train", "validation") for row in snapshot["samples"])
    ):
        raise ValueError("Unexpected handoff task/split")
    shapes = {}
    for split in ("train", "validation"):
        batch = adapt_snapshot(snapshot, split)
        shapes[split] = {
            "X": list(batch.x.shape),
            "y": list(batch.y.shape),
            "mask": list(batch.mask.shape),
        }
    return {
        "task_contract": snapshot["task"]["contract"],
        "candidate_items": list(WHOLE_LOG_ITEMS),
        "preprocessing_sha256": digest(snapshot["preprocessing"]),
        "splits_sha256": digest(snapshot["splits"]),
        "rows_sha256": digest(snapshot["samples"]),
        "consumer_shapes": shapes,
    }


def read_handoff(directory):
    """Verify receipt and all protected files before reusing a handoff."""
    directory = Path(directory)
    receipt = load(directory / "complete.json")
    report_path = directory / "handoff.json"
    if (
        receipt.get("schema_version") != SCHEMA
        or receipt.get("training_executed") is not False
        or receipt.get("sha256") != {"handoff.json": file_hash(report_path)}
    ):
        raise ValueError("Invalid handoff completion receipt")
    report = load(report_path)
    if (
        report.get("schema_version") != SCHEMA
        or report.get("training_executed") is not False
        or report.get("identity_sha256") != digest(report["identity"])
        or not report.get("protected_sha256")
    ):
        raise ValueError("Invalid handoff identity")
    check_unchanged(report["protected_sha256"])
    return report


def verify(parent, cohort, baseline, *, expected=None):
    """No fit calls: a source-replayed snapshot must match the existing baseline."""
    previous = read_handoff(expected) if expected is not None else None
    snapshot, _, protected = verify_inputs(parent, cohort)
    identity = input_identity(snapshot)
    if identity["consumer_shapes"] != {
        "train": {"X": [1592, 256], "y": [1592, 11], "mask": [1592, 11]},
        "validation": {"X": [398, 256], "y": [398, 11], "mask": [398, 11]},
    }:
        raise ValueError("Unexpected approved handoff shapes")
    _, baseline_files = verify_baseline(baseline, Path(cohort) / "snapshot.json")
    # The existing diagnostic verifier binds predictions, task and preprocessing.
    # Also enforce that the historical reference really is fixed C=1.
    for family in ("frequency", "logistic"):
        model = load_model(Path(baseline) / f"{family}.model.json")
        expected_parameters = {
            "C": 1.0 if family == "logistic" else None,
            "solver": "liblinear" if family == "logistic" else None,
            "max_iter": 2000,
            "random_state": 0,
            "class_weight": None,
        }
        if model["parameters"] != expected_parameters:
            raise ValueError("Unexpected baseline parameters")
    for name, sha in baseline_files.items():
        if name in protected and protected[name] != sha:
            raise ValueError("Conflicting input hashes")
        protected[name] = sha
    # Absolute paths make reuse independent of the shell working directory.
    files = {}
    for name, sha in protected.items():
        resolved = str(Path(name).resolve())
        if resolved in files and files[resolved] != sha:
            raise ValueError("Conflicting resolved input hashes")
        files[resolved] = sha
    if previous is not None and (
        previous["identity"] != identity or previous["protected_sha256"] != files
    ):
        raise ValueError("Handoff comparison identity changed")
    check_unchanged(files)
    return {
        "schema_version": SCHEMA,
        "training_executed": False,
        "identity": identity,
        "identity_sha256": digest(identity),
        "protected_sha256": files,
        "source_replay_verified": True,
        "baseline_predictions_recomputed": True,
        "verified_at": now(),
        "limitations": [
            "Integrity is not source-log completeness or optimal-item truth.",
            "Development validation with player overlap, not independent test.",
            "Future training must verify this handoff before and after execution.",
        ],
    }


def run(parent, cohort, baseline, output, *, expected=None):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite handoff output")
    report = verify(parent, cohort, baseline, expected=expected)
    check_unchanged(report["protected_sha256"])
    output.mkdir(parents=False, exist_ok=False)
    write_exclusive(output / "handoff.json", report)
    check_unchanged(report["protected_sha256"])
    write_exclusive(
        output / "complete.json",
        {
            "schema_version": SCHEMA,
            "sha256": {"handoff.json": file_hash(output / "handoff.json")},
            "training_executed": False,
        },
    )
    return report
