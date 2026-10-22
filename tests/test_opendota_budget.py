import httpx
import pytest

from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget


def test_all_requests_and_retries_share_spacing(tmp_path):
    now = [100000.0]

    def sleep(delay):
        now[0] += delay

    b = RequestBudget(tmp_path / "budget.json", clock=lambda: now[0], sleep=sleep)
    for endpoint in ("explorer", "matches/1", "matches/1"):
        b.before(httpx.Request("GET", "https://api.opendota.com/api/" + endpoint))
    assert b.state["requests"] == [100000, 100001.5, 100003]


def test_429_persists_and_prevents_next_request(tmp_path):
    path = tmp_path / "budget.json"
    b = RequestBudget(path, clock=lambda: 100000)
    req = httpx.Request("GET", "https://api.opendota.com/api/explorer")
    with pytest.raises(BudgetPaused):
        b.after(httpx.Response(429, request=req, headers={"Retry-After": "90000"}))
    restored = RequestBudget(path, clock=lambda: 100001)
    assert restored.state["blocked_until"] == 190000
    with pytest.raises(BudgetPaused):
        restored.before(req)
    assert restored.state["requests"] == []


def test_daily_budget_and_server_remaining_stop_before_next_call(tmp_path):
    req = httpx.Request("GET", "https://api.opendota.com/api/matches/1")
    b = RequestBudget(tmp_path / "budget.json", clock=lambda: 100000)
    b.state["requests"] = [99999] * 1900
    with pytest.raises(BudgetPaused):
        b.before(req)
    b.state = {"requests": [], "blocked_until": 0}
    b.after(httpx.Response(200, request=req, headers={"X-Rate-Limit-Remaining-Day": "20"}))
    with pytest.raises(BudgetPaused):
        b.before(req)


def test_minute_headroom(tmp_path):
    req = httpx.Request("GET", "https://api.opendota.com/api/explorer")
    b = RequestBudget(tmp_path / "budget.json", clock=lambda: 100000)
    b.after(httpx.Response(200, request=req, headers={"X-Rate-Limit-Remaining-Minute": "5"}))
    assert b.state["blocked_until"] == 100065
