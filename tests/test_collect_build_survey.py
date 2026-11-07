import importlib.util
import json
import time
from pathlib import Path

import httpx
import pytest

from dota_items.data.contracts import SLOTS
from dota_items.sources.opendota_budget import RequestBudget


def module():
    path = Path(__file__).resolve().parents[1] / "scripts/collect_build_survey.py"
    spec = importlib.util.spec_from_file_location("build_survey_cli", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


NOW = int(time.time())
START = NOW - 3 * 86400


def match(mid, *, parsed=True, duration=1500):
    return {
        "match_id": mid,
        "start_time": START,
        "duration": duration,
        "lobby_type": 7,
        "game_mode": 22,
        "patch": 60,
        "players": [
            {
                "player_slot": slot,
                "hero_id": i + 1,
                **({"purchase_log": [{"key": "bfury", "time": 1200}]} if parsed else {}),
            }
            for i, slot in enumerate(sorted(SLOTS))
        ],
    }


def run(tmp_path, monkeypatch, details, *, rows=(102, 101, 100), heroes=(), max_details=3):
    m = module()
    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    clock = [time.time()]
    monkeypatch.setattr(
        m,
        "RequestBudget",
        lambda p: RequestBudget(
            p, clock=lambda: clock[0], sleep=lambda t: clock.__setitem__(0, clock[0] + t)
        ),
    )
    calls, output = [], tmp_path / "out"

    def handler(request):
        calls.append(request)
        if request.url.host == "www.dota2.com":
            return httpx.Response(
                200, json={"patches": [{"patch_number": "t", "patch_timestamp": NOW - 30 * 86400}]}
            )
        if request.url.path == "/api/explorer":
            if "max(match_id)" in request.url.params["sql"]:
                return httpx.Response(200, json={"rows": [{"max_id": 103 + 52_000 * 24}]})
            first = sum(c.url.path == "/api/explorer" for c in calls) == 2
            body = [{"match_id": mid, "start_time": START, "avg_rank_tier": 72} for mid in rows]
            return httpx.Response(200, json={"rows": body if first else []})
        assert (output / "plan.json").is_file()
        mid = int(request.url.path.rsplit("/", 1)[1])
        return details(mid)

    state = m.collect(
        output,
        tmp_path / "budget.json",
        max_details=max_details,
        heroes=heroes,
        transport=httpx.MockTransport(handler),
    )
    return m, state, output, calls


def test_collects_without_hero_filter_and_counts_parsed(tmp_path, monkeypatch):
    def details(mid):
        return httpx.Response(200, json=match(mid, parsed=mid != 101))

    _, state, out, calls = run(tmp_path, monkeypatch, details)
    assert state == "completed"
    summary = json.loads((out / "summary.json").read_text())
    assert summary["screened"] == 2 and summary["reason_counts"] == {"purchase_log_missing": 1}
    assert summary["screened_hero_games"]["1"] == 2
    assert summary["discovered_avg_rank_tier_bands"] == {"7": 3}
    protocol = json.loads((out / "protocol.json").read_text())
    assert protocol["hero_filter"] == [] and protocol["parse_requests"] is False
    assert protocol["min_avg_rank_tier"] == 60 and protocol["min_duration_s"] == 900
    sql = json.loads((out / "discovery-0-receipt.json").read_text())["sql"]
    assert "ANY(radiant_team)" not in sql and "avg_rank_tier>=60" in sql
    assert "match_id>-999897 AND match_id<103 " in sql
    assert json.loads((out / "discovery-anchor-receipt.json").read_text())["initial_cursor"] == 103
    assert all(c.method == "GET" for c in calls)


def test_hero_top_up_is_recorded_in_query_and_protocol(tmp_path, monkeypatch):
    _, _, out, _ = run(
        tmp_path, monkeypatch, lambda mid: httpx.Response(200, json=match(mid)), heroes=(91,)
    )
    sql = json.loads((out / "discovery-0-receipt.json").read_text())["sql"]
    assert "91=ANY(radiant_team) OR 91=ANY(dire_team)" in sql
    assert json.loads((out / "protocol.json").read_text())["hero_filter"] == [91]


def test_short_games_are_screened_out(tmp_path, monkeypatch):
    _, _, out, _ = run(
        tmp_path,
        monkeypatch,
        lambda mid: httpx.Response(200, json=match(mid, duration=600)),
        rows=(100,),
        max_details=1,
    )
    summary = json.loads((out / "summary.json").read_text())
    assert summary["screened"] == 0 and "duration_not_covered" in summary["reason_counts"]


def test_service_failure_stops_and_identity_conflict_raises(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Service failure"):
        run(tmp_path, monkeypatch, lambda mid: httpx.Response(503, json={}))
    (tmp_path / "b").mkdir()
    with pytest.raises(ValueError, match="identity"):
        run(tmp_path / "b", monkeypatch, lambda mid: httpx.Response(200, json=match(mid + 1)))


def test_refuses_key_reused_output_and_oversized_runs(tmp_path, monkeypatch):
    m = module()
    monkeypatch.setenv("OPENDOTA_API_KEY", "x")
    with pytest.raises(ValueError, match="Anonymous"):
        m.collect(tmp_path / "a", tmp_path / "b.json", max_details=1)
    monkeypatch.delenv("OPENDOTA_API_KEY")
    (tmp_path / "used").mkdir()
    with pytest.raises(ValueError, match="New output"):
        m.collect(tmp_path / "used", tmp_path / "b.json", max_details=1)
    with pytest.raises(ValueError, match="max_details"):
        m.collect(tmp_path / "c", tmp_path / "b.json", max_details=m.MAX_DETAILS + 1)
