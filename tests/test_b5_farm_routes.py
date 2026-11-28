"""Regression checks for geometry-only labels and aligned, independent income windows."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def routes(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("review_b5_farm_routes")


def test_committed_route_survives_later_interrupt_and_empty_camp(routes):
    path = [(500, 0), (700, 0), (900, 0), (1100, 0), None, None, None]
    camps = [dict(id=3, x=1850, y=0)]
    assert routes.movement(path, (0, 0), camps)[0] == routes.JUNGLE
    assert routes.movement(path, (0, 0), [])[0] == routes.UNKNOWN
    assert routes.movement([(500, 0), (1300, 0), *path[2:]], (0, 0), camps)[0] == routes.UNKNOWN


def test_lane_and_unobserved_routes(routes):
    assert routes.movement([(500, 0)] * 7, (0, 0), [])[0] == routes.LANE
    assert routes.movement([(900, 0)] * 7, (0, 0), [])[0] == routes.UNKNOWN
    assert routes.movement([(500, 0)] * 2 + [None] * 5, (0, 0), [])[0] == routes.UNKNOWN


def test_real_income_endpoints_and_incomplete_windows(routes):
    events = [(t, t, "hero", 13, 1) for t in (99, 100, 119, 120, 129, 130)]
    bounds = {("hero", t): [v, 0] for t, v in ((100, 5), (120, 7), (130, 10))}
    assert routes.income("hero", 100, 20, 130, events, bounds)["creep"] == dict(
        counter=2, event=2, difference=0
    )
    assert routes.income("hero", 100, 30, 130, events, bounds)["creep"] == dict(
        counter=5, event=4, difference=1
    )
    assert routes.income("hero", 100, 30, 129, events, bounds) is None
    assert routes.income("hero", 100, 20, 129, events, {})["neutral"] == dict(
        counter=None, event=0, difference=None
    )


def test_census_includes_old_unknowns(routes):
    report = (
        "| 兵线 | 2 | 1 |\n"
        "| 16:45 | 风行者 | 兵线 | 未知 | 原因 |\n"
        "## 15:13　风行者 · 兵线\n观察到的动作：继续收线。\n"
    )
    assert routes.candidates(report) == [(913, "风行者", "继续收线"), (1005, "风行者", "未知")]
    with pytest.raises(ValueError, match="census"):
        routes.candidates(report.replace("| 2 |", "| 3 |"))


def test_local_viewer_reinstall_and_report_binding(routes, tmp_path):
    import json

    renderer = importlib.import_module("render_b5_farm_routes")
    path = tmp_path / "index.html"
    evidence = [dict(id=k, report_sha256=v) for k, v in routes.REPORT_HASHES.items()]
    html = (
        f'<script type="application/json" id="installed-evidence">{json.dumps(evidence)}</script>'
    )
    path.write_text(html + '<main><div class="workbench"></div></main>')
    renderer.install_workbench(path, "<p>30 秒</p>")
    saved = path.read_bytes()
    renderer.install_workbench(path, "<p>30 秒</p>")
    assert path.read_bytes() == saved
    assert path.read_text().count('id="farm-routes"') == 1
    path.write_text(path.read_text().replace(evidence[0]["report_sha256"], "stale"))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="fingerprints"):
        renderer.install_workbench(path, "stale")
    assert path.read_bytes() == before
