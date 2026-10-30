"""Local case HTTP isolation and overwrite refusal; no live network/budget use."""

import hashlib
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


def module():
    path = Path(__file__).parents[1] / "scripts/decision_review.py"
    spec = importlib.util.spec_from_file_location("decision_review_cli", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_existing_output_refused(tmp_path):
    with pytest.raises(ValueError, match="Output exists"):
        module().build(tmp_path)


def test_unsafe_plan_refused_before_output_creation(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"schema": "manual-decision-cases/1", "cases": [{"id": "../raw"}]}))
    output = tmp_path / "new"
    with pytest.raises(ValueError, match="Invalid manual case plan"):
        module().build(output, plan_path=plan)
    assert not output.exists()


def test_advice_is_sealed_before_any_future_read(tmp_path, monkeypatch):
    cli = module()
    output = tmp_path / "output"
    replay = tmp_path / "replay"
    folder = replay / "aligned/1"
    folder.mkdir(parents=True)
    raw = tmp_path / "raw.json"
    for p in (raw, folder / "manifest.json", folder / "radiant.jsonl"):
        p.write_bytes(b"{}")
    digest = hashlib.sha256(b"{}").hexdigest()
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "schema": "manual-decision-cases/1",
                "cases": [dict(id="case", match_id=1, view="radiant", tick=30, slot=0)],
            }
        )
    )
    calls = []

    class Replay:
        def __init__(self, root):
            pass

        def timeline(self, *args):
            return {"frames": [dict(tick=t, time=t // 30) for t in (0, 30, 60)]}

        def frame(self, mid, view, tick, trail):
            calls.append(tick)
            if tick > 30:
                assert (output / "advice-seal.json").exists()
                assert (output / "cases.json").exists()
                assert (output / "future-read-start.json").exists()
            return dict(tick=tick, time=tick // 30, players=[dict(player_slot=0)])

    class Evidence:
        def __init__(self, *args):
            pass

        def build(self, *args):
            assert not any(t > 30 for t in calls)
            return {
                "decision_input": {},
                "provenance": {
                    "raw": str(raw),
                    "raw_sha256": digest,
                    "view_sha256": digest,
                    "manifest_sha256": digest,
                },
            }

    monkeypatch.setattr(cli, "ReplayStore", Replay)
    monkeypatch.setattr(cli, "DecisionEvidenceStore", Evidence)
    cli.build(output, plan_path=plan, replay_root=replay)
    assert calls == [0, 60]
    assert (output / "advice-plan.json").read_bytes() == plan.read_bytes()


def test_http_curated_routes_and_separate_future(tmp_path):
    repo = tmp_path / "repo"
    image = repo / "data/map-reference-2026-10-26-v1/gem/assets/maps/Game_map_7.41.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"map-test")
    root = repo / "data/replay-quality-2026-10-26-v1"
    root.mkdir()
    (root / "map-calibration.json").write_text(
        json.dumps({"image_sha256": hashlib.sha256(b"map-test").hexdigest()})
    )
    output = tmp_path / "cases"
    output.mkdir()
    (output / "cases.json").write_text(json.dumps({"cards": [{"case": {"id": "first"}}]}))
    (output / "first-after.json").write_text('{"future_marker":"only-explicit-route"}')
    (output / "verification.json").write_text(
        json.dumps(
            {
                "outputs": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in output.glob("*.json")
                }
            }
        )
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), module().make_handler(output, repo))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/cases") as r:
            assert b"future_marker" not in r.read()
            assert r.headers["Cache-Control"] == "no-store"
        with urlopen(base + "/api/first-after.json") as r:
            assert b"future_marker" in r.read()
        for route in ["/raw.json", "/advice-plan.json", "/api/../../raw", "/api/cases?path=raw"]:
            with pytest.raises(HTTPError) as error:
                urlopen(base + route)
            assert error.value.code == 404
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/", headers={"Host": "evil.example"}))
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
