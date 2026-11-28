"""Offline batch authorization, atomic publication and saved-input validation."""

import bz2
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from dota_items.storage import digest, file_hash, write_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "b5_camp_batch", ROOT / "scripts/collect_b5_camp_evidence.py"
)
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def raw_capture(mid, cases):
    return dict(
        schema="gem-camp-evidence/1",
        match_id=mid,
        compat_manifest_sha256=batch.COMPAT_SHA256,
        omniscient=True,
        usage="audit_only_requires_team_visibility_projection",
        sampling="first_tick_start_before_entity_updates",
        frames=[
            dict(
                hero=hero,
                t=t,
                tick=100 + t,
                net_tick=100 + t,
                status="observed",
                observer=dict(team=2, slot=0, resource_index=0),
                units=[
                    dict(
                        entity_index=10,
                        entity_serial=2,
                        unit_name="centaur",
                        team=4,
                        x=0.0,
                        y=20.0,
                        health=0,
                        max_health=None,
                        life_state=0,
                        visibility=dict(radiant="visible", dire="hidden"),
                    )
                ],
            )
            for hero, t in cases
        ],
    )


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    data, out = tmp_path / "data", tmp_path / "batch"
    matches = []
    ids = [mid for mid in range(9000000000, 9000000020) if not batch.is_holdout(mid)][:2]
    for i, mid in enumerate(ids):
        demo = data / "demos" / f"{mid}.dem.bz2"
        demo.parent.mkdir(parents=True, exist_ok=True)
        demo.write_bytes(bz2.compress(f"PBDEMS2:{mid}".encode()))
        receipt, meta = data / "receipts" / f"{mid}.json", data / "meta" / f"{mid}.json"
        write_json(receipt, dict(match_id=mid, demo_sha256=file_hash(demo)))
        write_json(meta, dict(match_id=mid, duration=100, patch=60))
        fold = int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5
        cases = [
            dict(
                match=mid,
                hero="npc_dota_hero_sven",
                t=100 + n,
                fold=fold,
                action="unknown" if n else "stay_lane",
            )
            for n in range(i + 1)
        ]
        matches.append(
            dict(
                match=mid,
                duration=100,
                patch=60,
                cases=cases,
                demo_sha256=file_hash(demo),
                receipt_sha256=file_hash(receipt),
                meta_sha256=file_hash(meta),
            )
        )
    plan = dict(
        schema="b5-farm-plan/1",
        rows_sha256=batch.ROWS_SHA256,
        routes_sha256=batch.ROUTES_SHA256,
        matches=matches,
    )
    population = [c for m in matches for c in m["cases"]]
    monkeypatch.setattr(batch, "MATCHES", 2)
    monkeypatch.setattr(batch, "OPPORTUNITIES", 3)
    monkeypatch.setattr(batch, "POPULATION_SHA256", digest(population))
    monkeypatch.setattr(batch, "PLAN_SHA256", digest(plan))
    monkeypatch.setattr(batch, "verify_compatibility", lambda root: batch.COMPAT_SHA256)
    monkeypatch.setattr(
        batch,
        "capture_camp_evidence",
        lambda path, cases: raw_capture(int(path.read_bytes().split(b":")[1]), cases),
    )
    return dict(
        data=data, out=out, plan=plan, expected=batch.binding(plan), compat=tmp_path / "gem"
    )


def run(values, **kwargs):
    return batch.run(**values, **kwargs)


def match_dir(values, n=0):
    return values["out"] / "matches" / str(values["plan"]["matches"][n]["match"])


def resign(directory):
    receipt = json.loads((directory / "receipt.json").read_bytes())
    receipt.pop("payload_sha256")
    receipt.update(
        raw_sha256=file_hash(directory / "raw.json"),
        evidence_sha256=file_hash(directory / "evidence.json"),
    )
    receipt["payload_sha256"] = digest(receipt)
    write_json(directory / "receipt.json", receipt)


def test_partial_then_strict_resume_keeps_fixed_population(inputs, monkeypatch):
    assert batch.validate_plan(inputs["plan"]) == inputs["plan"]
    first = run(inputs, limit=1)
    assert first["planned_matches"] == 2 and first["planned_opportunities"] == 3
    assert first["completed_matches"] == 1 and first["completed_opportunities"] == 1
    assert not first["complete"] and first["pending_opportunities"] == 2
    before = {p.name: p.read_bytes() for p in match_dir(inputs).iterdir()}
    second = run(inputs)
    assert second["complete"] and second["completed_opportunities"] == 3
    assert second["visible_unit_observations"] == 3
    assert second["visible_field_coverage"]["health"] == dict(present=3, missing=0)
    assert second["visible_field_coverage"]["max_health"] == dict(present=0, missing=3)
    assert second["stock_complete"] is False and second["empty_confirmed"] is None
    assert before == {p.name: p.read_bytes() for p in match_dir(inputs).iterdir()}
    monkeypatch.setattr(
        batch, "capture_camp_evidence", lambda *a: pytest.fail("resume must not parse")
    )
    assert run(inputs)["complete"]


