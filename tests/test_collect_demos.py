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
    receipt = m.process(
        tmp_path, {"match_id": 6, "avg_rank_tier": 70}, api, valve, 0, ARGS, fake_runner
    )
    assert receipt["status"] == "skipped" and receipt["reasons"] == ["demo_not_found"]

    def short(request):
        return httpx.Response(200, json=meta(7, duration=300))

    api, valve = clients(short)
    receipt = m.process(
        tmp_path, {"match_id": 7, "avg_rank_tier": 70}, api, valve, 0, ARGS, fake_runner
    )
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
    receipt = m.process(
        tmp_path, {"match_id": 8, "avg_rank_tier": 70}, api, valve, 0, ARGS, fake_runner
    )
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
    receipt = m.process(
        tmp_path, {"match_id": 9, "avg_rank_tier": 70}, api, valve, 0, ARGS, failing
    )
    assert receipt["status"] == "parse_failed" and (tmp_path / "demos/9.dem.bz2").exists()


def test_summary_counts_heroes_only_in_qualifying_replays(tmp_path):
    m = module()
    (tmp_path / "receipts").mkdir()
    for mid, rank, heroes in ((1, 70, [1, 2]), (2, 75, [1, 3]), (3, 65, [4]), (4, None, [5])):
        (tmp_path / f"receipts/{mid}.json").write_text(
            json.dumps(
                {"status": "parsed", "avg_rank_tier": rank, "heroes": heroes, "parse_seconds": 10}
            )
        )
    result = m.summary(tmp_path)
    assert result["parsed"] == 2 and result["hero_games"] == {1: 2, 2: 1, 3: 1}
    assert result["parsed_total"] == 4 and result["parsed_outside_rank"] == 2


def test_discovery_query_has_no_hero_filter_unless_asked():
    m = module()
    assert "ANY(radiant_team)" not in m.discovery_sql(0, 1, 100, [])
    assert "91=ANY(radiant_team)" in m.discovery_sql(0, 1, 100, [91])
    assert "avg_rank_tier>=70" in m.discovery_sql(0, 1, 100, [])


@pytest.mark.parametrize("rank", [65, None])
def test_out_of_scope_candidate_is_skipped_before_network(tmp_path, rank):
    m = module()
    receipt = m.process(tmp_path, {"match_id": 10, "avg_rank_tier": rank}, None, None, 0, ARGS)
    assert receipt["status"] == "skipped"
    assert receipt["reasons"] == ["rank_below_threshold_or_unknown"]


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
    row = {"match_id": 11, "avg_rank_tier": 70}
    receipt = m.process(tmp_path, row, api, valve, 0, ARGS, over_limit)
    assert receipt["status"] == "parsed"
    assert receipt["parse_mode"] == "normalized_only_over_256mib"
    receipt = m.process(tmp_path / "b", row, api, valve, 0, ARGS, other_failure)
    assert receipt["status"] == "parse_failed" and "boom" in receipt["error"]


def test_retry_reprocesses_parse_failures_without_downloading(tmp_path):
    m = module()
    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts/12.json").write_text(
        json.dumps({"match_id": 12, "status": "parse_failed", "avg_rank_tier": 70, "error": "old"})
    )
    (tmp_path / "receipts/13.json").write_text(
        json.dumps({"match_id": 13, "status": "parse_failed", "avg_rank_tier": 65})
    )
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta/12.json").write_text(json.dumps(meta(12)))
    (tmp_path / "demos").mkdir()
    (tmp_path / "demos/12.dem.bz2").write_bytes(b"demo")

    def handler(request):
        raise AssertionError("no network request expected")

    api, valve = clients(handler)
    args = SimpleNamespace(parse_timeout=10, keep_workspace=False, target=2)
    m.retry(tmp_path, api, valve, 0, args, fake_runner)
    receipt = json.loads((tmp_path / "receipts/12.json").read_text())
    assert receipt["status"] == "parsed" and receipt["retried_from"] == "old"
    assert json.loads((tmp_path / "receipts/13.json").read_text())["status"] == "parse_failed"


def test_progress_line(tmp_path):
    m = module()
    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts/1.json").write_text(
        json.dumps(
            {"status": "parsed", "avg_rank_tier": 70, "download_seconds": 10, "parse_seconds": 110}
        )
    )
    (tmp_path / "receipts/2.json").write_text(json.dumps({"status": "skipped"}))
    (tmp_path / "receipts/3.json").write_text(json.dumps({"status": "parsed", "avg_rank_tier": 65}))
    line = m.progress(tmp_path, 31)
    assert "进度 1/31" in line and "跳过 1" in line and "每场约 120 秒" in line
    assert "预计还要 1.0 小时" in line


def test_resume_collects_until_qualifying_target(tmp_path, monkeypatch):
    m = module()
    root = tmp_path / "demos"
    for mid, rank in ((1, 65), (2, 71)):
        m.write_new(
            root / f"receipts/{mid}.json",
            {"match_id": mid, "status": "parsed", "avg_rank_tier": rank, "parse_seconds": 10},
        )
    processed = []

    def discover(api, lower, upper, seen, heroes, want):
        assert seen == {1, 2}
        return [{"match_id": mid, "avg_rank_tier": 70} for mid in (3, 4)]

    def process(root, row, api, plain, patch_start, args):
        processed.append(row["match_id"])
        return {**row, "status": "parsed", "parse_seconds": 10}

    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "DISK_RESERVE", 0)
    monkeypatch.setattr(m, "RequestBudget", lambda _: object())
    monkeypatch.setattr(m, "clients", lambda route, budget: (httpx.Client(), httpx.Client()))
    monkeypatch.setattr(m, "latest_patch_start", lambda _: ("test", 0))
    monkeypatch.setattr(m, "discover", discover)
    monkeypatch.setattr(m, "process", process)
    args = SimpleNamespace(
        root=root,
        route="proxy",
        target=2,
        hero=[],
        min_age_hours=2,
        max_age_hours=96,
        retry_failed=False,
        keep_workspace=False,
        once=False,
    )
    m.run(args)
    assert processed == [3]
    assert m.summary(root)["parsed"] == 2
    assert m.receipts(root)[1]["status"] == "parsed"


def test_back_off_waits_longer_then_stops(tmp_path):
    m = module()
    waits = []
    args = SimpleNamespace(once=False)
    assert m.back_off(tmp_path, 1, args, waits.append)
    assert m.back_off(tmp_path, 4, args, waits.append)
    assert m.back_off(tmp_path, 7, args, waits.append)
    assert waits == [60, 480, 1800]
    assert not m.back_off(tmp_path, m.MAX_FAILURES, args, waits.append)
    assert not m.back_off(tmp_path, 1, SimpleNamespace(once=True), waits.append)
