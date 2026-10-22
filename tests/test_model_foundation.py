import copy
import json
import subprocess
import sys

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from dota_items.modeling.foundation import (
    adapt_snapshot,
    check_lineup,
    fit_model,
    load_model,
    predict_lineup,
    save_model,
    validate_model,
)
from dota_items.modeling.synthetic_foundation import synthetic_snapshot


def fitted(snapshot=None, family="logistic"):
    return fit_model(
        adapt_snapshot(snapshot or synthetic_snapshot()),
        family=family,
        source_sha256="a" * 64,
        code_revision="synthetic-test",
    )


@pytest.mark.parametrize("family", ["frequency", "logistic"])
def test_roundtrip_and_no_retraining(tmp_path, monkeypatch, family):
    artifact = fitted(family=family)
    path = tmp_path / "model.json"
    features = synthetic_snapshot()["samples"][0]["features"]
    expected = predict_lineup(artifact, features)
    save_model(path, artifact)

    def forbidden(*args, **kwargs):
        raise AssertionError("load must not train")

    monkeypatch.setattr(LogisticRegression, "fit", forbidden)
    assert predict_lineup(load_model(path), features) == expected
    assert expected["probabilities"]["black_king_bar"] is None
    assert expected["untrained_items"] == ["black_king_bar"]
    assert expected["synthetic"] is True
    with pytest.raises(FileExistsError):
        save_model(path, artifact)


def test_permutation_unknown_and_dynamic_dimension():
    snapshot = synthetic_snapshot()
    artifact = fitted(snapshot)
    features = copy.deepcopy(snapshot["samples"][0]["features"])
    expected = predict_lineup(artifact, features)
    features["ally_hero_ids"].reverse()
    features["enemy_hero_ids"].reverse()
    assert predict_lineup(artifact, features) == expected
    features["enemy_hero_ids"][0] = 999
    assert predict_lineup(artifact, features)["unknown_counts"] == {"ally": 0, "enemy": 1}
    assert adapt_snapshot(snapshot).x.shape == (12, 24)


@pytest.mark.parametrize("damage", ["duplicate", "short", "bool", "target", "enemy_target"])
def test_bad_lineup(damage):
    features = synthetic_snapshot()["samples"][0]["features"]
    if damage == "duplicate":
        features["enemy_hero_ids"][0] = 1
    elif damage == "short":
        features["ally_hero_ids"].pop()
    elif damage == "bool":
        features["enemy_hero_ids"][0] = True
    elif damage == "target":
        features["target_hero_id"] = 1
    else:
        features["ally_hero_ids"][0], features["enemy_hero_ids"][0] = 10, 8
    with pytest.raises(ValueError):
        check_lineup(features)


def test_mask_and_no_observations():
    snapshot = synthetic_snapshot()
    for row in snapshot["samples"]:
        row["labels"][4], row["label_mask"][4] = None, False
    snapshot["samples"][0]["labels"][0] = None
    snapshot["samples"][0]["label_mask"][0] = False
    batch = adapt_snapshot(snapshot)
    assert np.isnan(batch.y[0, 0])
    artifact = fitted(snapshot, "frequency")
    assert artifact["models"][0]["frequency"] == 6 / 11
    assert artifact["models"][4]["reason"] == "no_observations"


def test_other_payloads_opaque_and_metadata_not_features():
    snapshot = synthetic_snapshot()
    expected = fitted(snapshot)
    for i, row in enumerate(snapshot["samples"]):
        if row["split"] != "train":
            snapshot["samples"][i] = {"split": row["split"], "labels": object()}
        else:
            row["role_hint"] = "changed"
            row["group_id"] = "changed"
            row["account_id"] = 123456
            row["purchase_log"] = object()
    assert fitted(snapshot) == expected


def test_fit_validation_and_test_adaptation_rejected():
    snapshot = synthetic_snapshot()
    with pytest.raises(ValueError, match="train only"):
        fit_model(adapt_snapshot(snapshot, "validation"), source_sha256="a" * 64, code_revision="x")
    with pytest.raises(ValueError, match="train/validation"):
        adapt_snapshot(snapshot, "test")


@pytest.mark.parametrize(
    "damage", ["columns", "encoded", "mask", "label", "order", "split", "vocab"]
)
def test_snapshot_mismatch_rejected(damage):
    snapshot = synthetic_snapshot()
    if damage == "columns":
        snapshot["preprocessing"]["columns"].reverse()
    elif damage == "encoded":
        snapshot["samples"][0]["encoded_features"][0] = 2
    elif damage == "mask":
        snapshot["samples"][0]["label_mask"][0] = 1
    elif damage == "label":
        snapshot["samples"][0]["labels"][0] = True
    elif damage == "order":
        snapshot["task"]["candidate_items"].reverse()
    elif damage == "split":
        snapshot["splits"]["validation"].append(1)
    else:
        snapshot["preprocessing"]["vocabulary"].append(999)
    with pytest.raises(ValueError):
        adapt_snapshot(snapshot)


def test_checksum_and_expected_feature_compatibility(tmp_path):
    artifact = fitted()
    path = tmp_path / "model.json"
    save_model(path, artifact)
    with pytest.raises(ValueError, match="compatibility"):
        load_model(path, expected_preprocessing={})
    envelope = json.loads(path.read_text())
    envelope["artifact"]["models"][0]["intercept"] += 1
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="checksum"):
        load_model(path)


def test_logistic_predictions_match_sklearn():
    snapshot = synthetic_snapshot()
    batch = adapt_snapshot(snapshot)
    artifact = fitted(snapshot)
    reference = LogisticRegression(C=1, solver="liblinear", max_iter=2000, random_state=0)
    reference.fit(batch.x, batch.y[:, 0])
    p = predict_lineup(artifact, snapshot["samples"][0]["features"])["probabilities"]["bfury"]
    assert p == pytest.approx(reference.predict_proba(batch.x[:1])[0, 1], abs=1e-14)


def test_cli_demo_and_predict(tmp_path):
    model = tmp_path / "model.json"
    command = [sys.executable, "scripts/model_foundation.py", "demo", "--output", str(model)]
    run = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(run.stdout)["synthetic"] is True
    assert subprocess.run(command, capture_output=True).returncode != 0
    lineup = tmp_path / "lineup.json"
    lineup.write_text(json.dumps(synthetic_snapshot()["samples"][0]["features"]))
    run = subprocess.run(
        [
            sys.executable,
            "scripts/model_foundation.py",
            "predict",
            "--model",
            str(model),
            "--lineup",
            str(lineup),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(run.stdout)["probabilities"]["bfury"] == 0.5


@pytest.mark.parametrize("damage", ["coefficient", "status", "parameters", "kind"])
def test_artifact_corruption_rejected(damage):
    artifact = fitted()
    if damage == "coefficient":
        artifact["models"][0]["coefficients"].pop()
    elif damage == "status":
        artifact["models"][3]["status"] = "trained"
    elif damage == "parameters":
        artifact["parameters"]["C"] = True
    else:
        del artifact["synthetic"]
    with pytest.raises((ValueError, KeyError)):
        validate_model(artifact)
