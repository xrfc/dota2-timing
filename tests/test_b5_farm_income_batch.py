"""B5 collection keeps the frozen population and distinguishes missing gold from zero."""

import importlib.util
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from dota_items.sources import gem_farm_income as farm


@pytest.fixture(scope="module")
def batch():
    path = Path(__file__).resolve().parents[1] / "scripts/collect_b5_farm_income.py"
    spec = importlib.util.spec_from_file_location("farm_income_batch_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case(t=100, action="unknown", match=123):
    return dict(match=match, hero="hero", t=t, fold=0, action=action)


def boundary(t, creep=100, neutral=50, status="observed"):
    return dict(hero="hero", t=t, creep=creep, neutral=neutral, status=status)


def captured(boundaries=None, events=()):
    return dict(
        match_id=123,
        boundaries=boundaries
        if boundaries is not None
        else [boundary(100), boundary(120), boundary(130)],
        events=list(events),
    )


def event(t, value, kind="creep"):
    return dict(hero="hero", kind=kind, t=t, value=value)


def test_event_windows_include_start_and_exclude_each_end(batch):
    data = captured(
        [boundary(100), boundary(120, 130), boundary(130, 200, 60)],
        [
            event(99, 999),
            event(100, 10),
            event(119, 20),
            event(120, 30),
            event(129, 40),
            event(130, 999),
            event(120, 10, "neutral"),
        ],
    )
    row = batch.score_windows([case()], data, 130)[0]
    assert row["action"] == "unknown"
    assert row["windows"]["20"] == dict(
        status="complete",
        creep=dict(counter=30, event=30, difference=0),
        neutral=dict(counter=0, event=0, difference=0),
    )
    assert row["windows"]["30"] == dict(
        status="complete",
        creep=dict(counter=100, event=100, difference=0),
        neutral=dict(counter=10, event=10, difference=0),
    )


def test_observed_zero_and_missing_counter_are_different(batch):
    data = captured([boundary(100), boundary(120), boundary(130, None)])
    row = batch.score_windows([case()], data, 130)[0]
    assert row["windows"]["20"]["creep"] == dict(counter=0, event=0, difference=0)
    assert row["windows"]["30"]["status"] == "missing_counter"
    assert row["windows"]["30"]["creep"] == dict(counter=None, event=0, difference=None)
    assert row["windows"]["30"]["neutral"] == dict(counter=0, event=0, difference=0)


@pytest.mark.parametrize("explicit", [False, True])
def test_missing_endpoint_does_not_become_zero(batch, explicit):
    bounds = [boundary(100), boundary(120)]
    if explicit:
        bounds.append(boundary(130, None, None, "missing_endpoint"))
    row = batch.score_windows([case()], captured(bounds), 130)[0]
    assert row["windows"]["30"]["status"] == "missing_endpoint"
    assert row["windows"]["30"]["creep"] == dict(counter=None, event=0, difference=None)


def test_actual_match_duration_overrides_late_parser_endpoints(batch):
    row = batch.score_windows([case()], captured(), 129)[0]
    assert row["windows"]["20"]["status"] == "complete"
    assert row["windows"]["30"]["status"] == "truncated"
    for kind in ("creep", "neutral"):
        assert row["windows"]["30"][kind] == dict(counter=None, event=None, difference=None)


def test_unknown_actions_and_counter_event_disagreement_are_retained(batch):
    data = captured([boundary(100), boundary(120, 105), boundary(130, 105)], [event(110, 3)])
    rows = batch.score_windows([case(action="unknown")], data, 130)
    assert len(rows) == 1 and rows[0]["action"] == "unknown"
    assert rows[0]["windows"]["20"]["creep"] == dict(counter=5, event=3, difference=2)


@pytest.mark.parametrize(
    ("bounds", "message"),
    [
        ([boundary(100), boundary(100)], "duplicate gold endpoint"),
        ([boundary(100), boundary(120, 99)], "decreasing cumulative farm gold"),
    ],
)
def test_invalid_endpoints_are_rejected(batch, bounds, message):
    with pytest.raises(ValueError, match=message):
        batch.score_windows([case()], captured(bounds), 130)


@pytest.fixture
def frozen_plan(batch, monkeypatch):
    # Synthetic values with the real frozen population cardinality, independent of local reports.
    matches = [
        dict(
            match=mid,
            patch=60,
            cases=[case(t=t, match=mid) for t in range(13 if mid <= 977 else 12)],
        )
        for mid in range(1, 1170)
    ]
    plan = dict(
        schema="b5-farm-plan/1",
        rows_sha256=batch.ROWS_SHA,
        routes_sha256=batch.ROUTES_SHA,
        matches=matches,
    )
    rows = sorted((r for m in matches for r in m["cases"]), key=batch.key)
    assert len(matches) == 1169 and len(rows) == 15005
    monkeypatch.setattr(batch, "POPULATION_SHA", batch.digest(rows))
    monkeypatch.setattr(batch, "is_holdout", lambda _: False)
    return plan


def test_frozen_population_accepts_exactly_bound_cases(batch, frozen_plan):
    batch.validate_plan(frozen_plan)


@pytest.mark.parametrize(
    ("field", "value"), [("hero", "other"), ("t", 999), ("fold", 1), ("action", "farm")]
)
def test_same_size_population_changes_are_rejected(batch, frozen_plan, field, value):
    frozen_plan["matches"][0]["cases"][0][field] = value
    with pytest.raises(ValueError, match="changed frozen identities, actions or folds"):
        batch.validate_plan(frozen_plan)


def test_incomplete_population_is_rejected(batch, frozen_plan):
    frozen_plan["matches"].pop()
    with pytest.raises(ValueError, match="incomplete frozen development plan"):
        batch.validate_plan(frozen_plan)


def test_reserved_match_is_rejected_even_with_bound_population(batch, frozen_plan, monkeypatch):
    monkeypatch.setattr(batch, "is_holdout", lambda mid: mid == 1)
    with pytest.raises(ValueError, match="reserved match"):
        batch.validate_plan(frozen_plan)


def record(batch, match, bound):
    result = dict(binding=deepcopy(bound), source=deepcopy(match), capture=captured(), rows=[])
    result["payload_sha256"] = batch.digest(result)
    return result


def test_saved_result_rejects_corruption_and_changed_binding(batch):
    bound, match = {"plan": "original"}, {"match": 123}
    result = record(batch, match, bound)
    batch.verify_result(result, match, bound)
    result["rows"].append({"counter": 42})
    with pytest.raises(ValueError, match="checksum mismatch"):
        batch.verify_result(result, match, bound)
    result["payload_sha256"] = batch.digest(
        {k: v for k, v in result.items() if k != "payload_sha256"}
    )
    with pytest.raises(ValueError, match="source/implementation mismatch"):
        batch.verify_result(result, match, {"plan": "changed"})
    with pytest.raises(ValueError, match="source/implementation mismatch"):
        batch.verify_result(result, {"match": 456}, bound)


@pytest.mark.parametrize("mode", ["manifest", "unbound", "locked"])
def test_run_refuses_foreign_output_or_existing_writer(batch, tmp_path, monkeypatch, mode):
    monkeypatch.setattr(batch, "validate_plan", lambda _: None)
    monkeypatch.setattr(batch, "binding", lambda _: {"plan": "current"})
    calls = []
    monkeypatch.setattr(batch, "execute_match", lambda *args: calls.append(args))
    if mode == "manifest":
        batch.write_json(tmp_path / "manifest.json", {"plan": "other"})
        message = "different inputs/implementation"
    elif mode == "unbound":
        batch.write_json(tmp_path / "123.json", {})
        message = "unbound previous results"
    else:
        (tmp_path / ".writer.lock").write_text("existing writer")
        message = "writer is busy"
    with pytest.raises(ValueError, match=message):
        batch.run({"matches": [{"match": 123}]}, tmp_path, tmp_path, None, None)
    assert not calls
    assert (tmp_path / ".writer.lock").exists() == (mode == "locked")


@pytest.fixture
def execution(batch, tmp_path, monkeypatch):
    data, output = tmp_path / "data", tmp_path / "output"
    output.mkdir()
    demo = data / "demos" / "123.dem.bz2"
    demo.parent.mkdir(parents=True)
    demo.write_bytes(b"fixture replay bytes")
    receipt = data / "receipts" / "123.json"
    meta = data / "meta" / "123.json"
    batch.write_json(receipt, dict(match_id=123, demo_sha256=batch.file_hash(demo)))
    batch.write_json(meta, dict(match_id=123, patch=60, duration=130))
    match = dict(
        match=123,
        patch=60,
        duration=130,
        cases=[case()],
        demo_sha256=batch.file_hash(demo),
        receipt_sha256=batch.file_hash(receipt),
        meta_sha256=batch.file_hash(meta),
    )
    bound = dict(implementation_sha256={"producer": "stable"})
    monkeypatch.setattr(batch, "implementation_hashes", lambda: bound["implementation_sha256"])
    monkeypatch.setitem(
        sys.modules, "gem", SimpleNamespace(__file__="/tmp/fixture-gem/__init__.py")
    )
    compatibility_checks = []
    monkeypatch.setattr(
        farm, "verify_compatibility", lambda root: compatibility_checks.append(root)
    )

    @contextmanager
    def prepare(source, scratch):
        yield source

    monkeypatch.setattr(batch, "prepared_demo", prepare)
    monkeypatch.setattr(farm, "capture_farm_income", lambda *args: captured())
    return match, data, output, bound, compatibility_checks


def test_resume_checks_sources_and_compatibility_without_reparsing(batch, execution, monkeypatch):
    match, data, output, bound, checks = execution
    batch.write_json(output / "123.json", record(batch, match, bound))
    monkeypatch.setattr(
        farm, "capture_farm_income", lambda *args: pytest.fail("resume must not parse")
    )
    assert batch.execute_match(match, data, output, bound) == "reused"
    assert len(checks) == 2
    (data / "demos" / "123.dem.bz2").write_bytes(b"changed source")
    with pytest.raises(ValueError, match="raw replay hash mismatch"):
        batch.execute_match(match, data, output, bound)


def test_runtime_change_blocks_resume(batch, execution, monkeypatch):
    match, data, output, bound, _ = execution
    batch.write_json(output / "123.json", record(batch, match, bound))

    def invalid_runtime(root):
        raise ValueError("runtime changed")

    monkeypatch.setattr(farm, "verify_compatibility", invalid_runtime)
    with pytest.raises(ValueError, match="runtime changed"):
        batch.execute_match(match, data, output, bound)


def test_source_change_during_capture_cannot_publish_result(batch, execution, monkeypatch):
    match, data, output, bound, _ = execution
    hashes = iter([bound["implementation_sha256"], {"producer": "changed"}])
    monkeypatch.setattr(batch, "implementation_hashes", lambda: next(hashes))
    with pytest.raises(ValueError, match="implementation changed during extraction"):
        batch.execute_match(match, data, output, bound)
    assert not (output / "123.json").exists()


def test_replay_bytes_changed_during_capture_cannot_publish_result(batch, execution, monkeypatch):
    match, data, output, bound, _ = execution

    def capture_changed_replay(raw, cases):
        (data / "demos" / "123.dem.bz2").write_bytes(b"changed replay with the same match ID")
        return captured()

    monkeypatch.setattr(farm, "capture_farm_income", capture_changed_replay)
    with pytest.raises(ValueError, match="raw replay changed during extraction"):
        batch.execute_match(match, data, output, bound)
    assert not (output / "123.json").exists()
