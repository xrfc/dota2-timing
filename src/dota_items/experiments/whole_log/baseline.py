"""Strict replay, then one fixed development comparison; never model selection."""

import platform
import subprocess
import time
import warnings
from importlib.metadata import version
from pathlib import Path

from sklearn.exceptions import ConvergenceWarning

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS, WHOLE_LOG_TASK_ID
from dota_items.modeling.artifacts import load_model, save_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.modeling.training import fit_model
from dota_items.modeling.whole_log_comparison import evaluate as evaluate_predictions
from dota_items.modeling.whole_log_comparison import rows_for
from dota_items.storage import digest, file_hash, now

from .inputs import load as load
from .inputs import verify_inputs
from .io import check_unchanged
from .io import write_exclusive as _write


def _unchanged(hashes):
    check_unchanged(hashes, message="Protected input or implementation changed")


FAMILIES = ("frequency", "logistic")
METRICS = ("brier", "average_precision", "roc_auc")
LIMITATIONS = [
    "Development comparison on reused validation; not independent generalization evidence.",
    "Source-log behavior, not optimal items, recommendation quality or win-rate benefit.",
    "Inherited at-least-30-minute cohort; player overlap is allowed.",
    "No tuning, threshold selection, bootstrap, independent test or model selection.",
    "Unknown labels are excluded, never converted to negatives.",
]


def implementation_identity():
    """Hash current source, including uncommitted/untracked implementation."""
    paths = sorted(Path("src/dota_items").rglob("*.py")) + [
        Path("scripts/run_whole_log_experiment.py"),
        Path("scripts/whole_log_experiment.py"),
        Path("scripts/prepare_whole_log_cohort.py"),
    ]
    hashes = {str(p): file_hash(p) for p in paths}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], text=True
    )
    return {
        "head": head,
        "dirty": bool(status),
        "status_porcelain": status,
        "implementation_sha256": hashes,
        "implementation_bundle_sha256": digest(hashes),
        "python": platform.python_version(),
        "dependencies": {p: version(p) for p in ("numpy", "scipy", "scikit-learn")},
    }


def _difference(a, b):
    return None if a is None or b is None else b - a


def fit_comparison(snapshot, output, *, source_sha256, code_revision):
    """Internal computation shared by synthetic tests; caller freezes protocol first."""
    train = adapt_snapshot(snapshot, "train")
    adapt_snapshot(snapshot, "validation")  # Validate both before any fit.
    results, timings = {}, {}
    for family in FAMILIES:
        start = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model = fit_model(
                train,
                family=family,
                c=1.0,
                solver="liblinear",
                source_sha256=source_sha256,
                code_revision=code_revision,
            )
        timings[family] = time.perf_counter() - start
        path = output / f"{family}.model.json"
        save_model(path, model)
        loaded = load_model(
            path,
            expected_preprocessing=snapshot["preprocessing"],
            expected_task_contract=snapshot["task"]["contract"],
        )
        if loaded != model:
            raise ValueError("Model roundtrip mismatch")
        results[family] = {}
        for split in ("train", "validation"):
            rows = rows_for(loaded, snapshot, split)
            _write(output / f"{family}.{split}.predictions.json", rows)
            results[family][split] = evaluate_predictions(rows)
    differences = {}
    for split in ("train", "validation"):
        a, b = results["frequency"][split], results["logistic"][split]
        differences[split] = {
            "per_item": {
                i: {k: _difference(a["per_item"][i][k], b["per_item"][i][k]) for k in METRICS}
                for i in WHOLE_LOG_ITEMS
            },
            "macro": {
                k: _difference(a["macro"][k]["value"], b["macro"][k]["value"]) for k in METRICS
            },
        }
    return {
        "metrics": results,
        "logistic_minus_frequency": differences,
        "fit_seconds": timings,
        "limitations": LIMITATIONS,
        "interpretation": "Lower Brier is better; higher AP/ROC-AUC is better. "
        "Descriptive development comparison only; no winner selected.",
    }


def run_experiment(parent, cohort, output, *, verify_only=False):
    start = time.perf_counter()
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite output")
    snapshot, sources, protected = verify_inputs(parent, cohort)
    if snapshot["task"]["contract"]["task_id"] != WHOLE_LOG_TASK_ID:
        raise ValueError("Unexpected task")
    shapes = {s: list(adapt_snapshot(snapshot, s).x.shape) for s in ("train", "validation")}
    if shapes != {"train": [1592, 256], "validation": [398, 256]}:
        raise ValueError("Unexpected approved consumer shapes")
    if verify_only:
        return {"verified": True, "training_executed": False, "consumer_shapes": shapes}
    identity = implementation_identity()
    protocol = {
        "schema_version": "whole-log-fixed-experiment/1",
        "frozen_at": now(),
        "task_contract": snapshot["task"]["contract"],
        "families": list(FAMILIES),
        "logistic_parameters": {
            "C": 1.0,
            "solver": "liblinear",
            "max_iter": 2000,
            "random_state": 0,
            "class_weight": None,
        },
        "frequency": "Observed train positives / observed train labels, per item",
        "split_members": snapshot["splits"],
        "membership_sha256": snapshot["membership_sha256"],
        "consumer_shapes": shapes,
        "candidate_items": list(WHOLE_LOG_ITEMS),
        "input_sha256": protected,
        "sources": sources,
        "identity": identity,
        "primary_metric": "brier",
        "secondary_metrics": ["average_precision", "roc_auc"],
        "metrics": list(METRICS),
        "macro": "Unweighted mean over defined item metrics",
        "limitations": LIMITATIONS,
        "convergence_warning": "fatal",
        "missing_or_single_class_train": "untrained artifact; null probabilities, not negatives",
    }
    _unchanged(protected)
    output.mkdir(parents=False, exist_ok=False)
    _write(output / "protocol.json", protocol)
    frozen_protocol_sha = file_hash(output / "protocol.json")
    report = fit_comparison(
        snapshot,
        output,
        source_sha256=protected[str(Path(cohort) / "snapshot.json")],
        code_revision=identity["head"] + ("+dirty" if identity["dirty"] else ""),
    )
    _unchanged(protected)
    _unchanged(identity["implementation_sha256"])
    _unchanged({str(output / "protocol.json"): frozen_protocol_sha})
    report.update(
        {
            "protocol_sha256": frozen_protocol_sha,
            "training_executed": True,
            "input_sha256_before": protected,
            "input_sha256_after": {p: file_hash(Path(p)) for p in protected},
            "total_seconds": time.perf_counter() - start,
        }
    )
    _write(output / "report.json", report)
    hashes = {p.name: file_hash(p) for p in sorted(output.iterdir())}
    _unchanged(protected)
    _write(
        output / "complete.json",
        {
            "schema_version": "whole-log-experiment-complete/1",
            "sha256": hashes,
            "training_executed": True,
            "completed_at": now(),
            "total_seconds": time.perf_counter() - start,
        },
    )
    return report
