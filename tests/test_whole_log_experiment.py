"""Only fabricated rows; production source gates remain closed to arbitrary cohorts."""

import copy
import runpy
import subprocess
import sys
import warnings
from types import SimpleNamespace

import pytest
from sklearn.exceptions import ConvergenceWarning
from test_whole_log_snapshot import fixture

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS
from dota_items.data.whole_log_snapshot import relabel_snapshot
from dota_items.experiments.whole_log import baseline as experiment
from dota_items.experiments.whole_log import inputs
from dota_items.modeling.artifacts import load_model
from dota_items.modeling.inference import predict_lineup
from dota_items.storage import digest, file_hash, json_bytes


def snapshot():
    result = relabel_snapshot(*fixture())
    for row in result["samples"]:
        row["labels"] = [(row["match_id"] + j) % 2 for j in range(11)]
    return result


def fit(result, output):
    output.mkdir()
    return experiment.fit_comparison(
        result, output, source_sha256="a" * 64, code_revision="synthetic"
    )


def test_train_only_fixed_parameters_predictions_and_roundtrip(tmp_path):
    original = snapshot()
    report = fit(original, tmp_path / "a")
    changed = copy.deepcopy(original)
    for row in changed["samples"]:
        if row["split"] == "validation":
            row["labels"] = [1 - v for v in row["labels"]]
    fit(changed, tmp_path / "b")
    train = [r for r in original["samples"] if r["split"] == "train"]
    for family in experiment.FAMILIES:
        a = load_model(tmp_path / "a" / f"{family}.model.json")
        b = load_model(tmp_path / "b" / f"{family}.model.json")
        assert a == b
        assert a["parameters"] == {
            "C": 1.0 if family == "logistic" else None,
            "solver": "liblinear" if family == "logistic" else None,
            "max_iter": 2000,
            "random_state": 0,
            "class_weight": None,
        }
        for j, model in enumerate(a["models"]):
            assert model["frequency"] == sum(r["labels"][j] for r in train) / len(train)
        for split in ("train", "validation"):
            rows = experiment.load(tmp_path / "a" / f"{family}.{split}.predictions.json")
            assert report["metrics"][family][split] == experiment.evaluate_predictions(rows)
            selected = [r for r in original["samples"] if r["split"] == split]
            assert [r["match_id"] for r in rows] == [r["match_id"] for r in selected]
            for row, source in zip(rows, selected, strict=True):
                assert (
                    row["probabilities"] == predict_lineup(a, source["features"])["probabilities"]
                )
            for metric in experiment.METRICS:
                values = report["metrics"][family][split]
                assert values["macro"][metric]["value"] == pytest.approx(
                    sum(m[metric] for m in values["per_item"].values()) / 11
                )
    for split in ("train", "validation"):
        for item in WHOLE_LOG_ITEMS:
            for key in experiment.METRICS:
                assert report["logistic_minus_frequency"][split]["per_item"][item][key] == (
                    report["metrics"]["logistic"][split]["per_item"][item][key]
                    - report["metrics"]["frequency"][split]["per_item"][item][key]
                )


def test_missing_labels_are_not_negatives(tmp_path):
    result = snapshot()
    for row in result["samples"]:
        row["labels"][1] = None
        row["label_mask"][1] = False
        if row["match_id"] % 3 == 0:
            row["labels"][0] = None
            row["label_mask"][0] = False
    report = fit(result, tmp_path / "masked")
    train = [r for r in result["samples"] if r["split"] == "train" and r["label_mask"][0]]
    for family in experiment.FAMILIES:
        model = load_model(tmp_path / "masked" / f"{family}.model.json")
        assert model["models"][0]["frequency"] == sum(r["labels"][0] for r in train) / len(train)
        assert model["models"][1]["reason"] == "no_observations"
        for split in ("train", "validation"):
            item = report["metrics"][family][split]["per_item"]["maelstrom"]
            assert item["observed"] == 0 and item["brier"] is None
            assert item["unknown"] > 0


@pytest.mark.parametrize("kind", ["directory", "file", "dangling"])
def test_output_refused_before_input_read(tmp_path, monkeypatch, kind):
    output = tmp_path / "output"
    if kind == "directory":
        output.mkdir()
    elif kind == "file":
        output.write_text("keep")
    else:
        output.symlink_to(tmp_path / "absent")
    monkeypatch.setattr(experiment, "verify_inputs", lambda *a: pytest.fail("read input"))
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        experiment.run_experiment("missing", "missing", output)


def test_failed_verification_never_fits_or_creates_output(tmp_path, monkeypatch):
    def reject(*args):
        raise ValueError("replay mismatch")

    monkeypatch.setattr(experiment, "verify_inputs", reject)
    monkeypatch.setattr(experiment, "fit_model", lambda *a, **k: pytest.fail("fit"))
    with pytest.raises(ValueError, match="replay mismatch"):
        experiment.run_experiment("parent", "cohort", tmp_path / "output")
    assert not (tmp_path / "output").exists()


def prepared(tmp_path, monkeypatch):
    result = snapshot()
    protected_path = tmp_path / "protected.json"
    protected_path.write_bytes(json_bytes(result))
    protected = {str(protected_path): file_hash(protected_path)}
    monkeypatch.setattr(
        inputs, "build_whole_log_bundle", lambda parent: (result, [], dict(protected))
    )
    # Run the existing frozen preparation CLI against the synthetic producer.
    import dota_items.data.whole_log_snapshot as producer

    monkeypatch.setattr(producer, "build_whole_log_bundle", inputs.build_whole_log_bundle)
    cohort = tmp_path / "cohort"
    monkeypatch.setattr(sys, "argv", ["prepare", "--parent", "parent", "--output", str(cohort)])
    runpy.run_path("scripts/prepare_whole_log_cohort.py", run_name="__main__")
    return result, cohort


