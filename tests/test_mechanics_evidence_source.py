import hashlib
import json
from pathlib import Path

import pytest

from dota_items.data import mechanics_evidence_source as module
from dota_items.data.mechanics_engineering_evidence import SOURCE_PATHS


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    directory = tmp_path / "baseline"
    original = write(tmp_path / "original.json", {"input": True})
    equivalent = write(directory / "mechanics-source-equivalence.json", {"used_files": {}})
    admission = write(
        directory / "mechanics-admission.json",
        {"source_refs": {"original": original, "equivalence": equivalent}},
    )
    outputs = {Path(ref["path"]).name: ref["sha256"] for ref in (equivalent, admission)}
    for name in module.BASE_SCHEMAS:
        ref = write(directory / f"mechanics-{name}.json", {"source_refs": {}})
        outputs[Path(ref["path"]).name] = ref["sha256"]
    receipt = write(
        directory / "receipt.json",
        {
            "schema": "patch-review-assets-receipt/1",
            "exact_patch": "7.42",
            "training_allowed": False,
            "action_review_allowed": False,
            "used_files": {original["path"]: original["sha256"]},
            "output_sha256": outputs,
        },
    )
    refs = {key: write(tmp_path / filename, {}) for key, filename in SOURCE_PATHS.items()}
    refs["admission"] = admission
    engineering = write(tmp_path / "engineering.json", {"source_refs": refs})
    # A registered miniature receipt exercises source closure without local reports.
    monkeypatch.setattr(module, "BASE_RECEIPT_SHA256", receipt["sha256"])
    return receipt, engineering, tmp_path, equivalent


def open_source(values):
    return module.MechanicsEvidenceSource(values[0], values[1], repository_root=values[2])


def test_nested_baseline_output_and_all_proof_sources_are_pinned(inputs):
    source = open_source(inputs)
    assert source.pins.inventory[inputs[3]["path"]] == inputs[3]["sha256"]
    assert set(source.documents) == set(SOURCE_PATHS)
    source.verify()
    Path(inputs[3]["path"]).write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        source.verify()


def test_unknown_baseline_registration_rejected_before_reading_file(tmp_path):
    with pytest.raises(ValueError, match="Unregistered"):
        module.MechanicsEvidenceSource(
            {"path": str(tmp_path / "absent"), "sha256": "0" * 64}, {}, repository_root=tmp_path
        )


def test_missing_or_changed_equivalence_output_cannot_be_consumed(inputs):
    Path(inputs[3]["path"]).write_text("{}")
    with pytest.raises(ValueError, match="digest"):
        open_source(inputs)


@pytest.mark.parametrize("damage", ["wrong_admission", "extra_source", "relocated_source"])
def test_engineering_reference_substitution_is_rejected(inputs, damage):
    receipt, ref, root, equivalent = inputs
    d = json.loads(Path(ref["path"]).read_text())
    if damage == "wrong_admission":
        d["source_refs"]["admission"] = equivalent
    elif damage == "extra_source":
        d["source_refs"]["extra"] = equivalent
    else:
        key = next(iter(SOURCE_PATHS))
        d["source_refs"][key] = write(root / "other.json", {})
    altered = write(Path(ref["path"]), d)
    with pytest.raises(ValueError):
        open_source((receipt, altered, root, equivalent))
