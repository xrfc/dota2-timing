"""Task scope is closed; all training here uses fabricated samples only."""

import copy
import subprocess
import sys

import pytest

from dota_items.contracts.tasks import TASK_ID, task_contract, validate_task_contract
from dota_items.data.task_snapshot import build_task_snapshot, verify_task_snapshot
from dota_items.modeling.artifacts import load_model, save_model, validate_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.modeling.inference import predict_lineup
from dota_items.modeling.inspection import inspect_model
from dota_items.modeling.provenance import PRE_TASK_IMPLEMENTATION_FILES
from dota_items.modeling.synthetic_foundation import synthetic_snapshot
from dota_items.modeling.training import fit_model
from dota_items.storage import digest, json_bytes


def versioned():
    snapshot = synthetic_snapshot()
    snapshot["schema_version"] = "purchase-log-modeling-snapshot/2"
    snapshot["task"]["contract"] = task_contract()
    return snapshot


def fit(snapshot, family="frequency"):
    return fit_model(
        adapt_snapshot(snapshot),
        family=family,
        source_sha256="a" * 64,
        code_revision="synthetic-task-contract-test",
    )


@pytest.mark.parametrize(
    "path,value",
    [
        (("task_id",), "unregistered/1"),
        (("schema_version",), "dota-task-contract/2"),
        (("target_hero_id",), 1),
        (("target_hero_id",), 8.0),
        (("role", "requested_position"), True),
        (("role", "evidence"), "verified"),
        (("patch_scope", "patches"), ["7.41f", "another-patch"]),
        (("window", "end_seconds"), 1200),
        (("window", "interval"), "[start,end]"),
        (("labels", "negative_means"), "did_not_purchase"),
        (("labels", "candidate_items"), ["bfury"]),
        (("features", "encoding"), "embedding/1"),
        (("features", "fit_split"), "validation"),
        (("extra",), True),
    ],
)
def test_changed_scope_rejected_by_snapshot_and_artifact(path, value):
    snapshot = versioned()
    artifact = fit(snapshot)
    changed = task_contract()
    parent = changed
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    snapshot["task"]["contract"] = changed
    artifact["task"]["contract"] = changed
    with pytest.raises(ValueError):
        adapt_snapshot(snapshot)
    with pytest.raises(ValueError):
        validate_model(artifact)


def test_registry_returns_independent_values():
    contract = task_contract()
    contract["labels"]["candidate_items"].clear()
    validate_task_contract(task_contract())
    with pytest.raises(ValueError):
        task_contract("new-hero/1")


@pytest.mark.parametrize("family", ["frequency", "logistic"])
def test_new_roundtrip_and_legacy_numerical_parity(tmp_path, family):
    snapshot = versioned()
    artifact = fit(snapshot, family)
    legacy = fit(synthetic_snapshot(), family)
    assert artifact["schema_version"] == "purchase-foundation-model/2"
    assert artifact["models"] == legacy["models"]
    path = tmp_path / "model.json"
    save_model(path, artifact)
    before = path.read_bytes()
    loaded = load_model(path, expected_task_contract=task_contract())
    features = snapshot["samples"][0]["features"]
    prediction = predict_lineup(loaded, features, expected_task_contract=task_contract())
    assert prediction["probabilities"] == predict_lineup(legacy, features)["probabilities"]
    assert prediction["task_contract"] == task_contract()
    assert inspect_model(path)["task_contract"] == task_contract()
    assert path.read_bytes() == before
    old_path = tmp_path / "old.json"
    save_model(old_path, legacy)
    assert load_model(old_path) == legacy
    with pytest.raises(ValueError, match="legacy scope"):
        load_model(old_path, expected_task_contract=task_contract())
    with pytest.raises(ValueError, match="legacy scope"):
        predict_lineup(legacy, features, expected_task_contract=task_contract())


@pytest.mark.parametrize("container", ["snapshot", "model"])
@pytest.mark.parametrize("damage", ["remove", "downgrade"])
def test_contract_cannot_be_omitted_or_silently_downgraded(container, damage):
    value = versioned()
    validate = adapt_snapshot
    if container == "model":
        value, validate = fit(value), validate_model
    if damage == "remove":
        del value["task"]["contract"]
    else:
        value["schema_version"] = value["schema_version"].replace("/2", "/1")
    with pytest.raises(ValueError):
        validate(value)


