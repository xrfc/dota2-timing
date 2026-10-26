"""Prospective collector contracts tested offline with isolated fake budgets."""

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    m = importlib.import_module("collect_evaluation_cohort")
    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps(dict(requests=[], blocked_until=0)))
    monkeypatch.setattr(m, "BUDGET", budget)
    monkeypatch.setattr(m, "MODELS", {})
    monkeypatch.setattr(m, "SOURCES", ())
    monkeypatch.setattr(m, "AUDIT", None)
    root = tmp_path / "cohort"
    m.freeze(root, data=tmp_path / "empty", now=datetime(2026, 10, 23, 5, tzinfo=UTC))
    p = m.load(root / "protocol.json")
    p.update(target_n=2, max_http_per_run=20)
    rewrite(root, p, m)
    stamp = [p["planned_upper_exclusive"] + 2 * 86400]

    def clock():
        return stamp[0]

    def sleep(seconds):
        stamp[0] += seconds

    return m, root, p, budget, clock, sleep


def rewrite(root, p, m):
    (root / "protocol.json").write_text(json.dumps(p))
    (root / "freeze.json").write_text(
        json.dumps(
            dict(
                sha256={
                    name: m.file_hash(root / name) for name in ("protocol.json", "exclusions.json")
                }
            )
        )
    )


def row(p, mid):
    # IDs deliberately not ordered by time: membership must be time-ordered.
    return dict(
        match_id=mid,
        start_time=p["start_time_min"] + (3 - mid) * 4000,
        duration=2000,
        avg_rank_tier=75,
        num_rank_tier=8,
        lobby_type=7,
        game_mode=22,
    )


def detail(p, mid):
    r = row(p, mid)
    return dict(
        r,
        patch=60,
        players=[
            dict(player_slot=slot, hero_id=hero, purchase_log=[{"time": -10, "key": "bfury"}])
            for slot, hero in zip(
                [0, 1, 2, 3, 4, 128, 129, 130, 131, 132],
                [8, 1, 2, 3, 4, 5, 6, 7, 9, 10],
                strict=True,
            )
        ],
    )


def handler_for(p, calls, *, fault=None):
    def handler(request):
        calls.append(request)
        if request.url.host == "www.dota2.com":
            patches = [{"patch_number": "7.41f", "patch_timestamp": p["start_time_min"] - 86400}]
            if fault == "patch_before":
                patches.append({"patch_number": "7.42", "patch_timestamp": p["start_time_min"] - 1})
            if fault == "patch_drift" and len(calls) > 1:
                patches.append(
                    {"patch_number": "7.42", "patch_timestamp": p["start_time_min"] + 86400}
                )
            return httpx.Response(200, json={"patches": patches})
        if request.url.path.endswith("explorer"):
            if fault in ("400", "429"):
                return httpx.Response(int(fault), json={"err": "Query read timeout"})
            if fault == "disconnect":
                raise httpx.ReadError("offline disconnection", request=request)
            sql = request.url.params["sql"]
            rows = [] if "match_id<1 " in sql else [row(p, 2), row(p, 1)]
            if fault == "duplicate" and rows:
                rows = [row(p, 2), row(p, 2)]
            if fault == "scope" and rows:
                rows[0]["start_time"] = p["start_time_min"] - 1
            if fault == "order" and rows:
                rows.reverse()
            return httpx.Response(200, json={"rows": rows})
        mid = int(request.url.path.rsplit("/", 1)[1])
        raw = detail(p, mid)
        if fault == "identity":
            raw["match_id"] = 999
        if fault == "time":
            raw["start_time"] += 1
        if fault == "numeric_patch":
            raw["patch"] = 61
        if fault == "missing_log":
            raw["players"][0].pop("purchase_log")
        return httpx.Response(200, json=raw)

    return handler


def execute(setup, calls, fault=None):
    m, root, p, _, clock, sleep = setup
    return m.run(
        root,
        transport=httpx.MockTransport(handler_for(p, calls, fault=fault)),
        clock=clock,
        sleep=sleep,
    )


def test_future_gate_never_touches_network_or_budget(setup):
    m, root, p, budget, _, sleep = setup
    before = budget.read_bytes()
    result = m.run(
        root,
        clock=lambda: p["start_time_min"] - 1,
        sleep=sleep,
        transport=httpx.MockTransport(lambda r: pytest.fail("Network forbidden")),
    )
    assert result["state"] == "waiting_window"
    assert budget.read_bytes() == before
    assert list((root / "batches").iterdir()) == []


