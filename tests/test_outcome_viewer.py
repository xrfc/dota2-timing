import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from scripts.outcome_match_report import render, render_input_coverage
from scripts.outcome_viewer import handler_for, load_reports, read_map


@pytest.fixture
def report(tmp_path):
    empty = dict(opportunities=0, eligible=0, supported=0, balanced=0, excluded=[])
    hero = "npc_dota_hero_sven"
    excluded = dict(
        t=150,
        hero=hero,
        action="unknown",
        early_death=True,
        unknown_action=True,
        incomplete_window=False,
    )
    diagnostics = dict(
        observed_heroes=[hero],
        by_domain={
            "wave": empty,
            "jungle": {**empty, "opportunities": 1, "excluded": [excluded]},
            "support": {**empty, "opportunities": 1, "eligible": 1, "supported": 1, "balanced": 1},
        },
    )
    actual = dict(hits=2, gold=-30, xp=None, death=0, dead_seconds=0, arrival=1)
    row = dict(
        hero=hero,
        action="approach",
        t=61,
        observed=actual,
        overlap_reason=None,
        label_exclusions={"xp": "unverified_level_transition"},
        values={"approach": {**actual, "death": 0.125}, "stay": actual},
    )
    text = render(123, [("support", row, 0.2)], {hero: "斯温"}, diagnostics)
    text += render_input_coverage(
        {k: dict(start=900, end=920, missing=[[905, 906]]) for k in ("state-v3", "extras-v1")}
    )
    path = tmp_path / "123/match-report.md"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    return path


def test_report_transports_observations_estimates_and_exclusions(report):
    (match,) = load_reports(report.parent.parent)["matches"]
    (clip,) = match["clips"]
    assert (match["id"], clip["time"], clip["hero"], clip["domain"], clip["action"]) == (
        "123",
        "1:01",
        "斯温",
        "支援",
        "接近队友",
    )
    assert clip["metrics"][-1] == "队友受击时到场"
    assert clip["rows"][0] == {"label": "录像实况", "values": ["2", "-30", "缺测", "否", "0", "是"]}
    assert clip["rows"][1]["values"] == ["2.00", "-30.00", "缺估", "12.5%", "0.00", "100.0%"]
    assert "同等级经验变化缺测" in " ".join(clip["notes"])
    assert match["excluded"][0]["reason"] == "前六秒无法按冻结规则识别动作、前六秒死亡"
    assert any("905–906" in line for line in match["coverage"])


@pytest.mark.parametrize(
    "old,new",
    [
        ("对局 123", "对局 456"),
        ("| 支援 | 1 | 1 | 1 | 1 |", "| 支援 | 2 | 1 | 1 | 1 |"),
        ("## 逐秒输入覆盖", "## 不完整"),
        ("| 录像实况 | 2 |", "| 录像实况 |"),
    ],
)
def test_inconsistent_report_is_rejected(report, old, new):
    text = report.read_text(encoding="utf-8")
    assert old in text
    report.write_text(text.replace(old, new), encoding="utf-8")
    with pytest.raises(ValueError, match="match-report.md"):
        load_reports(report.parent.parent)


def test_local_routes_keep_private_files_inaccessible(report):
    root = report.parent.parent
    reports = load_reports(root)
    bundle = dict(
        schema="b5-perspective-map/1",
        match="123",
        report_sha256=reports["matches"][0]["report_sha256"],
        clips=[],
    )
    report.with_name("perspective-map.json").write_text(json.dumps(bundle))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler_for(reports, root, root)) as server:
        serving = Thread(target=server.serve_forever)
        serving.start()
        try:
            for path, host, status in [
                ("/api/reports", f"localhost:{server.server_port}", 200),
                ("/api/reports", "other.invalid", 403),
                ("/api/map/123", f"localhost:{server.server_port}", 200),
                ("/api/map/999", f"localhost:{server.server_port}", 404),
                ("/api/map/123", "other.invalid", 403),
                ("/123/match-report.md", f"127.0.0.1:{server.server_port}", 404),
                ("/heroes/../123/match-report.md", f"127.0.0.1:{server.server_port}", 404),
            ]:
                conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                try:
                    conn.request("GET", path, headers={"Host": host})
                    response = conn.getresponse()
                    assert response.status == status
                    if status == 200:
                        assert json.loads(response.read()) == (
                            bundle if path == "/api/map/123" else reports
                        )
                finally:
                    conn.close()
        finally:
            server.shutdown()
            serving.join()


@pytest.mark.parametrize(
    "change", [{"match": "321"}, {"report_sha256": "stale"}, {"schema": "old"}]
)
def test_map_must_belong_to_loaded_report(report, change):
    match = load_reports(report.parent.parent)["matches"][0]
    bundle = dict(
        schema="b5-perspective-map/1", match=match["id"], report_sha256=match["report_sha256"]
    )
    path = report.with_name("perspective-map.json")
    path.write_text(json.dumps(bundle | change))
    with pytest.raises(ValueError, match="不匹配"):
        read_map(path, match)
