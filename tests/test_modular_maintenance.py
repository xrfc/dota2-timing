"""Synthetic-only checks for independently maintained module boundaries."""

import copy
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

from dota_items.modeling.artifacts import load_model, save_model, validate_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.modeling.estimators import get_estimator
from dota_items.modeling.inference import predict_lineup
from dota_items.modeling.provenance import IMPLEMENTATION_FILES, LEGACY_IMPLEMENTATION_FILES
from dota_items.modeling.specs import C_GRID, FEATURES, TASK, check_task
from dota_items.modeling.synthetic_foundation import synthetic_snapshot
from dota_items.modeling.training import fit_model
from dota_items.storage import digest

ROOT = Path(__file__).resolve().parents[1]


def fresh(code, blocked):
    guard = f"""
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p + '.') for p in {blocked!r}):
            raise AssertionError('Forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Block())
"""
    subprocess.run([sys.executable, "-c", guard + code], cwd=ROOT, check=True)


@pytest.mark.parametrize("family", ["frequency", "logistic"])
def test_prediction_without_training_dependencies(tmp_path, family):
    snapshot = synthetic_snapshot()
    artifact = fit_model(
        adapt_snapshot(snapshot), family=family, source_sha256="a" * 64, code_revision="synthetic"
    )
    path = tmp_path / "model.json"
    save_model(path, artifact)
    features = snapshot["samples"][0]["features"]
    expected = predict_lineup(artifact, features)
    fresh(
        f"""
from dota_items.modeling.foundation import load_model, predict_lineup
assert predict_lineup(load_model({str(path)!r}), {features!r}) == {expected!r}
""",
        ("sklearn", "dota_items.data", "dota_items.sources", "dota_items.workflow"),
    )


def test_bundle_reader_has_no_audit_or_model_dependency():
    fresh(
        "from dota_items.handoff.bundle import verify_bundle\n",
        ("numpy", "pydantic", "dota_items.data", "dota_items.modeling", "dota_items.sources"),
    )


def test_data_validation_does_not_import_workflow():
    fresh("from dota_items.data.validation import validate_match\n", ("dota_items.workflow",))


def test_replay_adapter_does_not_import_data():
    fresh("from dota_items.sources.gem_replay import canonicalize_match\n", ("dota_items.data",))


def test_contracts_are_stdlib_only():
    fresh(
        "from dota_items.contracts.replay_context import export_context\n",
        ("gem", "numpy", "pydantic", "dota_items.sources", "dota_items.data"),
    )


def test_compatibility_exports_are_same_functions():
    from dota_items.contracts import replay_context
    from dota_items.data import cohort_handoff, context, validation
    from dota_items.handoff import bundle
    from dota_items.modeling import artifacts, batch, foundation, inference
    from dota_items.workflow import validation as old_validation

    assert foundation.adapt_snapshot is batch.adapt_snapshot
    assert foundation.load_model is artifacts.load_model
    assert foundation.predict_lineup is inference.predict_lineup
    assert old_validation.validate_match is validation.validate_match
    assert context.export_context is replay_context.export_context
    assert cohort_handoff.verify_bundle is bundle.verify_bundle


def test_specs_are_fixed_and_reject_unapproved_tasks():
    assert TASK.target_hero_id == 8 and TASK.window == (0, 1800)
    assert FEATURES.encoding == "lineup-multihot/1"
    with pytest.raises(FrozenInstanceError):
        TASK.target_hero_id = 1
    task = copy.deepcopy(synthetic_snapshot()["task"])
    task["window"] = [0, 1200]
    with pytest.raises(ValueError):
        check_task(task)
    with pytest.raises(ValueError):
        get_estimator("mlp")
    from dota_items.modeling.purchase_baseline import C_GRID as old_grid

    assert C_GRID == old_grid


@pytest.mark.parametrize("family", ["frequency", "logistic"])
def test_estimators_share_parameter_interface(family):
    x = np.array([[0], [1], [2], [3]], dtype=float)
    y = np.array([0, 0, 1, 1], dtype=float)
    result = get_estimator(family).fit_parameters(x, y, c=1.0, solver="liblinear")
    assert result["frequency"] == 0.5
    assert set(result) == (
        {"frequency"} if family == "frequency" else {"frequency", "coefficients", "intercept"}
    )


def test_old_manifest_and_new_manifest_load_without_rewriting(tmp_path):
    artifact = fit_model(
        adapt_snapshot(synthetic_snapshot()), source_sha256="a" * 64, code_revision="synthetic"
    )
    assert set(artifact["provenance"]["implementation_files_sha256"]) == set(IMPLEMENTATION_FILES)
    old = copy.deepcopy(artifact)
    files = {name: "b" * 64 for name in LEGACY_IMPLEMENTATION_FILES}
    old["provenance"].update(
        implementation_sha256="b" * 64,
        implementation_files_sha256=files,
        implementation_bundle_sha256=digest(files),
    )
    path = tmp_path / "old.json"
    save_model(path, old)
    before = path.read_bytes()
    assert load_model(path) == old
    assert path.read_bytes() == before
    del files[LEGACY_IMPLEMENTATION_FILES[-1]]
    old["provenance"]["implementation_bundle_sha256"] = digest(files)
    with pytest.raises(ValueError, match="fingerprint"):
        validate_model(old)


def test_unknown_artifact_version_is_rejected():
    artifact = fit_model(
        adapt_snapshot(synthetic_snapshot()), source_sha256="a" * 64, code_revision="synthetic"
    )
    artifact["schema_version"] = "purchase-foundation-model/999"
    with pytest.raises(ValueError, match="Unsupported"):
        validate_model(artifact)


def test_evaluation_matches_frozen_experiment():
    from dota_items.modeling import evaluation
    from dota_items.modeling import purchase_baseline as legacy

    y = np.array([0, 1, 0, 1, 1, 0])
    p = np.array([0.2, 0.7, 0.4, 0.8, 0.6, 0.3])
    b = np.full(len(y), 0.5)
    groups = np.array([1, 1, 2, 2, 3, 3])
    assert evaluation.metrics(y, p) == legacy.metrics(y, p)
    assert evaluation.paired_intervals(y, b, p, groups, repeats=10) == (
        legacy.paired_intervals(y, b, p, groups, repeats=10)
    )
