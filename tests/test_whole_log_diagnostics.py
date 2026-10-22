"""Synthetic diagnostic identities and negative input checks; never train."""

import copy
from pathlib import Path

import pytest

from dota_items.modeling.whole_log_diagnostics import contributions, diagnose, summarize


def cli():
    from dota_items.experiments.whole_log import diagnostics

    return diagnostics


def predictions():
    result = {}
    for family in ("frequency", "logistic"):
        result[family] = {}
        for split, start in (("train", 1), ("validation", 5)):
            result[family][split] = [
                {
                    "match_id": start + i,
                    "split": split,
                    "labels": {"item": i % 2},
                    "label_mask": {"item": True},
                    "probabilities": {
                        "item": 0.5 if family == "frequency" else (0.1 if i % 2 == 0 else 0.9)
                    },
                }
                for i in range(4)
            ]
    return result


@pytest.mark.parametrize(
    "y,p", [([0, 1], [0, 1]), ([0, 1], [0.5, 0.5]), ([1, 0, 1], [0.2, 0.9, 0.7])]
)
def test_exact_identity_and_bins(y, p):
    r = summarize(y, p)
    assert r["brier"] == pytest.approx(r["exact_brier_decomposition"]["reconstructed_brier"])
    assert sum(b["count"] for b in r["calibration_bins"]) == len(y)
    assert len(r["calibration_bins"]) == 10
    assert r["ece10"] >= 0


def test_perfect_and_probability_one():
    r = summarize([0, 1], [0, 1])
    assert r["brier"] == r["ece10"] == 0
    assert r["calibration_bins"][-1]["count"] == 1
    assert r["calibration_bins"][4]["mean_probability"] is None


def test_empty_unknown_and_pairing():
    assert summarize([], [])["brier"] is None
    p = predictions()
    for f in p:
        p[f]["validation"][0]["labels"]["item"] = None
        p[f]["validation"][0]["label_mask"]["item"] = False
    r = diagnose(p, ["item"])
    assert r["metrics_and_calibration"]["logistic"]["validation"]["item"]["unknown"] == 1
    assert r["training_executed"] is False
    assert r["calibrator_fitted"] is False


def test_constant_increment_top10():
    r = contributions(list(range(20)), [0] * 10 + [1] * 10, [0.5] * 20, [0.9] * 10 + [0.1] * 10)
    assert r["mean_delta"] == pytest.approx(r["exact_increment_vs_constant_frequency"])
    assert r["top10_share_of_positive_delta"] == pytest.approx(0.5)
    assert len(r["top10_positive"]) == 10


@pytest.mark.parametrize("kind", ["duplicate", "misalign", "mask", "label", "probability", "test"])
def test_reject_invalid_predictions(kind):
    p = predictions()
    row = p["logistic"]["validation"][0]
    if kind == "duplicate":
        row["match_id"] = 6
    elif kind == "misalign":
        row["match_id"] = 99
    elif kind == "mask":
        row["label_mask"]["item"] = False
    elif kind == "label":
        row["labels"]["item"] = 2
    elif kind == "probability":
        row["probabilities"]["item"] = -0.1
    else:
        p["logistic"]["test"] = []
    with pytest.raises(ValueError):
        diagnose(p, ["item"])


def test_diagnosis_does_not_mutate():
    p = predictions()
    original = copy.deepcopy(p)
    diagnose(p, ["item"])
    assert p == original


def test_output_refused_before_verification(tmp_path, monkeypatch):
    module = cli()
    monkeypatch.setattr(module, "verify", lambda *a: pytest.fail("verification invoked"))
    with pytest.raises(ValueError, match="overwrite"):
        module.run("absent", "absent", tmp_path)


def test_receipt_corruption_blocks_verification(tmp_path):
    module = cli()
    from dota_items.storage import json_bytes

    names = {"protocol.json", "report.json"} | {
        f"{f}.{suffix}.json"
        for f in ("frequency", "logistic")
        for suffix in ("model", "train.predictions", "validation.predictions")
    }
    for name in names | {"snapshot.json"}:
        (tmp_path / name).write_text("{}")
    (tmp_path / "complete.json").write_bytes(
        json_bytes(
            {
                "schema_version": "whole-log-experiment-complete/1",
                "training_executed": True,
                "sha256": {n: "a" * 64 for n in names},
            }
        )
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        module.verify(tmp_path, tmp_path / "snapshot.json")


def test_no_training_calls_in_diagnostic_sources():
    import ast

    root = Path(__file__).resolve().parents[1]
    for name in (
        "scripts/diagnose_whole_log_experiment.py",
        "src/dota_items/experiments/whole_log/diagnostics.py",
        "src/dota_items/modeling/whole_log_diagnostics.py",
    ):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                assert getattr(fn, "attr", getattr(fn, "id", "")) not in (
                    "fit",
                    "fit_model",
                    "fit_transform",
                )
