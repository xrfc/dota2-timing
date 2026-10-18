"""Inspection reads only synthetic artifacts; never real data or model evaluation."""

import copy
import json
import os
import subprocess
import sys

import pytest

from dota_items.modeling.artifacts import save_model
from dota_items.modeling.foundation import adapt_snapshot, fit_model
from dota_items.modeling.inspection import inspect_model
from dota_items.modeling.provenance import IMPLEMENTATION_FILES, LEGACY_IMPLEMENTATION_FILES
from dota_items.modeling.synthetic_foundation import synthetic_snapshot
from dota_items.storage import digest


@pytest.fixture(params=["frequency", "logistic"])
def artifact(request):
    snapshot = synthetic_snapshot()
    for row in snapshot["samples"]:
        row["labels"][4], row["label_mask"][4] = None, False
    snapshot["samples"][0]["labels"][0] = None
    snapshot["samples"][0]["label_mask"][0] = False
    return fit_model(
        adapt_snapshot(snapshot),
        family=request.param,
        source_sha256="a" * 64,
        code_revision="synthetic-inspection-test",
    )


def cli(path):
    return subprocess.run(
        [sys.executable, "scripts/model_foundation.py", "inspect", "--model", str(path)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_summary_and_cli_preserve_bytes(tmp_path, artifact):
    path = tmp_path / "model.json"
    # Allowed extra metadata must not leak samples into the summary.
    artifact["task"]["samples"] = ["private-row"]
    artifact["preprocessing"]["samples"] = ["private-row"]
    save_model(path, artifact)
    before = path.read_bytes()
    summary = inspect_model(path)
    assert summary["schema_version"] == artifact["schema_version"]
    assert summary["family"] == artifact["family"]
    assert summary["synthetic"] is True
    assert summary["preprocessing"] == {
        "vocabulary_size": 11,
        "feature_dimension": 24,
        "fit_split": "train",
    }
    assert summary["targets"][0] == {
        "item": "bfury",
        "status": "trained",
        "reason": None,
        "support": {"positive": 6, "negative": 5, "observed": 11, "unknown": 1, "total": 12},
    }
    assert summary["targets"][3]["reason"] == "single_class"
    assert summary["targets"][3]["support"]["negative"] == 12
    assert summary["targets"][4]["reason"] == "no_observations"
    assert summary["targets"][4]["support"] == {
        "positive": 0,
        "negative": 0,
        "observed": 0,
        "unknown": 12,
        "total": 12,
    }
    assert summary["parameters"] == artifact["parameters"]
    for key in ("source_sha256", "code_revision", "python", "dependencies"):
        assert summary["provenance"][key] == artifact["provenance"][key]
    assert summary["task"]["actual_purchase_ground_truth"] is False
    encoded = json.dumps(summary)
    assert all(word not in encoded for word in ("coefficients", "intercept", "private-row"))
    result = cli(path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == summary
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "coverage", ["legacy_no_bundle", "historical_four_files", "modular_manifest"]
)
def test_recorded_fingerprint_coverage_not_current_verification(tmp_path, artifact, coverage):
    provenance = artifact["provenance"]
    # Deliberately unlike current source: consistent historic records still load.
    provenance["implementation_sha256"] = "b" * 64
    if coverage == "legacy_no_bundle":
        del provenance["implementation_files_sha256"]
        del provenance["implementation_bundle_sha256"]
        count = 1
    else:
        names = (
            LEGACY_IMPLEMENTATION_FILES
            if coverage == "historical_four_files"
            else IMPLEMENTATION_FILES
        )
        files = dict.fromkeys(names, "b" * 64)
        provenance["implementation_files_sha256"] = files
        provenance["implementation_bundle_sha256"] = digest(files)
        count = len(files)
    path = tmp_path / "historical.json"
    save_model(path, artifact)
    before = path.read_bytes()
    implementation = inspect_model(path)["provenance"]["implementation"]
    assert implementation["coverage"] == coverage
    assert implementation["recorded_file_count"] == count
    assert implementation["current_source_verified"] is False
    assert implementation["recorded_files_sha256"] == provenance.get("implementation_files_sha256")
    assert path.read_bytes() == before


@pytest.mark.parametrize("damage", ["checksum", "schema", "type", "bundle", "partial_bundle"])
def test_strict_failures_do_not_repair(tmp_path, artifact, damage):
    artifact = copy.deepcopy(artifact)
    if damage == "schema":
        artifact["schema_version"] = "unknown/2"
    elif damage == "type":
        artifact["models"][0]["support"]["positive"] = True
    elif damage == "bundle":
        artifact["provenance"]["implementation_bundle_sha256"] = "0" * 64
    elif damage == "partial_bundle":
        del artifact["provenance"]["implementation_bundle_sha256"]
    path = tmp_path / "broken.json"
    path.write_text(
        json.dumps(
            {
                "artifact": artifact,
                "sha256": "0" * 64 if damage == "checksum" else digest(artifact),
            }
        )
    )
    before = path.read_bytes()
    with pytest.raises(ValueError):
        inspect_model(path)
    result = cli(path)
    assert result.returncode != 0
    assert not result.stdout
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_missing_file_is_not_created(tmp_path):
    path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        inspect_model(path)
    assert cli(path).returncode != 0
    assert not path.exists()


@pytest.mark.parametrize("mode", ["api", "cli"])
def test_independent_process_without_training_or_dataset_modules(tmp_path, artifact, mode):
    path = tmp_path / "model.json"
    save_model(path, artifact)
    before = path.read_bytes()
    program = r"""
import importlib.abc
import json
import runpy
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = ("sklearn", "numpy", "dota_items.data", "dota_items.modeling.training",
                   "dota_items.modeling.batch", "dota_items.modeling.inference",
                   "dota_items.modeling.synthetic_foundation")
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("Inspection imported forbidden module: " + fullname)
sys.meta_path.insert(0, Block())
mode, model = sys.argv[1:]
if mode == "api":
    from dota_items.modeling.inspection import inspect_model
    print(json.dumps(inspect_model(model)))
else:
    sys.argv = ["scripts/model_foundation.py", "inspect", "--model", model]
    runpy.run_path("scripts/model_foundation.py", run_name="__main__")
"""
    result = subprocess.run(
        [sys.executable, "-c", program, mode, str(path)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == inspect_model(path)
    assert path.read_bytes() == before
