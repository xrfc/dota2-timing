"""Unattended demo collector (U128, U129): offline, with fake OpenDota, Valve and parser."""

import gzip
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location(
        "collect_demos", ROOT / "scripts/collect_demos.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def meta(mid, **over):
    base = {
        "match_id": mid,
        "start_time": int(time.time()) - 7200,
        "duration": 2000,
        "lobby_type": 7,
        "game_mode": 22,
        "replay_url": f"http://replay1.valve.net/570/{mid}_1.dem.bz2",
        "players": [{"hero_id": h} for h in range(1, 11)],
    }
    return {**base, **over}


def fake_runner(args, **kwargs):
    workspace = Path(args[args.index("--workspace") + 1])
    out = workspace / "cache/matches/abc/normalized.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"players": [], "context": {"channels": {"combat_log": [1, 2]}}}))
    return subprocess.CompletedProcess(args, 0, "", "")


def clients(handler):
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport), httpx.Client(transport=transport)


ARGS = SimpleNamespace(parse_timeout=10, keep_workspace=False)


def test_metadata_checks():
    m = module()
    assert m.check_metadata(meta(1), 1, 0) == []
    assert "too_short" in m.check_metadata(meta(1, duration=600), 1, 0)
    assert "not_ranked_all_pick" in m.check_metadata(meta(1, game_mode=23), 1, 0)
    assert "no_replay_url" in m.check_metadata(meta(1, replay_url="http://evil.example/x"), 1, 0)
    assert "players_incomplete" in m.check_metadata(meta(1, players=[{"hero_id": 1}] * 10), 1, 0)
    with pytest.raises(ValueError):
        m.check_metadata(meta(2), 1, 0)


def test_one_match_keeps_demo_and_compressed_parse_and_removes_work(tmp_path):
    m = module()

    def handler(request):
        if request.url.host == "api.opendota.com":
            return httpx.Response(200, json=meta(5))
        return httpx.Response(200, content=b"demo-bytes")

    api, valve = clients(handler)
    receipt = m.process(
        tmp_path, {"match_id": 5, "avg_rank_tier": 72}, api, valve, 0, ARGS, fake_runner
    )
    assert receipt["status"] == "parsed" and receipt["heroes"] == list(range(1, 11))
    assert (tmp_path / "demos/5.dem.bz2").read_bytes() == b"demo-bytes"
    with gzip.open(tmp_path / "parsed/5.normalized.json.gz") as packed:
        assert json.load(packed)["context"]["channels"]["combat_log"] == [1, 2]
    assert not (tmp_path / "work/5").exists() and receipt["workspace_removed"]


def test_missing_demo_and_bad_metadata_are_skipped_not_errors(tmp_path):
    m = module()

    def handler(request):
        if request.url.host == "api.opendota.com":
            return httpx.Response(200, json=meta(6))
        return httpx.Response(404)

    api, valve = clients(handler)
    receipt = m.process(tmp_path, {"match_id": 6}, api, valve, 0, ARGS, fake_runner)
    assert receipt["status"] == "skipped" and receipt["reasons"] == ["demo_not_found"]

    def short(request):
        return httpx.Response(200, json=meta(7, duration=300))

    api, valve = clients(short)
    receipt = m.process(tmp_path, {"match_id": 7}, api, valve, 0, ARGS, fake_runner)
    assert receipt["reasons"] == ["too_short"] and not (tmp_path / "demos/7.dem.bz2").exists()


def test_resume_reuses_saved_metadata_and_demo(tmp_path):
    m = module()
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta/8.json").write_text(json.dumps(meta(8)))
    (tmp_path / "demos").mkdir()
    (tmp_path / "demos/8.dem.bz2").write_bytes(b"already-here")

    def handler(request):
        raise AssertionError("no network request expected on resume")

    api, valve = clients(handler)
    receipt = m.process(tmp_path, {"match_id": 8}, api, valve, 0, ARGS, fake_runner)
    assert receipt["status"] == "parsed" and receipt["demo_bytes"] == len(b"already-here")


def test_parse_failure_keeps_the_demo(tmp_path):
    m = module()

    def handler(request):
        if request.url.host == "api.opendota.com":
            return httpx.Response(200, json=meta(9))
        return httpx.Response(200, content=b"demo")

    def failing(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "boom")

    api, valve = clients(handler)
    receipt = m.process(tmp_path, {"match_id": 9}, api, valve, 0, ARGS, failing)
    assert receipt["status"] == "parse_failed" and (tmp_path / "demos/9.dem.bz2").exists()


def test_summary_counts_heroes(tmp_path):
    m = module()
    (tmp_path / "receipts").mkdir()
    for mid, heroes in ((1, [1, 2]), (2, [1, 3])):
        (tmp_path / f"receipts/{mid}.json").write_text(
            json.dumps({"status": "parsed", "heroes": heroes, "parse_seconds": 10, "demo_bytes": 1})
        )
    result = m.summary(tmp_path)
    assert result["parsed"] == 2 and result["hero_games"] == {1: 2, 2: 1, 3: 1}


def test_discovery_query_has_no_hero_filter_unless_asked():
    m = module()
    assert "ANY(radiant_team)" not in m.discovery_sql(0, 1, 100, [])
    assert "91=ANY(radiant_team)" in m.discovery_sql(0, 1, 100, [91])
    assert "avg_rank_tier>=60" in m.discovery_sql(0, 1, 100, [])


def test_long_game_over_the_cleaning_limit_keeps_the_full_parse(tmp_path):
    m = module()

    def handler(request):
        if request.url.host == "api.opendota.com":
            return httpx.Response(200, json=meta(11))
        return httpx.Response(200, content=b"demo")

    def over_limit(args, **kwargs):
        fake_runner(args)
        out = '{"results": [{"status": "failed", "error": "' + m.SIZE_LIMIT_ERROR + '"}]}'
        return subprocess.CompletedProcess(args, 1, out, "")

    def other_failure(args, **kwargs):
        fake_runner(args)
        return subprocess.CompletedProcess(args, 1, '{"status": "failed", "error": "boom"}', "")

    api, valve = clients(handler)
    receipt = m.process(tmp_path, {"match_id": 11}, api, valve, 0, ARGS, over_limit)
    assert receipt["status"] == "parsed"
    assert receipt["parse_mode"] == "normalized_only_over_256mib"
    receipt = m.process(tmp_path / "b", {"match_id": 11}, api, valve, 0, ARGS, other_failure)
    assert receipt["status"] == "parse_failed" and "boom" in receipt["error"]


def test_retry_reprocesses_parse_failures_without_downloading(tmp_path):
    m = module()
    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts/12.json").write_text(
        json.dumps({"match_id": 12, "status": "parse_failed", "error": "old"})
    )
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta/12.json").write_text(json.dumps(meta(12)))
    (tmp_path / "demos").mkdir()
    (tmp_path / "demos/12.dem.bz2").write_bytes(b"demo")

    def handler(request):
        raise AssertionError("no network request expected")

    api, valve = clients(handler)
    args = SimpleNamespace(parse_timeout=10, keep_workspace=False)
    m.retry(tmp_path, api, valve, 0, args, fake_runner)
    receipt = json.loads((tmp_path / "receipts/12.json").read_text())
    assert receipt["status"] == "parsed" and receipt["retried_from"] == "old"
