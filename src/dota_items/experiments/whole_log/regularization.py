"""Fixed two-C development protocol; frozen inputs and old baselines stay read-only."""

import time
import warnings
from pathlib import Path

from dota_items.modeling.artifacts import load_model, save_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.modeling.whole_log_comparison import compare as compare_models
from dota_items.modeling.whole_log_comparison import evaluate as evaluate
from dota_items.modeling.whole_log_comparison import rows_for
from dota_items.modeling.whole_log_diagnostics import SPLITS
from dota_items.storage import digest, file_hash, now
from dota_items.storage import json_bytes as json_bytes

from .diagnostics import verify as verify_baseline
from .handoff import (
    input_identity,
    read_handoff,
)
from .handoff import (
    verify as verify_handoff,
)
from .io import assert_equal, check_unchanged, load
from .io import write_exclusive as write

CANDIDATES = {"logistic_c0_1": 0.1, "logistic_c0_01": 0.01}
SCHEMA = "whole-log-regularization/1"
RULES = {
    "candidates": CANDIDATES,
    "primary_metric": "validation.macro.brier",
    "penalty": "l2",
    "solver": "liblinear",
    "max_iter": 2000,
    "random_state": 0,
    "class_weight": None,
    "fit_intercept": True,
    "intercept_scaling": 1,
    "calibration_bins": "10 equal-width bins",
    "selection": False,
    "calibrator_fitted": False,
    "stop": "two candidates only; convergence warnings fatal; no expanded search",
    "meaning": "Reused development validation; behavior not optimal equipment",
}


def parameters(c):
    return {
        "C": c,
        "solver": "liblinear" if c is not None else None,
        "max_iter": 2000,
        "random_state": 0,
        "class_weight": None,
    }


