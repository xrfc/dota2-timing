"""The audit verifies a fixed snapshot without changing or trusting producer code."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def audit_module(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "farm_audit_test", scripts / "audit_b5_farm_income.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample(audit_module, tmp_path, monkeypatch):
    module = audit_module
    producer, batch_dir = tmp_path / "producer", tmp_path / "batch"
    producer.mkdir()
    batch_dir.mkdir()
    for name in module.batch.IMPLEMENTATION:
        path = producer / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raise RuntimeError('frozen producer must never be executed')\n")
    matches = [
        dict(
            match=mid,
            duration=200,
            patch=60,
            cases=[dict(match=mid, hero="hero0", t=100, fold=mid % 5, action="unknown")],
        )
        for mid in (101, 102)
    ]
    plan = dict(matches=matches)
    plan_path = tmp_path / "plan.json"
    module.write_json(plan_path, plan)
    # Small fixtures exercise I/O; the real closed-population validator has its own tests.
    monkeypatch.setattr(module.batch, "validate_plan", lambda value: None)
    manifest = dict(
        schema="b5-farm-run/1",
        plan_sha256=module.digest(plan),
        implementation_sha256={
            name: module.file_hash(producer / name) for name in module.batch.IMPLEMENTATION
        },
    )
    module.write_json(batch_dir / "manifest.json", manifest)

    def make_record(index=0):
        match = matches[index]
        capture = dict(
            schema=module.SCHEMA,
            match_id=match["match"],
            compat_manifest_sha256=module.COMPAT_SHA256,
            sampling="first_tick_start_before_entity_updates",
            ownership="player_resource_selected_hero_and_team_slot",
            window_convention="integer game seconds [t,t+seconds)",
            recipients={
                f"hero{i}": dict(team=2 + i // 5, slot=i % 5, resource_index=i) for i in range(10)
            },
            boundaries=[
                dict(
                    hero="hero0",
                    t=t,
                    tick=t * 30,
                    net_tick=t * 30,
                    status="observed",
                    creep=100,
                    neutral=50,
                )
                for t in (100, 120, 130)
            ],
            events=[],
            gold_event_counts={},
        )
        return dict(
            binding=deepcopy(manifest),
            source=deepcopy(match),
            capture=capture,
            rows=module.batch.score_windows(match["cases"], capture, match["duration"]),
        )

    def save(record, *, rescore=False, checksum=True):
        if rescore:
            record["rows"] = module.batch.score_windows(
                record["source"]["cases"], record["capture"], record["source"]["duration"]
            )
        if checksum:
            record["payload_sha256"] = module.digest(
                {k: v for k, v in record.items() if k != "payload_sha256"}
            )
        module.write_json(batch_dir / f"{record['source']['match']}.json", record)

    def run(name="audit"):
        return module.audit(plan_path, batch_dir, producer, tmp_path / name)

    return dict(
        module=module,
        root=tmp_path,
        producer=producer,
        batch=batch_dir,
        plan=plan_path,
        make=make_record,
        save=save,
        run=run,
    )


@pytest.mark.parametrize("completed", [0, 1, 2])
def test_partial_and_complete_counts_are_explicit_and_reproducible(sample, completed):
    for i in range(completed):
        sample["save"](sample["make"](i))
    first = sample["run"]()
    assert first["matches_complete"] == completed
    assert first["matches_pending"] == first["opportunities_pending"] == 2 - completed
    assert first["extraction_complete"] == (completed == 2)
    assert first["counter_zero_cells"] == completed * 4
    assert first["unexplained_difference_cells"] == 0
    assert sample["run"]("audit-copy") == first
    for path in (sample["root"] / "audit").iterdir():
        assert path.read_bytes() == (sample["root"] / "audit-copy" / path.name).read_bytes()


def test_missing_counter_and_zero_remain_distinct(sample):
    record = sample["make"]()
    record["capture"]["boundaries"][-1]["creep"] = None
    sample["save"](record, rescore=True)
    result = sample["run"]()
    assert result["amount_categories"] == {"equal": 3, "unobserved": 1}
    assert result["counter_zero_cells"] == 3
    assert result["windows"]["30"]["statuses"] == {"missing_counter": 1}


def test_missing_endpoint_remains_unobserved(sample):
    record = sample["make"]()
    endpoint = record["capture"]["boundaries"][-1]
    endpoint.update(status="missing_endpoint", creep=None, neutral=None, tick=None, net_tick=None)
    sample["save"](record, rescore=True)
    result = sample["run"]()
    assert result["windows"]["30"]["statuses"] == {"missing_endpoint": 1}
    assert result["amount_categories"] == {"equal": 2, "unobserved": 2}


def test_negative_difference_is_retained_and_never_declared_explained(sample):
    record = sample["make"]()
    record["capture"]["events"] = [dict(hero="hero0", kind="creep", t=110, tick=3300, value=5)]
    record["capture"]["gold_event_counts"] = {"13": 1}
    sample["save"](record, rescore=True)
    result = sample["run"]()
    assert result["negative_difference_cells"] == result["unexplained_difference_cells"] == 2
    assert ",-5" in (sample["root"] / "audit/discrepancies.csv").read_text()


def test_payload_tampering_is_rejected(sample):
    record = sample["make"]()
    sample["save"](record)
    record["rows"] = []
    sample["save"](record, checksum=False)
    with pytest.raises(ValueError, match="checksum mismatch"):
        sample["run"]()


@pytest.mark.parametrize("mode", ["lost", "duplicate", "value", "boolean", "action"])
def test_rehashed_corruption_cannot_hide_changed_cases_or_amounts(sample, mode):
    record = sample["make"]()
    if mode == "lost":
        record["rows"] = []
    elif mode == "duplicate":
        record["rows"] *= 2
    elif mode == "action":
        record["rows"][0]["action"] = "stay_lane"
    else:
        record["rows"][0]["windows"]["20"]["creep"]["counter"] = False if mode == "boolean" else 99
    sample["save"](record)
    with pytest.raises(ValueError, match="rescored cases"):
        sample["run"]()


@pytest.mark.parametrize("mode", ["source", "capture_match", "schema", "compat", "endpoints"])
def test_source_and_capture_contracts_are_checked(sample, mode):
    record = sample["make"]()
    if mode == "source":
        record["source"]["duration"] = 300
    elif mode == "capture_match":
        record["capture"]["match_id"] = 102
    elif mode == "schema":
        record["capture"]["schema"] = "gem-farm-income/1"
    elif mode == "compat":
        record["capture"]["compat_manifest_sha256"] = "unregistered"
    else:
        record["capture"]["boundaries"].pop()
    sample["save"](record)
    with pytest.raises(ValueError, match="mismatch"):
        sample["run"]()


@pytest.mark.parametrize("target", ["input", "producer"])
def test_changes_during_audit_block_publication(sample, monkeypatch, target):
    sample["save"](sample["make"]())
    module = sample["module"]
    original = module.batch.score_windows

    def drift(*args):
        path = (
            sample["batch"] / "101.json"
            if target == "input"
            else sample["producer"] / module.batch.IMPLEMENTATION[0]
        )
        path.write_bytes(path.read_bytes() + b"\n")
        return original(*args)

    monkeypatch.setattr(module.batch, "score_windows", drift)
    with pytest.raises(ValueError, match="changed during verification"):
        sample["run"]()
    assert not (sample["root"] / "audit").exists()


def test_wrong_producer_binding_is_rejected_without_executing_it(sample):
    (sample["producer"] / sample["module"].batch.IMPLEMENTATION[0]).write_text("different")
    with pytest.raises(ValueError, match="producer or plan"):
        sample["run"]()


def test_deleted_snapshot_input_cannot_publish(sample, monkeypatch):
    sample["save"](sample["make"]())
    module = sample["module"]
    original = module.batch.score_windows

    def remove(*args):
        (sample["batch"] / "101.json").unlink()
        return original(*args)

    monkeypatch.setattr(module.batch, "score_windows", remove)
    with pytest.raises(FileNotFoundError):
        sample["run"]()
    assert not (sample["root"] / "audit").exists()


@pytest.mark.parametrize("filename", ["999.json", "extra.json", "0101.json"])
def test_extra_batch_files_are_rejected(sample, filename):
    (sample["batch"] / filename).write_text("{}")
    with pytest.raises(ValueError, match="unknown extra"):
        sample["run"]()


def test_valid_publication_during_audit_is_deferred_to_next_snapshot(sample, monkeypatch):
    sample["save"](sample["make"]())
    second = sample["make"](1)
    module = sample["module"]
    original = module.batch.score_windows

    def publish(*args):
        sample["save"](second)
        return original(*args)

    monkeypatch.setattr(module.batch, "score_windows", publish)
    result = sample["run"]()
    assert result["matches_complete"] == result["matches_pending"] == 1
    provenance = json.loads((sample["root"] / "audit/provenance.json").read_text())
    assert provenance["completed_matches"] == [101]
    assert provenance["pending_matches"] == [102]


def test_existing_output_is_not_overwritten(sample):
    target = sample["root"] / "audit"
    target.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        sample["run"]()
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("directory", ["batch", "producer"])
def test_output_cannot_modify_input_directories(sample, directory):
    with pytest.raises(ValueError, match="outside batch and producer"):
        sample["module"].audit(
            sample["plan"], sample["batch"], sample["producer"], sample[directory] / "audit"
        )


def test_audit_invokes_the_closed_population_gate(audit_module, tmp_path):
    path = tmp_path / "plan.json"
    path.write_text('{"matches": []}')
    with pytest.raises(ValueError, match="unsupported plan/population"):
        audit_module.audit(path, tmp_path / "batch", tmp_path / "producer", tmp_path / "output")
