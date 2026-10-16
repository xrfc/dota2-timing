import copy

import pytest

from dota_items.modeling.purchase_sensitivity import compare


def fixture():
    return {
        "task": {"candidate_items": ["manta", "bkb"]},
        "samples": [
            {
                "match_id": f"{split}-{i}",
                "split": split,
                "encoded_features": [i % 2, i / 10],
                "labels": [i % 2, 0],
                "label_mask": [True, True],
            }
            for split in ["train", "validation"]
            for i in range(10)
        ],
    }


def test_test_payload_is_never_read():
    clean = fixture()
    poisoned = copy.deepcopy(clean)
    poisoned["samples"].append({"split": "test", "labels": object()})
    assert compare(clean) == compare(poisoned)


def test_frequency_can_win_and_unknown_labels_are_excluded():
    data = fixture()
    for r in data["samples"]:
        r["encoded_features"] = [0, 0]
    unknown = copy.deepcopy(data["samples"][0])
    unknown.update(labels=[None, None], label_mask=[False, False])
    expected = compare(data)
    data["samples"].append(unknown)
    assert compare(data) == expected
    result = expected["items"]["manta"]
    assert result["selected_index"] == 0
    assert len(result["trials"]) == 9
    assert expected["excluded_train_single_class_items"] == ["bkb"]


def test_validation_does_not_change_fitted_parameters():
    data = fixture()
    before = compare(data)["items"]["manta"]["trials"]
    for r in data["samples"]:
        if r["split"] == "validation":
            r["labels"][0] = 1 - r["labels"][0]
    after = compare(data)["items"]["manta"]["trials"]
    for a, b in zip(before, after, strict=True):
        for key in ["coefficients", "intercept", "validation_predictions"]:
            assert a[key] == b[key]


def test_missing_validation_fails():
    data = fixture()
    data["samples"] = [r for r in data["samples"] if r["split"] == "train"]
    with pytest.raises(ValueError, match="Validation"):
        compare(data)


def test_readonly_report_preserves_result_and_delta_direction():
    from dota_items.modeling.sensitivity_report import render_report

    result = compare(fixture())
    before = copy.deepcopy(result)
    report = render_report(result, source_sha256="a" * 64)
    assert result == before
    assert "a" * 64 in report
    assert "bkb" in report
    assert "不是单因素因果消融" in report
    trial = result["items"]["manta"]["trials"][1]
    baseline = result["items"]["manta"]["trials"][0]
    delta = trial["metrics"]["validation"]["brier"] - baseline["metrics"]["validation"]["brier"]
    assert f"{delta:+.4f}" in report
    result["test_evaluated"] = True
    with pytest.raises(ValueError, match="train/validation"):
        render_report(result, source_sha256="a" * 64)


@pytest.mark.parametrize(
    "damage",
    ["nan", "support", "bias", "selection", "baseline", "missing"],
)
def test_readonly_report_rejects_corrupted_evidence(damage):
    from dota_items.modeling.sensitivity_report import render_report

    result = compare(fixture())
    group = result["items"]["manta"]
    metric = group["trials"][1]["metrics"]["validation"]
    if damage == "nan":
        metric["brier"] = float("nan")
    elif damage == "support":
        metric["observed"] += 1
    elif damage == "bias":
        metric["mean_prediction_minus_observed"] = 0.9
    elif damage == "selection":
        group["selected_index"] = -1
    elif damage == "baseline":
        group["trials"][0]["name"] = "missing-frequency"
    else:
        del metric["positive_rate"]
    with pytest.raises(ValueError):
        render_report(result, source_sha256="a" * 64)


def test_report_cli_rejects_bad_input_without_creating_output(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "result.json"
    output = tmp_path / "report.md"
    source.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
    run = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/render_purchase_sensitivity.py"),
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0
    assert not output.exists()