def test_outer_label_fields_must_agree_with_contract():
    value = versioned()
    value["task"]["window"] = [0, 1200]
    with pytest.raises(ValueError):
        adapt_snapshot(value)


def test_previous_modular_manifest_still_loads_but_cannot_claim_v2():
    artifact = fit(synthetic_snapshot())
    provenance = artifact["provenance"]
    files = {
        name: provenance["implementation_files_sha256"][name]
        for name in PRE_TASK_IMPLEMENTATION_FILES
    }
    provenance["implementation_files_sha256"] = files
    provenance["implementation_bundle_sha256"] = digest(files)
    validate_model(artifact)
    artifact["schema_version"] = "purchase-foundation-model/2"
    artifact["task"]["contract"] = task_contract()
    with pytest.raises(ValueError, match="fingerprint"):
        validate_model(artifact)


def producer_fixture(tmp_path, monkeypatch):
    summary = {
        "audit": {
            "config": {
                "hero_id": 8,
                "requested_role": 1,
                "requested_patch": "7.41f",
                "window_start": 0,
                "window_end": 1800,
                "candidate_items": task_contract()["labels"]["candidate_items"],
            },
            "results": [{"patch_time_check": "time_consistent"}],
        }
    }
    path = tmp_path / "summary.json"
    path.write_bytes(json_bytes(summary))
    original = synthetic_snapshot()
    monkeypatch.setattr(
        "dota_items.data.task_snapshot.build_snapshot",
        lambda *args, **kwargs: copy.deepcopy(original),
    )
    return path, summary, original


def test_producer_consumer_roundtrip_and_no_input_mutation(tmp_path, monkeypatch):
    path, summary, original = producer_fixture(tmp_path, monkeypatch)
    value = build_task_snapshot(path, task_id=TASK_ID)
    adapt_snapshot(value)
    assert "contract" not in original["task"]
    assert path.read_bytes() == json_bytes(summary)
    output = tmp_path / "new.json"
    output.write_bytes(json_bytes(value))
    assert verify_task_snapshot(output, path) == value
    value["task"]["contract"]["role"]["evidence"] = "verified"
    output.write_bytes(json_bytes(value))
    with pytest.raises(ValueError, match="reconstruction"):
        verify_task_snapshot(output, path)


@pytest.mark.parametrize(
    "key,value",
    [
        ("hero_id", 1),
        ("requested_role", 2),
        ("requested_patch", "next"),
        ("window_end", 1200),
        ("candidate_items", ["bfury"]),
    ],
)
def test_producer_rejects_unregistered_configuration_before_reconstruction(
    tmp_path, monkeypatch, key, value
):
    path, summary, _ = producer_fixture(tmp_path, monkeypatch)
    summary["audit"]["config"][key] = value
    path.write_bytes(json_bytes(summary))
    monkeypatch.setattr(
        "dota_items.data.task_snapshot.build_snapshot",
        lambda *a, **kw: pytest.fail("Unsupported task must fail before source processing"),
    )
    with pytest.raises(ValueError, match="configuration"):
        build_task_snapshot(path)


def test_producer_does_not_promote_uncertain_patch_evidence(tmp_path, monkeypatch):
    path, summary, _ = producer_fixture(tmp_path, monkeypatch)
    summary["audit"]["results"][0]["patch_time_check"] = "boundary_uncertain"
    path.write_bytes(json_bytes(summary))
    with pytest.raises(ValueError, match="release-time"):
        build_task_snapshot(path)


def test_cli_predict_enforces_task_and_unknown_id_rejected(tmp_path):
    snapshot = versioned()
    path = tmp_path / "model.json"
    lineup = tmp_path / "lineup.json"
    save_model(path, fit(snapshot))
    lineup.write_bytes(json_bytes(snapshot["samples"][0]["features"]))
    command = [
        sys.executable,
        "scripts/model_foundation.py",
        "predict",
        "--model",
        str(path),
        "--lineup",
        str(lineup),
        "--task-id",
    ]
    completed = subprocess.run(command + [TASK_ID], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert TASK_ID in completed.stdout
    rejected = subprocess.run(command + ["other/1"], capture_output=True, text=True)
    assert rejected.returncode != 0
