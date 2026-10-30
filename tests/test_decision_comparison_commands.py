"""Guard output immutability before any reads or optional parser imports."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "name,entry", [("build_decision_comparisons", "build"), ("audit_decision_mana", "audit")]
)
def test_existing_output_refused_without_modifying_it(tmp_path, name, entry):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    marker = tmp_path / "preserved.txt"
    marker.write_text("original")
    with pytest.raises(ValueError):
        getattr(module, entry)(tmp_path)
    assert marker.read_text() == "original"
    assert list(tmp_path.iterdir()) == [marker]