def new_output(output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite output")
    return output


def prepare(parent, cohort, baseline, handoff):
    """Full source replay plus existing baseline replay, never a fit."""
    verified = verify_handoff(parent, cohort, baseline, expected=handoff)
    snapshot_path = Path(cohort) / "snapshot.json"
    snapshot = load(snapshot_path)
    assert_equal(input_identity(snapshot), verified["identity"], "handoff identity")
    protected = dict(verified["protected_sha256"])
    for name in ("complete.json", "handoff.json"):
        path = (Path(handoff) / name).resolve()
        protected[str(path)] = file_hash(path)
    check_unchanged(protected)
    return snapshot, protected, verified["identity_sha256"]


def model_check(model, snapshot, c, source_sha):
    if (
        model["parameters"] != parameters(c)
        or model["family"] != ("frequency" if c is None else "logistic")
        or model["provenance"]["source_sha256"] != source_sha
    ):
        raise ValueError("Candidate parameters/source mismatch")
    train = adapt_snapshot(snapshot, "train")
    for j, entry in enumerate(model["models"]):
        known = train.mask[:, j]
        labels = train.y[known, j]
        expected = {
            "observed": len(labels),
            "positive": int(labels.sum()),
            "unknown": int((~known).sum()),
        }
        assert_equal(entry["support"], expected, "train support")


def compare(snapshot, models):
    return compare_models(snapshot, models, candidates=CANDIDATES, rules=RULES)


def fit_candidates(snapshot, output, source_sha, code_revision, guard):
    """Internal synthetic-test seam; production caller freezes protocol before entering."""
    from sklearn.exceptions import ConvergenceWarning

    from dota_items.modeling.training import fit_model

    train = adapt_snapshot(snapshot, "train")
    adapt_snapshot(snapshot, "validation")
    models, timings = {}, {}
    for name, c in CANDIDATES.items():
        guard()
        start = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model = fit_model(
                train,
                family="logistic",
                c=c,
                solver="liblinear",
                source_sha256=source_sha,
                code_revision=code_revision,
            )
        timings[name] = time.perf_counter() - start
        model_check(model, snapshot, c, source_sha)
        save_model(output / f"{name}.model.json", model)
        models[name] = load_model(
            output / f"{name}.model.json",
            expected_preprocessing=snapshot["preprocessing"],
            expected_task_contract=snapshot["task"]["contract"],
        )
        assert_equal(models[name], model, "model roundtrip")
        for split in SPLITS:
            write(output / f"{name}.{split}.predictions.json", rows_for(model, snapshot, split))
    guard()
    return models, timings


def baseline_models(baseline, snapshot, source_sha):
    models = {}
    for name, c in (("frequency", None), ("logistic", 1.0)):
        model = load_model(
            Path(baseline) / f"{name}.model.json",
            expected_preprocessing=snapshot["preprocessing"],
            expected_task_contract=snapshot["task"]["contract"],
        )
        model_check(model, snapshot, c, source_sha)
        models[name] = model
    return models


def run(parent, cohort, baseline, handoff, output, *, execute=False):
    output = new_output(output)
    snapshot, protected, identity_sha = prepare(parent, cohort, baseline, handoff)
    if not execute:
        return {
            "verified": True,
            "training_executed": False,
            "rules": RULES,
            "identity_sha256": identity_sha,
        }
    from .baseline import implementation_identity

    implementation = implementation_identity()
    for name in (
        "whole_log_regularization",
        "run_whole_log_regularization",
        "report_whole_log_regularization",
        "verify_whole_log_handoff",
        "diagnose_whole_log_experiment",
    ):
        p = Path("scripts") / f"{name}.py"
        implementation["implementation_sha256"][str(p.resolve())] = file_hash(p)
    implementation["implementation_bundle_sha256"] = digest(implementation["implementation_sha256"])
    source_sha = file_hash(Path(cohort) / "snapshot.json")
    models = baseline_models(baseline, snapshot, source_sha)
    protocol = {
        "schema_version": SCHEMA,
        "rules": RULES,
        "frozen_at": now(),
        "identity_sha256": identity_sha,
        "input_sha256": protected,
        "handoff": str(Path(handoff).resolve()),
        "snapshot_sha256": source_sha,
        "implementation": implementation,
    }
    output.mkdir(parents=False)
    write(output / "protocol.json", protocol)
    protocol_sha = file_hash(output / "protocol.json")

    def guard():
        check_unchanged(protected)
        if read_handoff(handoff)["identity_sha256"] != identity_sha:
            raise ValueError("Handoff identity changed")
        check_unchanged(implementation["implementation_sha256"])
        check_unchanged({str(output / "protocol.json"): protocol_sha})

    start = time.perf_counter()
    candidates, timings = fit_candidates(
        snapshot,
        output,
        source_sha,
        implementation["head"] + ("+dirty" if implementation.get("dirty") else ""),
        guard,
    )
    models.update(candidates)
    report = compare(snapshot, models)
    report.update(
        protocol_sha256=protocol_sha,
        training_executed=True,
        fit_seconds=timings,
        total_seconds=time.perf_counter() - start,
        input_sha256_before=protected,
        input_sha256_after=protected,
    )
    write(output / "report.json", report)
    # Re-read published payloads before completion, not just the in-memory report.
    for name in CANDIDATES:
        assert_equal(load_model(output / f"{name}.model.json"), models[name], "published model")
        for split in SPLITS:
            assert_equal(
                load(output / f"{name}.{split}.predictions.json"),
                rows_for(models[name], snapshot, split),
                "published predictions",
            )
    assert_equal(load(output / "report.json"), report, "published report")
    guard()
    write(
        output / "complete.json",
        {
            "schema_version": SCHEMA,
            "training_executed": True,
            "sha256": {p.name: file_hash(p) for p in sorted(output.iterdir())},
        },
    )
    return report


def verify_result(parent, cohort, baseline, handoff, experiment):
    snapshot, protected, identity_sha = prepare(parent, cohort, baseline, handoff)
    experiment = Path(experiment)
    names = {"protocol.json", "report.json"} | {
        f"{n}.{s}.json"
        for n in CANDIDATES
        for s in ("model", "train.predictions", "validation.predictions")
    }
    receipt = load(experiment / "complete.json")
    if (
        receipt.get("schema_version") != SCHEMA
        or receipt.get("training_executed") is not True
        or set(receipt.get("sha256", {})) != names
    ):
        raise ValueError("Invalid regularization receipt")
    files = {str(experiment / n): sha for n, sha in receipt["sha256"].items()}
    files[str(experiment / "complete.json")] = file_hash(experiment / "complete.json")
    check_unchanged(files)
    protocol = load(experiment / "protocol.json")
    source_sha = file_hash(Path(cohort) / "snapshot.json")
    for key, expected in (
        ("schema_version", SCHEMA),
        ("rules", RULES),
        ("identity_sha256", identity_sha),
        ("input_sha256", protected),
        ("snapshot_sha256", source_sha),
        ("handoff", str(Path(handoff).resolve())),
    ):
        assert_equal(protocol[key], expected, key)
    implementation = protocol["implementation"]
    if implementation["implementation_bundle_sha256"] != digest(
        implementation["implementation_sha256"]
    ):
        raise ValueError("Implementation identity mismatch")
    # Recompute historical baseline predictions; never retrain it.
    verify_baseline(baseline, Path(cohort) / "snapshot.json")
    models = baseline_models(baseline, snapshot, source_sha)
    for name, c in CANDIDATES.items():
        model = load_model(
            experiment / f"{name}.model.json",
            expected_preprocessing=snapshot["preprocessing"],
            expected_task_contract=snapshot["task"]["contract"],
        )
        model_check(model, snapshot, c, source_sha)
        for split in SPLITS:
            assert_equal(
                load(experiment / f"{name}.{split}.predictions.json"),
                rows_for(model, snapshot, split),
                "candidate predictions",
            )
        models[name] = model
    recomputed = compare(snapshot, models)
    report = load(experiment / "report.json")
    for key, expected in {
        **recomputed,
        "training_executed": True,
        "protocol_sha256": file_hash(experiment / "protocol.json"),
        "input_sha256_before": protected,
        "input_sha256_after": protected,
    }.items():
        assert_equal(report[key], expected, "report/" + key)
    check_unchanged(protected)
    check_unchanged(files)
    return recomputed, {**protected, **files}


def report_run(parent, cohort, baseline, handoff, experiment, output):
    output = new_output(output)
    result, protected = verify_result(parent, cohort, baseline, handoff, experiment)
    output.mkdir(parents=False)
    write(output / "report.json", result)
    check_unchanged(protected)
    write(
        output / "complete.json",
        {
            "schema_version": "whole-log-regularization-diagnostics/1",
            "training_executed": False,
            "calibrator_fitted": False,
            "sha256": {"report.json": file_hash(output / "report.json")},
            "input_sha256": protected,
        },
    )
    return result
