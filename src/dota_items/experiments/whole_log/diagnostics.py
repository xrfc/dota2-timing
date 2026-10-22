"""Verify a frozen whole-log experiment, then diagnose without fitting anything."""

import json
import subprocess
from pathlib import Path

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS, WHOLE_LOG_TASK_ID
from dota_items.modeling.artifacts import load_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.modeling.whole_log_comparison import evaluate, rows_for
from dota_items.modeling.whole_log_diagnostics import (
    FAMILIES,
    METRICS,
    SPLITS,
    diagnose,
    difference,
)
from dota_items.storage import file_hash, now

from .io import assert_equal, check_unchanged, write_exclusive


def load(path):
    return json.loads(Path(path).read_bytes())


def unchanged(protected):
    check_unchanged(protected, message="Protected input changed")


def verify(experiment, snapshot_path):
    experiment, snapshot_path = Path(experiment), Path(snapshot_path)
    names = {"protocol.json", "report.json"} | {
        f"{family}.{suffix}.json"
        for family in FAMILIES
        for suffix in ("model", "train.predictions", "validation.predictions")
    }
    paths = [experiment / "complete.json", snapshot_path] + [experiment / n for n in names]
    protected = {str(p): file_hash(p) for p in paths}
    receipt = load(experiment / "complete.json")
    if (
        receipt.get("schema_version") != "whole-log-experiment-complete/1"
        or receipt.get("training_executed") is not True
        or set(receipt.get("sha256", {})) != names
    ):
        raise ValueError("Invalid experiment completion receipt")
    for name in names:
        if receipt["sha256"][name] != protected[str(experiment / name)]:
            raise ValueError(f"Experiment receipt hash mismatch: {name}")
    protocol, report = (load(experiment / name) for name in ("protocol.json", "report.json"))
    snapshot = load(snapshot_path)
    bound = [
        sha
        for name, sha in protocol["input_sha256"].items()
        if Path(name).resolve() == snapshot_path.resolve()
    ]
    if bound != [protected[str(snapshot_path)]]:
        raise ValueError("Protocol snapshot hash binding mismatch")
    if (
        protocol["schema_version"] != "whole-log-fixed-experiment/1"
        or protocol["families"] != list(FAMILIES)
        or protocol["candidate_items"] != list(WHOLE_LOG_ITEMS)
        or protocol["task_contract"]["task_id"] != WHOLE_LOG_TASK_ID
        or set(snapshot["splits"]) != {*SPLITS, "test"}
        or snapshot["splits"]["test"] != []
        or any(r["split"] not in SPLITS for r in snapshot["samples"])
    ):
        raise ValueError("Unexpected frozen protocol/split")
    ids = [r["match_id"] for r in snapshot["samples"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate snapshot IDs")
    for key, value in (
        ("task_contract", snapshot["task"]["contract"]),
        ("split_members", snapshot["splits"]),
        ("membership_sha256", snapshot["membership_sha256"]),
    ):
        assert_equal(protocol[key], value, key)
    for split in SPLITS:
        batch = adapt_snapshot(snapshot, split)
        assert_equal(protocol["consumer_shapes"][split], list(batch.x.shape), "shapes")
    assert_equal(report["protocol_sha256"], receipt["sha256"]["protocol.json"], "protocol sha")
    if report["training_executed"] is not True:
        raise ValueError("Incomplete original experiment")
    for key in ("input_sha256_before", "input_sha256_after"):
        assert_equal(report[key], protocol["input_sha256"], key)
    predictions, evaluated = {}, {}
    for family in FAMILIES:
        model = load_model(
            experiment / f"{family}.model.json",
            expected_preprocessing=snapshot["preprocessing"],
            expected_task_contract=snapshot["task"]["contract"],
        )
        if model["family"] != family or model["provenance"]["source_sha256"] != bound[0]:
            raise ValueError("Model source/family binding mismatch")
        predictions[family], evaluated[family] = {}, {}
        for split in SPLITS:
            rows = load(experiment / f"{family}.{split}.predictions.json")
            expected_rows = rows_for(model, snapshot, split)
            if len(rows) != len(expected_rows):
                raise ValueError("Prediction row count mismatch")
            for row, expected in zip(rows, expected_rows, strict=True):
                assert_equal(row, expected, "prediction/snapshot/model")
            predictions[family][split] = rows
            evaluated[family][split] = evaluate(rows)
    assert_equal(report["metrics"], evaluated, "report metrics")
    deltas = {}
    for split in SPLITS:
        a, b = (evaluated[f][split] for f in FAMILIES)
        deltas[split] = {
            "per_item": {
                i: {k: difference(a["per_item"][i][k], b["per_item"][i][k]) for k in METRICS}
                for i in WHOLE_LOG_ITEMS
            },
            "macro": {
                k: difference(a["macro"][k]["value"], b["macro"][k]["value"]) for k in METRICS
            },
        }
    assert_equal(report["logistic_minus_frequency"], deltas, "report deltas")
    unchanged(protected)
    return predictions, protected


def run(experiment, snapshot, output, *, command=None):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite output")
    # Match IDs must never accidentally land in tracked/public documentation.
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(output / "report.json")], check=False
    )
    if ignored.returncode != 0:
        raise ValueError("Output must be git-ignored (use reports/)")
    predictions, protected = verify(experiment, snapshot)
    implementation = {str(p): file_hash(p) for p in sorted(Path("src/dota_items").rglob("*.py"))}
    implementation[__file__] = file_hash(Path(__file__))
    cli_path = Path("scripts/diagnose_whole_log_experiment.py")
    implementation[str(cli_path)] = file_hash(cli_path)
    result = diagnose(predictions, WHOLE_LOG_ITEMS)
    unchanged(protected)
    unchanged(implementation)
    result.update(
        input_sha256_before=protected,
        input_sha256_after={p: file_hash(Path(p)) for p in protected},
        implementation_sha256=implementation,
        command=command,
    )
    output.mkdir(parents=False, exist_ok=False)
    write_exclusive(output / "report.json", result)
    unchanged(protected)
    unchanged(implementation)
    write_exclusive(
        output / "complete.json",
        {
            "schema_version": "whole-log-diagnostics-complete/1",
            "completed_at": now(),
            "sha256": {"report.json": file_hash(output / "report.json")},
            "training_executed": False,
            "calibrator_fitted": False,
            "input_sha256": protected,
        },
    )
    return result
