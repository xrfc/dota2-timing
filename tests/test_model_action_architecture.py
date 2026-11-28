"""Executable M1 layering and prediction import boundaries; no real artifacts."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/dota_items/modeling/awareness"
MODULES = ("action_features", "action_models", "action_values", "action_evaluation")


def dependencies(name):
    tree = ast.parse((PACKAGE / f"{name}.py").read_text())
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name(
                    "." * node.level + base, "dota_items.modeling.awareness"
                )
            result.add(base)
            result.update(f"{base}.{alias.name}" for alias in node.names)
    return result


@pytest.mark.parametrize("name", MODULES)
def test_action_prediction_has_no_script_data_or_training_dependency(name):
    denied = (
        "scripts",
        "lane_study",
        "lane_study_baselines",
        "lane_study_sequence",
        "outcome_values",
        "dota_items.data",
        "dota_items.sources",
        "dota_items.experiments",
        "dota_items.workflow",
        "dota_items.modeling.awareness.action_training",
        "scipy.optimize",
    )
    imports = dependencies(name)
    assert not {s for s in imports if any(s == d or s.startswith(d + ".") for d in denied)}
    tree = ast.parse((PACKAGE / f"{name}.py").read_text())
    # The M1 modules have no fitted-state learning or filesystem responsibilities.
    assert not {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and (node.name == "fit" or node.name.startswith("fit_"))
    }


def test_internal_action_modules_are_acyclic_and_prediction_cannot_import_evaluation():
    graph = {
        name: {
            other
            for other in MODULES
            if any(
                s == f"dota_items.modeling.awareness.{other}"
                or s.startswith(f"dota_items.modeling.awareness.{other}.")
                for s in dependencies(name)
            )
        }
        for name in MODULES
    }
    assert graph["action_features"] == set()
    assert graph["action_models"] <= {"action_features"}
    assert graph["action_values"] <= {"action_features", "action_models"}
    assert graph["action_evaluation"] <= {"action_features", "action_models", "action_values"}


def test_sequence_prediction_import_does_not_load_optimizer_or_business_readers():
    code = """
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        prefixes = ('scripts', 'dota_items.data', 'dota_items.sources',
                    'dota_items.workflow', 'dota_items.experiments', 'scipy.optimize',
                    'dota_items.modeling.awareness.action_training')
        if any(fullname == p or fullname.startswith(p + '.') for p in prefixes):
            raise AssertionError('forbidden prediction import: ' + fullname)
sys.meta_path.insert(0, Block())
import numpy as np
from dota_items.modeling.awareness.action_models import SequenceOutcome
from dota_items.modeling.awareness.action_features import FeatureScale
scale = FeatureScale(np.zeros(1), np.ones(1))
# 4 window channels, 3 static channels after missing indicators + proposed action.
state = SequenceOutcome(True, scale, scale, np.zeros(64), 1.0, 2.0, None)
hits, death = state.predict([{'static': [1.0], 'sequence': [[0.0], [1.0], [2.0]],
                             'action': 'farm'}])
assert hits.tolist() == [1.0] and death.tolist() == [0.5]
assert 'scipy.optimize' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_legacy_oracle_sources_match_frozen_manifest_and_m1_baseline():
    import hashlib
    import json

    folder = ROOT / "tests/fixtures/action_legacy"
    manifest = json.loads((folder / "manifest.json").read_text())
    baseline = json.loads((ROOT / "docs/acceptance/action-m1-baseline.json").read_text())
    assert manifest["revision"] == "7ca2ae3d14edae67042634f820a9456827d78ce1"
    assert manifest["files"] == baseline["test_sources"]
    assert set(manifest["files"]) == {
        "baselines.py.txt",
        "sequence.py.txt",
        "outcome_values.py.txt",
        "lane_study.py.txt",
    }
    for name, evidence in manifest["files"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == evidence["sha256"]
    assert baseline["real_model_loaded"] is False
    assert baseline["real_migration_activated"] is False
    assert baseline["real_compatibility_matrix_entries"] == 0
