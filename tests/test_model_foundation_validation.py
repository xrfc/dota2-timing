"""Synthetic boundary failures and split isolation; never load real match payloads."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from dota_items.contracts.lineup import columns, encode_lineup
from dota_items.modeling.foundation import (
    adapt_snapshot,
    fit_model,
    load_model,
    predict_lineup,
    save_model,
    validate_model,
)
from dota_items.modeling.synthetic_foundation import synthetic_snapshot
from dota_items.storage import digest, file_hash


@pytest.fixture(scope="module")
def logistic():
    return fit_model(
        adapt_snapshot(synthetic_snapshot()),
        family="logistic",
        source_sha256="a" * 64,
        code_revision="synthetic-boundary-test",
    )


def replace(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), "unknown/1"),
        (("modeling_ready",), 1),
        (("synthetic",), "false"),
        (("task",), None),
        (("task", "window"), [False, 1800]),
        (("task", "window"), [0, 1800.0]),
        (("task", "window"), [0, 1799]),
        (("task", "actual_purchase_ground_truth"), 0),
        (("preprocessing", "vocabulary"), []),
        (("preprocessing", "fit_split"), "validation"),
        (("preprocessing", "vocabulary", 0), True),
        (("preprocessing", "columns", 0), "metadata_match_id"),
        (("splits", "train"), None),
        (("splits", "validation", 0), 1),
        (("splits", "test", 0), True),
        (("samples",), []),
        (("samples", 0, "match_id"), True),
        (("samples", 0, "match_id"), 1.0),
        (("samples", 0, "split"), "unknown"),
        (("samples", 0, "features"), {}),
        (("samples", 0, "features", "enemy_hero_ids", 0), float("nan")),
        (("samples", 0, "encoded_features"), []),
        (("samples", 0, "encoded_features", 0), 1.0),
        (("samples", 0, "encoded_features", 0), float("inf")),
        (("samples", 0, "labels"), None),
        (("samples", 0, "labels", 0), float("nan")),
        (("samples", 0, "labels", 0), 2),
        (("samples", 0, "label_mask"), []),
        (("samples", 0, "label_mask", 0), 0),
    ],
)
def test_malformed_snapshot_is_value_error(path, value):
    snapshot = synthetic_snapshot()
    replace(snapshot, path, value)
    with pytest.raises(ValueError):
        adapt_snapshot(snapshot)


def test_duplicate_or_missing_selected_rows_rejected():
    for damage in ("duplicate", "missing"):
        snapshot = synthetic_snapshot()
        if damage == "duplicate":
            snapshot["samples"].append(copy.deepcopy(snapshot["samples"][0]))
        else:
            snapshot["samples"].pop(0)
        with pytest.raises(ValueError):
            adapt_snapshot(snapshot)


@pytest.mark.parametrize("split", ["train", "validation"])
def test_other_split_payloads_are_opaque_and_cannot_expand_vocabulary(split):
    snapshot = synthetic_snapshot()
    expected = adapt_snapshot(snapshot, split)
    for index, row in enumerate(snapshot["samples"]):
        if row["split"] != split:
            # Would raise during encoding/serialization/fitting if accidentally inspected.
            snapshot["samples"][index] = {
                "split": row["split"],
                "features": {"enemy_hero_ids": [999999]},
                "encoded_features": object(),
                "labels": object(),
                "label_mask": object(),
            }
        else:
            row["account_id"] = object()
            row["purchase_log"] = object()
            row["role_hint"] = "metadata-only"
    actual = adapt_snapshot(snapshot, split)
    np.testing.assert_array_equal(actual.x, expected.x)
    np.testing.assert_array_equal(actual.y, expected.y)
    np.testing.assert_array_equal(actual.mask, expected.mask)
    assert actual.preprocessing == expected.preprocessing
    if split == "train":
        options = dict(source_sha256="a" * 64, code_revision="isolation")
        assert fit_model(actual, **options) == fit_model(expected, **options)


def test_held_out_heroes_stay_unknown_and_training_vocabulary_cannot_include_them():
    snapshot = synthetic_snapshot()
    held_out = snapshot["samples"][12]
    held_out["features"]["enemy_hero_ids"][0] = 999
    prep = snapshot["preprocessing"]
    held_out["encoded_features"] = encode_lineup(held_out["features"], prep["vocabulary"])
    train = adapt_snapshot(snapshot)
    validation = adapt_snapshot(snapshot, "validation")
    assert 999 not in train.preprocessing["vocabulary"]
    assert validation.x[0, -1] == 1
    prep["vocabulary"].append(999)
    prep["columns"] = columns(prep["vocabulary"])
    for row in snapshot["samples"]:
        row["encoded_features"] = encode_lineup(row["features"], prep["vocabulary"])
    with pytest.raises(ValueError, match="train"):
        adapt_snapshot(snapshot)


@pytest.mark.parametrize("damage", ["null_observed", "non_null_masked"])
def test_mask_null_contract(damage):
    snapshot = synthetic_snapshot()
    row = snapshot["samples"][0]
    if damage == "null_observed":
        row["labels"][0] = None
    else:
        row["label_mask"][0] = False
    with pytest.raises(ValueError):
        adapt_snapshot(snapshot)


@pytest.mark.parametrize(
    "damage",
    [
        "masked_zero",
        "masked_inf",
        "observed_nan",
        "feature_two",
        "feature_fraction",
        "unknown_negative",
        "unknown_six",
        "wrong_side_count",
        "x_object",
        "x_empty",
        "x_dimension",
        "y_bool",
        "mask_dimension",
        "synthetic_string",
    ],
)
def test_direct_batch_cannot_bypass_domains(damage):
    batch = adapt_snapshot(synthetic_snapshot())
    if damage.startswith("masked_"):
        batch.mask[0, 0] = False
        batch.y[0, 0] = 0 if damage == "masked_zero" else np.inf
    elif damage == "observed_nan":
        batch.y[0, 0] = np.nan
    elif damage == "feature_two":
        batch.x[0, 0] = 2
    elif damage == "feature_fraction":
        batch.x[0, 0] = 0.5
    elif damage == "unknown_negative":
        batch.x[0, -1] = -1
    elif damage == "unknown_six":
        batch.x[0, -1] = 6
    elif damage == "wrong_side_count":
        batch.x[0, 0] = 0
    elif damage == "x_object":
        batch.x = batch.x.astype(str)
    elif damage == "x_empty":
        batch.x, batch.y, batch.mask = batch.x[:0], batch.y[:0], batch.mask[:0]
    elif damage == "x_dimension":
        batch.x = batch.x[:, :-1]
    elif damage == "y_bool":
        batch.y = batch.y.astype(bool)
    elif damage == "mask_dimension":
        batch.mask = batch.mask[:, :-1]
    else:
        batch.synthetic = "false"
    with pytest.raises(ValueError):
        fit_model(batch, source_sha256="a" * 64, code_revision="synthetic")


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), "unknown/1"),
        (("synthetic",), 1),
        (
            ("task", "candidate_items"),
            list(reversed(["bfury", "maelstrom", "manta", "black_king_bar", "skadi"])),
        ),
        (("preprocessing", "columns", 0), "enemy_hero_1"),
        (("models", 0, "item"), "skadi"),
        (("parameters", "C"), True),
        (("parameters", "solver"), "saga"),
        (("parameters", "max_iter"), True),
        (("parameters", "random_state"), False),
        (("parameters", "class_weight"), "balanced"),
        (("models", 0, "coefficients", 0), "1.0"),
        (("models", 0, "coefficients", 0), True),
        (("models", 0, "coefficients", 0), float("nan")),
        (("models", 0, "coefficients", 0), float("inf")),
        (("models", 0, "coefficients"), []),
        (("models", 0, "intercept"), True),
        (("models", 0, "intercept"), "0"),
        (("models", 0, "intercept"), float("inf")),
        (("models", 0, "support", "observed"), True),
        (("models", 0, "support", "positive"), -1),
        (("models", 0, "support", "positive"), 13),
        (("models", 0, "support", "unknown"), 1),
        (("models", 0, "frequency"), 0.50000001),
        (("models", 3, "reason"), "no_observations"),
        (("models", 3, "frequency"), 0.5),
        (("provenance", "source_sha256"), 1),
        (("provenance", "code_revision"), True),
        (("meaning",), ""),
    ],
)
def test_checksum_valid_malformed_artifact_is_rejected(tmp_path, logistic, path, value):
    artifact = copy.deepcopy(logistic)
    replace(artifact, path, value)
    # Recompute envelope checksum: semantic checks must stand on their own.
    destination = tmp_path / "malformed.json"
    envelope = {"artifact": artifact, "sha256": "0" * 64}
    if "NaN" not in json.dumps(artifact) and "Infinity" not in json.dumps(artifact):
        envelope["sha256"] = digest(artifact)
    destination.write_text(json.dumps(envelope))
    with pytest.raises(ValueError):
        load_model(destination)


@pytest.mark.parametrize(
    "payload",
    [
        "null",
        "[]",
        "{}",
        '{"artifact":null,"sha256":null}',
        '{"artifact":{},"artifact":{},"sha256":"x"}',
        "{bad",
    ],
)
def test_malformed_envelope_fails_without_training(tmp_path, monkeypatch, payload):
    def forbidden(*args, **kwargs):
        raise AssertionError("load must never train")

    monkeypatch.setattr(LogisticRegression, "fit", forbidden)
    path = tmp_path / "invalid.json"
    path.write_text(payload)
    with pytest.raises(ValueError):
        load_model(path)


def test_fingerprint_covers_lineup_and_legacy_artifact_remains_loadable(tmp_path, logistic):
    provenance = logistic["provenance"]
    files = provenance["implementation_files_sha256"]
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/dota_items/modeling/foundation.py",
        "src/dota_items/contracts/lineup.py",
        "src/dota_items/modeling/specs.py",
        "src/dota_items/modeling/training.py",
        "src/dota_items/modeling/estimators/logistic.py",
        "src/dota_items/storage.py",
    ):
        assert files[relative] == file_hash(root / relative)
    assert provenance["implementation_bundle_sha256"] == digest(files)
    assert provenance["implementation_sha256"] == files["src/dota_items/modeling/foundation.py"]
    legacy = copy.deepcopy(logistic)
    del legacy["provenance"]["implementation_files_sha256"]
    del legacy["provenance"]["implementation_bundle_sha256"]
    path = tmp_path / "legacy.json"
    save_model(path, legacy)
    features = synthetic_snapshot()["samples"][0]["features"]
    assert predict_lineup(load_model(path), features) == predict_lineup(logistic, features)
    broken = copy.deepcopy(logistic)
    broken["provenance"]["implementation_files_sha256"]["src/dota_items/contracts/lineup.py"] = (
        "0" * 64
    )
    with pytest.raises(ValueError, match="fingerprint"):
        validate_model(broken)


@pytest.mark.parametrize("family", ["frequency", "logistic"])
def test_synthetic_train_save_load_independent_predict(tmp_path, family):
    model = tmp_path / f"{family}.json"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    demo = subprocess.run(
        [
            sys.executable,
            "scripts/model_foundation.py",
            "demo",
            "--family",
            family,
            "--output",
            str(model),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    expected = json.loads(demo.stdout)
    assert expected.pop("performance_evidence") is False
    lineup = tmp_path / "lineup.json"
    lineup.write_text(json.dumps(synthetic_snapshot()["samples"][0]["features"]))
    predict_command = [
        sys.executable,
        "scripts/model_foundation.py",
        "predict",
        "--model",
        str(model),
        "--lineup",
        str(lineup),
    ]
    result = subprocess.run(predict_command, capture_output=True, text=True, check=True, env=env)
    assert json.loads(result.stdout) == expected
    original = model.read_bytes()
    duplicate = subprocess.run(
        [
            sys.executable,
            "scripts/model_foundation.py",
            "demo",
            "--family",
            family,
            "--output",
            str(model),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert duplicate.returncode != 0
    assert model.read_bytes() == original
    # Failed inference cannot silently repair/retrain a malformed model.
    model.write_text("{}")
    failed = subprocess.run(predict_command, capture_output=True, text=True, env=env)
    assert failed.returncode != 0
    assert not failed.stdout
    assert model.read_text() == "{}"


def test_prediction_fails_on_finite_weights_that_overflow_score(logistic):
    artifact = copy.deepcopy(logistic)
    artifact["models"][0]["coefficients"] = [1e308] * len(artifact["preprocessing"]["columns"])
    with pytest.raises(ValueError, match="finite"):
        predict_lineup(artifact, synthetic_snapshot()["samples"][0]["features"])


@pytest.mark.parametrize("family", ["frequency", "logistic"])
@pytest.mark.parametrize("label", [0, 1, None])
def test_single_class_and_all_unknown_roundtrip_without_fit(tmp_path, monkeypatch, family, label):
    snapshot = synthetic_snapshot()
    for row in snapshot["samples"]:
        if row["split"] == "train":
            row["labels"] = [label] * 5
            row["label_mask"] = [label is not None] * 5

    def forbidden(*args, **kwargs):
        raise AssertionError("An unlearnable target must not be fitted")

    monkeypatch.setattr(LogisticRegression, "fit", forbidden)
    model = fit_model(
        adapt_snapshot(snapshot), family=family, source_sha256="a" * 64, code_revision="synthetic"
    )
    path = tmp_path / "untrained.json"
    save_model(path, model)
    result = predict_lineup(load_model(path), snapshot["samples"][0]["features"])
    assert all(value is None for value in result["probabilities"].values())
    assert all(
        entry["reason"] == ("no_observations" if label is None else "single_class")
        for entry in model["models"]
    )


@pytest.mark.parametrize("solver", ["liblinear", "lbfgs"])
@pytest.mark.parametrize("c", [0.01, 0.1, 1.0, 10.0])
def test_supported_explicit_logistic_parameters_roundtrip(tmp_path, solver, c):
    snapshot = synthetic_snapshot()
    batch = adapt_snapshot(snapshot)
    artifact = fit_model(
        batch,
        family="logistic",
        c=c,
        solver=solver,
        source_sha256="a" * 64,
        code_revision="synthetic",
    )
    path = tmp_path / "explicit.json"
    save_model(path, artifact)
    features = snapshot["samples"][0]["features"]
    expected = LogisticRegression(C=c, solver=solver, max_iter=2000, random_state=0)
    expected.fit(batch.x, batch.y[:, 0])
    assert predict_lineup(load_model(path), features)["probabilities"]["bfury"] == pytest.approx(
        expected.predict_proba(batch.x[:1])[0, 1],
        abs=1e-14,
    )


@pytest.mark.parametrize("remove", ["implementation_files_sha256", "implementation_bundle_sha256"])
def test_incomplete_fingerprint_is_not_legacy(logistic, remove):
    artifact = copy.deepcopy(logistic)
    del artifact["provenance"][remove]
    with pytest.raises(ValueError, match="fingerprint"):
        validate_model(artifact)


def test_missing_model_stays_missing(tmp_path):
    path = tmp_path / "does-not-exist.json"
    with pytest.raises(FileNotFoundError):
        load_model(path)
    assert not path.exists()


def test_invalid_model_is_not_published(tmp_path, logistic):
    artifact = copy.deepcopy(logistic)
    artifact["synthetic"] = "true"
    path = tmp_path / "not-published.json"
    with pytest.raises(ValueError):
        save_model(path, artifact)
    assert not path.exists()


def test_convergence_warning_is_failure_not_frequency_fallback(monkeypatch):
    from sklearn.exceptions import ConvergenceWarning

    def fail(*args, **kwargs):
        import warnings

        warnings.warn("synthetic nonconvergence", ConvergenceWarning, stacklevel=2)

    monkeypatch.setattr(LogisticRegression, "fit", fail)
    with pytest.raises(ConvergenceWarning):
        fit_model(
            adapt_snapshot(synthetic_snapshot()),
            family="logistic",
            source_sha256="a" * 64,
            code_revision="synthetic",
        )


def test_logistic_mask_excludes_unknown_rows_instead_of_filling_zero():
    snapshot = synthetic_snapshot()
    for index in (0, 1, 3):
        snapshot["samples"][index]["labels"][0] = None
        snapshot["samples"][index]["label_mask"][0] = False
    batch = adapt_snapshot(snapshot)
    artifact = fit_model(
        batch, family="logistic", source_sha256="a" * 64, code_revision="synthetic"
    )
    keep = batch.mask[:, 0]
    reference = LogisticRegression(C=1, solver="liblinear", max_iter=2000, random_state=0)
    reference.fit(batch.x[keep], batch.y[keep, 0])
    expected = reference.predict_proba(batch.x[:1])[0, 1]
    actual = predict_lineup(artifact, snapshot["samples"][0]["features"])
    assert actual["probabilities"]["bfury"] == pytest.approx(expected, abs=1e-14)
    assert artifact["models"][0]["support"] == {"observed": 9, "positive": 4, "unknown": 3}