@pytest.mark.parametrize(
    "mutation", ["action", "fold", "metadata", "hash", "duplicate", "drop", "heldout"]
)
def test_plan_drift_rejected(inputs, mutation):
    plan = deepcopy(inputs["plan"])
    match = plan["matches"][0]
    case = match["cases"][0]
    if mutation == "action":
        case["action"] = "move_to_jungle"
    elif mutation == "fold":
        case["fold"] = (case["fold"] + 1) % 5
    elif mutation == "metadata":
        match["duration"] += 1
    elif mutation == "hash":
        match["demo_sha256"] = "0" * 64
    elif mutation == "duplicate":
        match["cases"].append(deepcopy(case))
    elif mutation == "drop":
        plan["matches"].pop()
    else:
        match["match"] = next(mid for mid in range(9000000000, 9000000100) if batch.is_holdout(mid))
    with pytest.raises(ValueError):
        batch.validate_plan(plan)


def test_fixed_known_population_constants():
    assert batch.MATCHES == 1169 and batch.OPPORTUNITIES == 15005
    assert batch.PLAN_SHA256 == "8ad71d1e60b251360b9e96a4afc0c4a599443ddaa1c88abdb012b060cba7f3ad"


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "change", "leak"])
def test_rehashed_public_tamper_rejected(inputs, mutation):
    run(inputs, limit=1)
    directory = match_dir(inputs)
    public = json.loads((directory / "evidence.json").read_bytes())
    if mutation == "drop":
        public["frames"] = []
    elif mutation == "duplicate":
        public["frames"].append(deepcopy(public["frames"][0]))
    elif mutation == "change":
        public["frames"][0]["units"][0]["health"] = 200
    else:
        public["frames"][0]["hidden_total"] = 500
    write_json(directory / "evidence.json", public)
    resign(directory)
    with pytest.raises(ValueError, match="whitelist projection"):
        batch.verify_result(directory, inputs["plan"]["matches"][0], inputs["expected"])


@pytest.mark.parametrize("mutation", ["match_id", "compat", "case", "source", "checksum"])
def test_source_capture_and_receipt_binding_rejected(inputs, mutation):
    run(inputs, limit=1)
    directory = match_dir(inputs)
    if mutation in ("match_id", "compat", "case"):
        raw = json.loads((directory / "raw.json").read_bytes())
        if mutation == "match_id":
            raw["capture"]["match_id"] += 1
        elif mutation == "compat":
            raw["capture"]["compat_manifest_sha256"] = "0" * 64
        else:
            raw["capture"]["frames"][0]["t"] += 1
        write_json(directory / "raw.json", raw)
        resign(directory)
    else:
        receipt = json.loads((directory / "receipt.json").read_bytes())
        if mutation == "source":
            receipt["source"]["cases"][0]["action"] = "unknown"
            receipt.pop("payload_sha256")
            receipt["payload_sha256"] = digest(receipt)
        else:
            receipt["payload_sha256"] = "0" * 64
        write_json(directory / "receipt.json", receipt)
    with pytest.raises(ValueError):
        batch.verify_result(directory, inputs["plan"]["matches"][0], inputs["expected"])


@pytest.mark.parametrize("source", ["demo", "receipt", "meta"])
def test_input_drift_during_parse_refuses_atomic_publication(inputs, monkeypatch, source):
    mid = inputs["plan"]["matches"][0]["match"]
    before = batch.capture_camp_evidence

    def mutate(path, cases):
        value = before(path, cases)
        relative = (
            f"demos/{mid}.dem.bz2"
            if source == "demo"
            else f"{source}s/{mid}.json"
            if source == "receipt"
            else f"meta/{mid}.json"
        )
        target = inputs["data"] / relative
        target.write_bytes(target.read_bytes() + b" ")
        return value

    monkeypatch.setattr(batch, "capture_camp_evidence", mutate)
    result = run(inputs, limit=1)
    assert len(result["run_errors"]) == 1 and not match_dir(inputs).exists()
    assert list((inputs["out"] / "matches").iterdir()) == []


def test_producer_drift_during_parse_refuses_publication(inputs, monkeypatch):
    before = batch.capture_camp_evidence

    def mutate(path, cases):
        value = before(path, cases)
        monkeypatch.setattr(batch, "implementation_hashes", lambda: {"changed": "source"})
        return value

    monkeypatch.setattr(batch, "capture_camp_evidence", mutate)
    with pytest.raises(ValueError, match="implementation changed"):
        run(inputs, limit=1)
    assert not match_dir(inputs).exists()


