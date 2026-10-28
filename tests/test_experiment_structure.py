"""Whole-log orchestration boundaries, old entrypoints and implementation coverage."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture import PACKAGE, module_imports

from dota_items.experiments.whole_log import baseline


@pytest.mark.parametrize(
    "name,canonical",
    [
        ("whole_log_experiment", "baseline"),
        ("whole_log_regularization", "regularization"),
        ("verify_whole_log_handoff", "handoff"),
        ("diagnose_whole_log_experiment", "diagnostics"),
    ],
)
def test_legacy_imports_export_same_functions(name, canonical):
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / (name + ".py"))
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    module = __import__("dota_items.experiments.whole_log." + canonical, fromlist=["*"])
    for function in (
        "run",
        "run_experiment",
        "verify",
        "read_handoff",
        "compare",
        "fit_comparison",
    ):
        if hasattr(module, function):
            assert getattr(legacy, function) is getattr(module, function)


@pytest.mark.parametrize(
    "name",
    [
        "run_whole_log_experiment",
        "run_whole_log_regularization",
        "report_whole_log_regularization",
        "verify_whole_log_handoff",
        "diagnose_whole_log_experiment",
    ],
)
def test_cli_help_still_works(name):
    result = subprocess.run(
        [sys.executable, "scripts/" + name + ".py", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--output" in result.stdout


def test_orchestration_does_not_import_scripts():
    for path in (PACKAGE / "experiments").rglob("*.py"):
        for name in module_imports(path):
            assert not name.startswith("scripts.")
            assert name.split(".")[0] not in {
                "whole_log_experiment",
                "whole_log_regularization",
                "verify_whole_log_handoff",
                "diagnose_whole_log_experiment",
            }


def test_implementation_manifest_covers_new_modules():
    manifest = baseline.implementation_identity()["implementation_sha256"]
    for path in (PACKAGE / "experiments").rglob("*.py"):
        assert path.relative_to(Path.cwd()).as_posix() in manifest
    assert "src/dota_items/modeling/whole_log_comparison.py" in manifest


def test_readonly_handoff_import_does_not_load_training():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from dota_items.experiments.whole_log import handoff
assert 'dota_items.modeling.training' not in sys.modules
assert 'dota_items.experiments.whole_log.baseline' not in sys.modules
""",
        ],
        check=True,
    )
