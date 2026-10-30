"""CLI guards keep live probes bounded and all old outputs immutable."""

import importlib.util
from pathlib import Path

import pytest


def load(name):
    path = Path(__file__).parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_and_probe_output_overwrite_refused(tmp_path):
    cli = load("probe_decision_state")
    with pytest.raises(ValueError, match="Plan output exists"):
        cli.prepare_plan(tmp_path)
    with pytest.raises(ValueError, match="Requires new output"):
        cli.run(tmp_path / "missing", 9056008987, tmp_path)


def test_state_package_overwrite_refused(tmp_path):
    with pytest.raises(ValueError, match="Output exists"):
        load("build_decision_state_cards").build(tmp_path)