def test_success_orders_by_time_and_has_no_labels(setup):
    m, root, p, budget, _, _ = setup
    calls = []
    result = execute(setup, calls)
    assert result["state"] == "target_reached"
    assert result["screened_count"] == 2
    assert result["batch_patch_verified"]
    assert [r["match_id"] for r in result["results"]] == [2, 1]
    assert all("observations" not in r for r in result["results"])
    assert not result["training_allowed"] and not result["inference_allowed"]
    assert not result["formal_split_assigned"]
    assert result["http_requests"] == len(calls) == 6
    assert len(m.load(budget)["requests"]) == 4  # Two official calls counted only in total.
    assert m.verify(root)[1] == result
    again = execute(setup, calls)
    assert again == result and len(calls) == 6


@pytest.mark.parametrize(
    "fault",
    [
        "400",
        "429",
        "disconnect",
        "duplicate",
        "scope",
        "order",
        "identity",
        "time",
        "numeric_patch",
        "patch_before",
        "patch_drift",
    ],
)
def test_failure_stops_without_retries_and_keeps_receipts(setup, fault):
    m, root, _, _, _, _ = setup
    calls = []
    result = execute(setup, calls, fault)
    assert result["state"] == "blocked_review"
    assert result["http_requests"] == len(calls)
    batch = root / "batches/batch-0001"
    assert len(list(batch.glob("request-*.json"))) == len(calls)
    if fault in ("400", "429"):
        assert m.load(batch / "receipt-0002.json")["status"] == int(fault)
        assert m.load(batch / "response-0002.json")["err"] == "Query read timeout"
    if fault == "disconnect":
        assert not (batch / "receipt-0002.json").exists()
    old_count = len(calls)
    assert execute(setup, calls)["state"] == "blocked_review"
    assert len(calls) == old_count
    m.verify(root)


def test_missing_logs_not_negative_or_admitted(setup):
    calls = []
    result = execute(setup, calls, "missing_log")
    assert result["state"] == "candidates_exhausted"
    assert result["screened_count"] == 0
    assert all("purchase_log_missing" in r["reasons"] for r in result["results"])


def test_resume_across_batches_accumulates_budget_without_refetch(setup):
    m, root, p, budget, clock, sleep = setup
    p["max_http_per_run"] = 4
    rewrite(root, p, m)
    calls = []
    # one patch + two discovery pages + final patch, no detail yet
    first = execute(setup, calls)
    assert first["state"] == "paused_run" and first["phase"] == "details"
    assert first["http_requests"] == 4 and first["screened_count"] == 0
    second = execute(setup, calls)
    assert second["state"] == "target_reached" and second["http_requests"] == 8
    assert len(calls) == 8
    details = [r.url.path for r in calls if "/api/matches/" in r.url.path]
    assert details == ["/api/matches/2", "/api/matches/1"]
    assert m.verify(root)[2] == 2


@pytest.mark.parametrize(
    "cap,limit,expected",
    [
        ("max_http_requests", 4, "stopped_total_budget"),
        ("max_non_detail_requests", 4, "stopped_discovery_budget"),
    ],
)
def test_budget_ceiling_reserves_closing_patch(setup, cap, limit, expected):
    m, root, p, _, _, _ = setup
    p[cap] = limit
    rewrite(root, p, m)
    calls = []
    result = execute(setup, calls)
    assert result["state"] == expected
    assert result["http_requests"] == len(calls) == limit
    assert result["batch_patch_verified"] and result["screened_count"] == 0


def test_tampered_protocol_and_unsealed_batch_block_network(setup):
    m, root, p, _, _, _ = setup
    (root / "protocol.json").write_text("{}")
    with pytest.raises(ValueError, match="Evidence changed"):
        execute(setup, [])
    rewrite(root, p, m)
    (root / "batches/batch-0001").mkdir()
    with pytest.raises(FileNotFoundError):
        execute(setup, [])


def test_response_tampering_blocks_resume(setup):
    m, root, _, _, _, _ = setup
    execute(setup, [])
    (root / "batches/batch-0001/response-0001.json").write_text("{}")
    with pytest.raises(ValueError, match="Evidence changed"):
        execute(setup, [])


def test_daily_cooldown_preserved_without_request(setup):
    m, root, p, budget, clock, _ = setup
    before = dict(
        requests=[clock() - 20],
        blocked_until=clock() + 86400,
        remaining={"day": 20},
        last_status=200,
    )
    budget.write_text(json.dumps(before))
    calls = []
    result = execute(setup, calls)
    assert result["state"] == "paused_budget" and not calls
    assert m.load(budget) == before
    assert m.verify(root)[1]["http_requests"] == 0


def test_deadline_no_network(setup):
    m, root, p, budget, _, sleep = setup
    before = budget.read_bytes()
    result = m.run(
        root,
        clock=lambda: p["deadline"],
        sleep=sleep,
        transport=httpx.MockTransport(lambda r: pytest.fail("No HTTP")),
    )
    assert result["state"] == "stopped_deadline" and budget.read_bytes() == before


