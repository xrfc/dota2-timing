"""Enhancement refuses overwrite/selection drift; it never rewrites sealed originals."""

import importlib.util
import json
from pathlib import Path

import pytest


def cli():
    spec = importlib.util.spec_from_file_location(
        "enhance_cases", Path(__file__).parents[1] / "scripts/enhance_decision_cases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_output_refused(tmp_path):
    with pytest.raises(ValueError, match="Output exists"):
        cli().enhance(tmp_path)


def test_unexpected_selection_refused_before_output(tmp_path):
    old = tmp_path / "reports/decision-review-2026-10-27-v2"
    old.mkdir(parents=True)
    path = old / "cases.json"
    path.write_text(json.dumps({"cards": [{"case": {"id": "other"}}]}))
    before = path.read_bytes()
    output = tmp_path / "new"
    with pytest.raises(ValueError, match="Unexpected original case selection"):
        cli().enhance(output, tmp_path)
    assert path.read_bytes() == before and not output.exists()