def test_unknown_output_match_and_changed_producer_cannot_resume(inputs):
    run(inputs, limit=1)
    extra = inputs["out"] / "matches" / "123"
    extra.mkdir()
    with pytest.raises(ValueError, match="unknown or unsafe"):
        run(inputs)
    extra.rmdir()
    manifest = json.loads((inputs["out"] / "manifest.json").read_bytes())
    manifest["implementation_sha256"]["unexpected.py"] = "0" * 64
    write_json(inputs["out"] / "manifest.json", manifest)
    with pytest.raises(ValueError, match="resume producer or plan drift"):
        run(inputs)


def test_nonempty_unbound_output_and_writer_lock_rejected(inputs):
    inputs["out"].mkdir()
    unknown = inputs["out"] / "unrelated.txt"
    unknown.write_text("keep")
    with pytest.raises(ValueError, match="unbound nonempty"):
        run(inputs)
    assert unknown.read_text() == "keep"
    unknown.unlink()
    lock = inputs["out"] / ".writer.lock"
    lock.write_text("someone else")
    with pytest.raises(ValueError, match="writer is busy"):
        run(inputs)
    assert lock.read_text() == "someone else"


@pytest.mark.parametrize(
    "kwargs", [dict(workers=0), dict(workers=5), dict(limit=0), dict(match_ids=[123])]
)
def test_invalid_selection_or_concurrency_refused_before_outputs(inputs, kwargs):
    with pytest.raises(ValueError):
        run(inputs, **kwargs)
    assert not inputs["out"].exists()


def test_output_cannot_be_inside_source_data(inputs):
    inputs["out"] = inputs["data"] / "output"
    with pytest.raises(ValueError, match="separate from source data"):
        run(inputs)


def test_report_uses_fixed_published_snapshot(inputs, monkeypatch):
    run(inputs, limit=1)
    original = batch.verify_result
    added = False

    def publish_later(directory, match, expected):
        nonlocal added
        result = original(directory, match, expected)
        if not added:
            added = True
            batch.execute_match(
                inputs["plan"]["matches"][1],
                inputs["data"],
                inputs["out"],
                expected,
                inputs["compat"],
            )
        return result

    monkeypatch.setattr(batch, "verify_result", publish_later)
    progress = batch.report(inputs["plan"], inputs["data"], inputs["out"], inputs["expected"])
    assert progress["completed_matches"] == 1 and not progress["complete"]
    assert match_dir(inputs, 1).is_dir()


def test_missing_and_zero_visible_frames_are_separate(inputs, monkeypatch):
    original = batch.capture_camp_evidence

    def missing(path, cases):
        value = original(path, cases)
        for frame in value["frames"]:
            if frame["t"] == 100:
                frame.update(status="missing_observer", observer=None)
            else:
                frame["units"] = []
        return value

    monkeypatch.setattr(batch, "capture_camp_evidence", missing)
    result = run(inputs)
    assert result["frame_statuses"] == dict(missing_observer=2, observed=1)
    assert result["observed_frames_without_visible_units"] == 1
    assert result["visible_unit_observations"] == 0
    assert result["complete"] and result["stock_complete"] is False


def test_noncanonical_plan_bytes_refused_before_reading_any_replay(inputs, monkeypatch):
    path = inputs["data"].parent / "plan.json"
    write_json(path, inputs["plan"])
    path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(batch, "verify_inputs", lambda *args: pytest.fail("must reject plan first"))
    with pytest.raises(ValueError, match="plan bytes changed"):
        batch.main(["report", "--plan", str(path), "--out", str(inputs["out"])])


@pytest.mark.parametrize("source", ["demo", "receipt", "meta"])
def test_report_rechecks_inputs_after_last_bundle(inputs, monkeypatch, source):
    run(inputs)
    original = batch.verify_result
    mid = inputs["plan"]["matches"][0]["match"]

    def mutate(directory, match, expected):
        result = original(directory, match, expected)
        if directory == match_dir(inputs, 1):
            relative = (
                f"demos/{mid}.dem.bz2"
                if source == "demo"
                else f"receipts/{mid}.json"
                if source == "receipt"
                else f"meta/{mid}.json"
            )
            path = inputs["data"] / relative
            path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(batch, "verify_result", mutate)
    with pytest.raises(ValueError, match="fingerprint changed"):
        batch.report(inputs["plan"], inputs["data"], inputs["out"], inputs["expected"])


def test_report_rechecks_earlier_bundle_after_later_read(inputs, monkeypatch):
    run(inputs)
    original = batch.verify_result

    def mutate(directory, match, expected):
        result = original(directory, match, expected)
        if directory == match_dir(inputs, 1):
            (match_dir(inputs) / "raw.json").unlink()
        return result

    monkeypatch.setattr(batch, "verify_result", mutate)
    with pytest.raises(ValueError, match="file set changed"):
        batch.report(inputs["plan"], inputs["data"], inputs["out"], inputs["expected"])
