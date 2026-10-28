import importlib.util
import json
import time
from pathlib import Path

import httpx
import pytest

from dota_items.data.contracts import SLOTS
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget


def module():
    path = Path(__file__).resolve().parents[1] / "scripts/collect_purchase_latest.py"
    spec = importlib.util.spec_from_file_location("latest_cli", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def match(mid=100):
    now = int(time.time())
    return {
        "match_id": mid,
        "start_time": now - 7200,
        "duration": 1800,
        "lobby_type": 7,
        "game_mode": 22,
        "patch": 1,
        "players": [
            {
                "player_slot": slot,
                "hero_id": i + 1,
                "purchase_log": [{"key": "bfury", "time": 1200}],
            }
            for i, slot in enumerate(sorted(SLOTS))
        ],
    }


def test_offline_mock_collection_freezes_plan_before_details(tmp_path, monkeypatch):
    m = module()
    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    (data / "plan.json").write_text(json.dumps({"match_ids": [99]}))
    output = tmp_path / "output"
    calls = []
    now = [time.time()]
    monkeypatch.setattr(
        m,
        "RequestBudget",
        lambda p: RequestBudget(
            p, clock=lambda: now[0], sleep=lambda t: now.__setitem__(0, now[0] + t)
        ),
    )

    def handler(request):
        calls.append(request.url.path)
        if request.url.host == "www.dota2.com":
            return httpx.Response(
                200,
                json={
                    "patches": [
                        {"patch_number": "test", "patch_timestamp": int(time.time()) - 86400}
                    ]
                },
            )
        if request.url.path == "/api/explorer":
            rows = (
                [{"match_id": 100, "start_time": int(time.time()) - 7200}]
                if calls.count("/api/explorer") == 1
                else []
            )
            return httpx.Response(200, json={"rows": rows})
        assert (output / "plan.json").is_file()
        return httpx.Response(200, json=match())

    assert (
        m.collect(output, data, tmp_path / "budget.json", transport=httpx.MockTransport(handler))
        == "completed"
    )
    result = json.loads((output / "results.json").read_text())
    assert result["screened"] == 1 and result["training_allowed"] is False
    assert result["requests"] == {"all": 3, "detail": 1, "discovery": 2}
    assert json.loads((output / "exclusions.json").read_text())["match_ids"] == [99]
    with pytest.raises(ValueError, match="New output"):
        m.collect(output, data, tmp_path / "budget.json")


def test_history_covers_all_plans_deleted_and_failed_ids(tmp_path):
    m = module()
    for n, mid in (("a", 1), ("b", 2)):
        (tmp_path / n).mkdir()
        (tmp_path / n / "plan.json").write_text(json.dumps({"match_ids": [mid]}))
    (tmp_path / "3.manifest.json").write_text("{}")
    (tmp_path / "failure-4.json").write_text("{}")
    assert m.history(tmp_path)[0] == [1, 2, 3, 4]


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_service_failure_is_recorded_and_stops_before_next_match(tmp_path, monkeypatch, status):
    m = module()
    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    output = tmp_path / "output"
    calls = []
    clock = [time.time()]
    monkeypatch.setattr(
        m,
        "RequestBudget",
        lambda p: RequestBudget(
            p, clock=lambda: clock[0], sleep=lambda t: clock.__setitem__(0, clock[0] + t)
        ),
    )

    def handler(request):
        calls.append(request.url.path)
        if request.url.host == "www.dota2.com":
            return httpx.Response(
                200,
                json={
                    "patches": [
                        {"patch_number": "test", "patch_timestamp": int(time.time()) - 86400}
                    ]
                },
            )
        if request.url.path == "/api/explorer":
            rows = (
                [{"match_id": mid, "start_time": int(time.time()) - 7200} for mid in (101, 100)]
                if calls.count("/api/explorer") == 1
                else []
            )
            return httpx.Response(200, json={"rows": rows})
        assert request.url.path == "/api/matches/101"
        return httpx.Response(status, json={"error": "service unavailable"})

    with pytest.raises(ValueError, match="Service failure"):
        m.collect(output, data, tmp_path / "budget.json", transport=httpx.MockTransport(handler))

    result = json.loads((output / "results.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    assert result["state"] == summary["state"] == "failed"
    assert result["selected"] == 2
    assert result["attempted_results"] == summary["attempted_results"] == 1
    assert result["requests"]["detail"] == 1
    assert result["rows"] == [
        {
            "match_id": 101,
            "screened": False,
            "request_reserved": True,
            "status": status,
            "error_type": "HTTPStatusError",
        }
    ]
    assert calls.count("/api/matches/101") == 1
    assert "/api/matches/100" not in calls
    assert json.loads((output / "matches/101.manifest.json").read_text())["status"] == status
    assert (output / "matches/101.json").is_file()


@pytest.mark.parametrize("kind,limit", [("detail", 200), ("discovery", 5), ("all", 220)])
def test_hard_cap_before_reserving(tmp_path, kind, limit):
    m = module()

    class Persistent:
        def before(self, request):
            pytest.fail("Must stop before reserving or sending")

    budget = m.RunBudget(Persistent(), tmp_path)
    budget.counts[kind] = limit
    endpoint = "explorer" if kind == "discovery" else "matches/1"
    with pytest.raises(BudgetPaused):
        budget.before(httpx.Request("GET", "https://api.opendota.com/api/" + endpoint))


def test_label_missing_never_negative_and_identity_rejected():
    m = module()
    raw = match()
    window = {
        "release_timestamp": int(time.time()) - 86400,
        "upper_exclusive": int(time.time()),
        "upper_kind": "snapshot_retrieval",
        "boundary_buffer_seconds": 3600,
    }
    p = next(p for p in raw["players"] if p["hero_id"] == 8)
    del p["purchase_log"]
    result = m.inspect_match(raw, 100, window)
    assert not result["screened"]
    assert all(
        r["log_presence"] is None and not r["log_presence_mask"] for r in result["observations"]
    )
    with pytest.raises(ValueError):
        m.inspect_match(raw, 101, window)


def test_api_key_rejected_without_io(tmp_path, monkeypatch):
    m = module()
    monkeypatch.setenv("OPENDOTA_API_KEY", "synthetic-not-a-real-key")
    with pytest.raises(ValueError, match="Anonymous"):
        m.collect(tmp_path / "out", tmp_path, tmp_path / "budget")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("mode", ["429", "bad_time"])
def test_discovery_failures_never_fetch_details(tmp_path, monkeypatch, mode):
    m = module()
    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    output = tmp_path / "out"
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.host == "www.dota2.com":
            return httpx.Response(
                200,
                json={
                    "patches": [
                        {"patch_number": "test", "patch_timestamp": int(time.time()) - 86400}
                    ]
                },
            )
        assert request.url.path == "/api/explorer"
        if mode == "429":
            return httpx.Response(429, headers={"Retry-After": "90000"})
        return httpx.Response(200, json={"rows": [{"match_id": 100, "start_time": 1}]})

    if mode == "429":
        assert (
            m.collect(output, data, tmp_path / "budget", transport=httpx.MockTransport(handler))
            == "paused_budget"
        )
        assert json.loads((tmp_path / "budget").read_text())["blocked_until"] > time.time() + 89900
    else:
        with pytest.raises(ValueError, match="time differs"):
            m.collect(output, data, tmp_path / "budget", transport=httpx.MockTransport(handler))
    assert calls.count("/api/explorer") == 1
    assert not (output / "matches").exists()
    assert (output / "summary.json").is_file()