def test_freeze_rejects_overwrite_and_shifted_approval(setup, tmp_path):
    m, root, _, _, _, _ = setup
    with pytest.raises(ValueError, match="New output"):
        m.freeze(root, now=datetime(2026, 10, 23, tzinfo=UTC))
    with pytest.raises(ValueError, match="Approval dates expired"):
        m.freeze(tmp_path / "late", now=datetime(2026, 10, 24, tzinfo=UTC))


def test_midrun_daily_limit_can_resume_without_refetch(setup):
    m, root, p, budget, clock, sleep = setup
    calls = []
    base = handler_for(p, calls)

    def handler(request):
        response = base(request)
        if request.url.path.endswith("/2"):
            response.headers["X-Rate-Limit-Remaining-Day"] = "20"
        return response

    first = m.run(root, transport=httpx.MockTransport(handler), clock=clock, sleep=sleep)
    assert first["state"] == "paused_budget"
    assert first["batch_patch_verified"] and first["screened_count"] == 1
    old_requests = m.load(budget)["requests"]
    sleep(86401)  # fake clock, not wall-clock waiting
    second = execute(setup, calls)
    assert second["state"] == "target_reached"
    assert [r.url.path for r in calls if "/api/matches/" in r.url.path] == [
        "/api/matches/2",
        "/api/matches/1",
    ]
    assert len(old_requests) == 3
    m.verify(root)


def test_minute_cooldown_waits_without_repeating_request(setup):
    m, root, p, _, clock, sleep = setup
    calls, waits = [], []
    base = handler_for(p, calls)

    def handler(request):
        response = base(request)
        if request.url.path.endswith("/2"):
            response.headers["X-Rate-Limit-Remaining-Minute"] = "5"
        return response

    def tracked_sleep(seconds):
        waits.append(seconds)
        sleep(seconds)

    result = m.run(root, transport=httpx.MockTransport(handler), clock=clock, sleep=tracked_sleep)
    assert result["state"] == "target_reached"
    assert 60 in waits and all(0 <= seconds <= 60 for seconds in waits)
    assert len(calls) == 6


def test_model_or_source_drift_blocks_before_network(setup, tmp_path):
    m, root, p, _, _, _ = setup
    source = tmp_path / "producer.py"
    source.write_text("old")
    p["implementation_sha256"] = {str(source): m.file_hash(source)}
    rewrite(root, p, m)
    source.write_text("changed")
    with pytest.raises(ValueError, match="Frozen implementation/model changed"):
        execute(setup, [])


def test_midrun_source_drift_is_not_published_as_success(setup, tmp_path):
    m, root, p, _, clock, sleep = setup
    source = tmp_path / "producer.py"
    source.write_text("old")
    p["implementation_sha256"] = {str(source): m.file_hash(source)}
    rewrite(root, p, m)
    calls = []
    base = handler_for(p, calls)

    def handler(request):
        response = base(request)
        if request.url.path.endswith("/1"):
            source.write_text("changed")
        return response

    result = m.run(root, transport=httpx.MockTransport(handler), clock=clock, sleep=sleep)
    assert result["state"] == "blocked_review"
    assert not result["batch_patch_verified"]


def test_history_exclusion_is_retained_not_replaced(setup):
    m, root, p, _, _, _ = setup
    (root / "exclusions.json").write_text(
        json.dumps(dict(match_ids=[2], historical_plan_sha256={}))
    )
    rewrite(root, p, m)
    calls = []
    result = execute(setup, calls)
    assert result["state"] == "candidates_exhausted" and result["screened_count"] == 1
    assert result["results"][0]["reasons"] == ["historical_id"]
    assert [r.url.path for r in calls if "/api/matches/" in r.url.path] == ["/api/matches/1"]


def test_freeze_binds_audit_and_rejects_old_input_drift(setup, monkeypatch, tmp_path):
    m, _, _, _, _, _ = setup
    audited = tmp_path / "audited-input.json"
    audited.write_text("{}")
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            dict(
                old_source_count=1990,
                old_end_max_utc="2026-10-13T08:59:46+00:00",
                inputs={str(audited): m.file_hash(audited)},
            )
        )
    )
    (tmp_path / "complete.json").write_text(json.dumps(dict(audit_sha256=m.file_hash(audit))))
    design = tmp_path / "design.md"
    design.write_text("approved design")
    monkeypatch.setattr(m, "AUDIT", audit)
    monkeypatch.setattr(m, "DESIGN", design)
    frozen = tmp_path / "bound"
    m.freeze(frozen, data=tmp_path / "empty", now=datetime(2026, 10, 23, tzinfo=UTC))
    assert (frozen / "prior-audit.json").read_bytes() == audit.read_bytes()
    assert m.verify(frozen)[0]["approved_design_sha256"] == m.file_hash(design)
    audited.write_text("changed")
    with pytest.raises(ValueError, match="Audited input changed"):
        m.freeze(tmp_path / "bad", data=tmp_path / "empty", now=datetime(2026, 10, 23, tzinfo=UTC))
    assert not (tmp_path / "bad").exists()