def test_full_replay_and_each_cohort_payload_tamper(tmp_path, monkeypatch):
    result, cohort = prepared(tmp_path, monkeypatch)
    replayed, _, _ = experiment.verify_inputs("parent", cohort)
    assert replayed == result
    receipt = experiment.load(cohort / "complete.json")
    for name in receipt["sha256"]:
        path = cohort / name
        original = path.read_bytes()
        path.write_bytes(b"{}")
        # Even a renewed self-reported hash cannot bypass source replay.
        altered = copy.deepcopy(receipt)
        altered["sha256"][name] = file_hash(path)
        (cohort / "complete.json").write_bytes(json_bytes(altered))
        with pytest.raises(ValueError, match="replay or hash mismatch"):
            experiment.verify_inputs("parent", cohort)
        path.write_bytes(original)
    (cohort / "complete.json").write_bytes(json_bytes(receipt))
    assert experiment.verify_inputs("parent", cohort)[0] == result


def production_gate_mock(monkeypatch):
    real_adapt = experiment.adapt_snapshot
    real_verify = experiment.verify_inputs

    def verify(parent, cohort):
        monkeypatch.setattr(experiment, "adapt_snapshot", real_adapt)
        try:
            return real_verify(parent, cohort)
        finally:
            monkeypatch.setattr(experiment, "adapt_snapshot", adapt)

    monkeypatch.setattr(experiment, "verify_inputs", verify)

    def adapt(value, split):
        real_adapt(value, split)
        return SimpleNamespace(x=SimpleNamespace(shape=(1592 if split == "train" else 398, 256)))

    monkeypatch.setattr(experiment, "adapt_snapshot", adapt)
    return real_adapt


def test_protocol_before_fit_receipt_last_and_verify_only(tmp_path, monkeypatch):
    result, cohort = prepared(tmp_path, monkeypatch)
    real_adapt = production_gate_mock(monkeypatch)
    output = tmp_path / "output"
    monkeypatch.setattr(experiment, "fit_model", lambda *a, **k: pytest.fail("fit"))
    assert experiment.run_experiment("parent", cohort, output, verify_only=True)["verified"]
    assert not output.exists()
    from dota_items.modeling.training import fit_model

    monkeypatch.setattr(experiment, "fit_model", fit_model)
    original = experiment.fit_comparison

    def fit_checked(value, directory, **kwargs):
        assert (directory / "protocol.json").exists()
        assert not (directory / "complete.json").exists()
        monkeypatch.setattr(experiment, "adapt_snapshot", real_adapt)
        return original(value, directory, **kwargs)

    monkeypatch.setattr(experiment, "fit_comparison", fit_checked)
    report = experiment.run_experiment("parent", cohort, output)
    receipt = experiment.load(output / "complete.json")
    assert len(receipt["sha256"]) == 8
    assert report["input_sha256_before"] == report["input_sha256_after"]
    for name, sha in receipt["sha256"].items():
        assert file_hash(output / name) == sha
    protocol = experiment.load(output / "protocol.json")
    assert protocol["identity"]["implementation_bundle_sha256"] == digest(
        protocol["identity"]["implementation_sha256"]
    )


def test_convergence_failure_never_completes(tmp_path, monkeypatch):
    _, cohort = prepared(tmp_path, monkeypatch)
    real_adapt = production_gate_mock(monkeypatch)
    original = experiment.fit_comparison

    def comparison(*args, **kwargs):
        monkeypatch.setattr(experiment, "adapt_snapshot", real_adapt)
        return original(*args, **kwargs)

    def failing_fit(*args, **kwargs):
        warnings.warn("synthetic convergence failure", ConvergenceWarning, stacklevel=2)

    monkeypatch.setattr(experiment, "fit_comparison", comparison)
    monkeypatch.setattr(experiment, "fit_model", failing_fit)
    output = tmp_path / "failed"
    with pytest.raises(ConvergenceWarning):
        experiment.run_experiment("parent", cohort, output)
    assert (output / "protocol.json").exists()
    assert not (output / "complete.json").exists()


def test_cli_rejects_output_before_missing_sources(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_whole_log_experiment.py",
            "--parent",
            "absent",
            "--cohort",
            "absent",
            "--output",
            str(tmp_path),
            "--verify-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "Refusing to overwrite" in result.stderr


def test_input_drift_after_fit_blocks_completion(tmp_path, monkeypatch):
    _, cohort = prepared(tmp_path, monkeypatch)
    real_adapt = production_gate_mock(monkeypatch)
    original = experiment.fit_comparison

    def drifting_fit(*args, **kwargs):
        monkeypatch.setattr(experiment, "adapt_snapshot", real_adapt)
        report = original(*args, **kwargs)
        (tmp_path / "protected.json").write_text("changed")
        return report

    monkeypatch.setattr(experiment, "fit_comparison", drifting_fit)
    output = tmp_path / "drift"
    with pytest.raises(ValueError, match="Protected input"):
        experiment.run_experiment("parent", cohort, output)
    assert not (output / "complete.json").exists()


def test_invalid_validation_mask_fails_before_fit(tmp_path, monkeypatch):
    result = snapshot()
    row = next(r for r in result["samples"] if r["split"] == "validation")
    row["label_mask"][0] = False
    monkeypatch.setattr(experiment, "fit_model", lambda *a, **k: pytest.fail("fit"))
    with pytest.raises(ValueError, match="Unknown labels"):
        fit(result, tmp_path / "invalid")
    assert not list((tmp_path / "invalid").iterdir())
