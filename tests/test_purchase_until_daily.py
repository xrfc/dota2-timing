import importlib.util
import json
from pathlib import Path

import httpx
import pytest


def module(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "daily_cli", scripts / "collect_purchase_until_daily.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def budget(tmp_path, monkeypatch, **state):
    m = module(monkeypatch)
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({"requests": [], "blocked_until": 0, **state}))
    now = [100000.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    b = m.MinuteWaitBudget(path, clock=lambda: now[0], sleep=sleep)
    return m, b, now, sleeps


def request():
    return httpx.Request("GET", "https://api.opendota.com/api/matches/123")


def test_minute_wait_then_reserve(tmp_path, monkeypatch):
    _, b, _, sleeps = budget(
        tmp_path, monkeypatch, blocked_until=100065, remaining={"minute": 5, "day": 1000}
    )
    b.before(request())
    assert sleeps == [30, 30, 5]
    assert b.sent == 1
    assert json.loads(b.path.read_text())["requests"] == [100065]


@pytest.mark.parametrize(
    "state",
    [
        {"remaining": {"day": 20}},
        {"last_status": 429},
        {"requests": [99999] * 1900},
        {"blocked_until": 100500, "remaining": {"minute": 5}},
    ],
)
def test_daily_stop_without_request_or_wait(tmp_path, monkeypatch, state):
    m, b, _, sleeps = budget(tmp_path, monkeypatch, **state)
    before = b.path.read_bytes()
    with pytest.raises(m.DailyFinished):
        b.before(request())
    assert b.sent == 0 and not sleeps
    assert b.path.read_bytes() == before


def test_fixed_allowance_does_not_refill_as_old_requests_expire(tmp_path, monkeypatch):
    m, b, now, _ = budget(tmp_path, monkeypatch, requests=[13601] * 1899)
    assert b.allowance == 1
    now[0] += 10
    b.before(request())
    with pytest.raises(m.DailyFinished):
        b.before(request())
    assert b.sent == 1


def test_response_429_persists_stop(tmp_path, monkeypatch):
    m, b, _, _ = budget(tmp_path, monkeypatch)
    b.before(request())
    with pytest.raises(m.BudgetPaused):
        b.after(httpx.Response(429, request=request()))
    assert json.loads(b.path.read_text())["last_status"] == 429
    with pytest.raises(m.DailyFinished):
        b.before(request())


def test_resume_only_unsent_and_reject_tampering(tmp_path, monkeypatch):
    m = module(monkeypatch)
    (tmp_path / "matches").mkdir()
    m.save(tmp_path / "exclusions.json", {"match_ids": []})
    m.save(
        tmp_path / "protocol.json",
        {
            "route": "proxy",
            "training_allowed": False,
            "exclusions_sha256": m.file_hash(tmp_path / "exclusions.json"),
        },
    )
    m.save(
        tmp_path / "plan.json",
        {
            "match_ids": [4, 3, 2, 1],
            "protocol_sha256": m.file_hash(tmp_path / "protocol.json"),
        },
    )
    m.save(tmp_path / "matches/4.json", {"match_id": 4})
    m.save(
        tmp_path / "matches/4.manifest.json",
        {
            "match_id": 4,
            "sha256": m.file_hash(tmp_path / "matches/4.json"),
        },
    )
    m.save(
        tmp_path / "results.json",
        {
            "rows": [
                {"match_id": 3, "request_reserved": True},
                {"match_id": 2, "request_reserved": False},
            ]
        },
    )
    assert m.resume_plan(tmp_path)[1:] == ([2, 1], 1)
    (tmp_path / "matches/4.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        m.resume_plan(tmp_path)


def test_run_resumes_then_stops_at_empty_window(tmp_path, monkeypatch):
    m = module(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    previous = tmp_path / "previous"
    previous.mkdir()
    m.save(previous / "protocol.json", {})
    route = tmp_path / "data/purchase-proxy-trial-2026-10-15"
    route.mkdir(parents=True)
    m.save(route / "request-budget.json", {"requests": [], "blocked_until": 0})
    protocol = {"window": {"patch": "test"}, "start_time_min": 10, "start_time_max_exclusive": 20}
    monkeypatch.setattr(m, "resume_plan", lambda p: (protocol, [3], 3))
    monkeypatch.setattr(m, "load_patch_window", lambda *a: protocol["window"])
    monkeypatch.setattr(m, "history", lambda p: ([3], {}))
    monkeypatch.setattr(m, "inspect_match", lambda *a: {"screened": False, "match_id": 3})
    calls = []

    def respond(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/3"):
            return httpx.Response(200, json={"match_id": 3, "start_time": 15})
        return httpx.Response(200, json={"rows": []})

    original = httpx.Client

    def client(**kwargs):
        kwargs.pop("proxy")
        return original(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(m.httpx, "Client", client)
    out = tmp_path / "out"
    assert m.run(previous, out) == "window_exhausted"
    assert calls == ["/api/matches/3", "/api/explorer"]
    assert m.load(out / "summary.json")["saved"] == 1
    assert m.load(out / "summary.json")["training_allowed"] is False
    with pytest.raises(ValueError, match="New output"):
        m.run(previous, out)


def daily_fixture(tmp_path, monkeypatch):
    m = module(monkeypatch)
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "matches").mkdir()
    m.save(parent / "exclusions.json", {})
    m.save(
        parent / "protocol.json",
        {
            "route": "proxy",
            "training_allowed": False,
            "exclusions_sha256": m.file_hash(parent / "exclusions.json"),
            "window": {"patch": "test"},
            "start_time_min": 10,
            "start_time_max_exclusive": 20,
        },
    )
    m.save(
        parent / "plan.json",
        {"match_ids": [5, 4], "protocol_sha256": m.file_hash(parent / "protocol.json")},
    )
    m.save(parent / "results.json", {"rows": []})
    previous = tmp_path / "daily"
    previous.mkdir()
    (previous / "matches").mkdir()
    (previous / "batch-0000").mkdir()
    protocol = {
        **m.load(parent / "protocol.json"),
        "schema_version": "daily-purchase-continuation/1",
        "previous": str(parent),
        "previous_protocol_sha256": m.file_hash(parent / "protocol.json"),
        "initial_cursor": 4,
        "initial_remaining_plan": [5, 4],
        "historical_plan_sha256": {},
        "historical_exclusions": [5, 4],
    }
    m.save(previous / "protocol.json", protocol)
    m.save(previous / "batch-0000/plan.json", {"match_ids": [5, 4]})
    m.save(previous / "matches/5.json", {"match_id": 5})
    m.save(
        previous / "matches/5.manifest.json",
        {"match_id": 5, "status": 200, "sha256": m.file_hash(previous / "matches/5.json")},
    )
    m.save(previous / "summary.json", {"state": "failed", "saved": 1})
    m.save(previous / "results.json", {"rows": [{"match_id": 4, "request_reserved": True}]})
    return m, previous


def test_daily_resume_retries_response_missing_not_saved(tmp_path, monkeypatch):
    m, previous = daily_fixture(tmp_path, monkeypatch)
    protocol, pending, cursor = m.resume_plan(previous)
    assert pending == [4] and cursor == 4
    assert protocol["patch_receipt_path"] == str(tmp_path / "parent/patch-receipt.json")
    (previous / "batch-0001").mkdir()
    assert m.resume_plan(previous)[1:] == ([4], 4)


@pytest.mark.parametrize("target", ["plan", "cache", "parent", "count", "terminal"])
def test_daily_resume_rejects_damaged_chain(tmp_path, monkeypatch, target):
    m, previous = daily_fixture(tmp_path, monkeypatch)
    if target == "plan":
        (previous / "batch-0000/plan.json").write_text('{"match_ids": [4]}')
    elif target == "cache":
        (previous / "matches/5.json").write_text("{}")
    elif target == "parent":
        (tmp_path / "parent/protocol.json").write_text("{}")
    else:
        (previous / "summary.json").write_text(
            json.dumps(
                {
                    "saved": 2 if target == "count" else 1,
                    "state": "failed" if target == "count" else "stopped_daily_limit",
                }
            )
        )
    with pytest.raises(ValueError):
        m.resume_plan(previous)
