"""Synthetic viewer isolation, discontinuity, corruption and HTTP route regressions."""

import hashlib
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dota_items.data.replay_viewer import ReplayStore


def row(tick, visible=True, **kw):
    return (
        dict(
            match_id=1,
            player_slot=0,
            hero_id=14,
            source_tick=tick,
            time=tick // 30,
            observer_team="radiant",
            visibility="visible" if visible else "hidden",
            current_position={"x": 9000 + tick, "y": 10000} if visible else None,
            visible_life_state=0 if visible else None,
            last_seen={"position": {"x": 9000, "y": 10000}, "source_tick": 0, "time": 0},
        )
        | kw
    )


def write_bundle(root, rows):
    folder = root / "aligned/1"
    folder.mkdir(parents=True, exist_ok=True)
    payload = b"".join((json.dumps(r) + "\n").encode() for r in rows)
    (folder / "radiant.jsonl").write_bytes(payload)
    manifest = json.dumps(
        {
            "match_id": 1,
            "counts": {"radiant": len(rows)},
            "files": {"radiant.jsonl": hashlib.sha256(payload).hexdigest()},
        }
    ).encode()
    (folder / "manifest.json").write_bytes(manifest)
    (root / "summary.json").write_text(
        json.dumps(
            {"matches": [{"match_id": 1, "manifest_sha256": hashlib.sha256(manifest).hexdigest()}]}
        )
    )
    return ReplayStore(root)


def test_team_view_works_without_any_omniscient_file(tmp_path):
    store = write_bundle(tmp_path, [row(0), row(30, False), row(60)])
    assert store.catalog() == [1]
    assert len(store.timeline(1, "radiant")["frames"]) == 3
    p = store.frame(1, "radiant", 30)["players"][0]
    assert p["current_position"] is None and p["life_state"] is None
    assert p["last_seen"]["source_tick"] == 0
    assert not ({"x", "y", "state_refs", "state_entity"} & p.keys())
    assert store.frame(1, "radiant", 60)["players"][0]["segments"] == []


def test_same_second_ticks_preserved_and_duplicates_withheld(tmp_path):
    store = write_bundle(
        tmp_path, [row(0), row(5), row(30), row(30, current_position={"x": 999, "y": 888})]
    )
    assert [f["tick"] for f in store.timeline(1, "radiant")["frames"]] == [0, 5, 30]
    p = store.frame(1, "radiant", 30)["players"][0]
    assert p["current_position"] is None and p["last_seen"] is None
    assert p["display_issue"] == "duplicate_tick"


@pytest.mark.parametrize(
    "change",
    [
        {"current_position": {"x": 12345, "y": 54321}, "visibility": "hidden"},
        {"visible_life_state": 2, "visibility": "unknown", "current_position": None},
        {"observer_team": "dire"},
        {"last_seen": {"position": {"x": 9, "y": 8}, "source_tick": 90, "time": 3}},
        {"current_position": {"x": True, "y": 3}},
    ],
)
def test_bad_observer_records_fail_closed(tmp_path, change):
    store = write_bundle(tmp_path, [row(0, **change)])
    with pytest.raises(ValueError):
        store.timeline(1, "radiant")


def test_missing_sample_is_unknown_not_current(tmp_path):
    store = write_bundle(tmp_path, [row(0), row(30, player_slot=1, hero_id=8)])
    p = store.frame(1, "radiant", 30)["players"][0]
    assert p["visibility"] == "unknown" and p["current_position"] is None
    assert p["display_issue"] == "no_sample"


@pytest.mark.parametrize("last", [row(100), row(30, current_position={"x": 20000, "y": 20000})])
def test_long_gap_and_displacement_break_trails(tmp_path, last):
    store = write_bundle(tmp_path, [row(0), last])
    assert store.frame(1, "radiant", last["source_tick"])["players"][0]["segments"] == []


def test_no_future_positions_and_positive_visible_control(tmp_path):
    store = write_bundle(tmp_path, [row(0), row(30), row(60)])
    before = store.frame(1, "radiant", 30)
    changed = write_bundle(tmp_path, [row(0), row(30), row(60, current_position={"x": 1, "y": 1})])
    assert before == changed.frame(1, "radiant", 30)
    changed = write_bundle(
        tmp_path, [row(0), row(30, current_position={"x": 9001, "y": 10001}), row(60)]
    )
    assert before != changed.frame(1, "radiant", 30)


@pytest.mark.parametrize("filename", ["manifest.json", "radiant.jsonl"])
def test_hash_change_rejected_on_load(tmp_path, filename):
    store = write_bundle(tmp_path, [row(0)])
    p = tmp_path / "aligned/1" / filename
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.timeline(1, "radiant")


def test_http_allowlist_and_view_isolation(tmp_path):
    store = write_bundle(tmp_path, [row(0), row(30, False)])
    path = Path(__file__).parents[1] / "scripts/replay_viewer.py"
    spec = importlib.util.spec_from_file_location("viewer_web", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    map_path = tmp_path / "map.jpg"
    map_path.write_bytes(b"synthetic-map")
    handler = module.make_handler(
        store,
        map_path,
        {"image_sha256": hashlib.sha256(b"synthetic-map").hexdigest(), "image_size": [8878, 8356]},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/frame?match=1&view=radiant&tick=30&trail=15") as r:
            p = json.load(r)["players"][0]
            assert p["current_position"] is None
            assert r.headers["Cache-Control"] == "no-store"
        for route in [
            "/raw.json",
            "/api/frame?match=1&view=../../raw&tick=30&trail=15",
            "/api/timeline?match=2&view=radiant",
            "/api/timeline?match=1&view=radiant&view=omniscient",
        ]:
            with pytest.raises(HTTPError):
                urlopen(base + route)
        with pytest.raises(HTTPError) as e:
            urlopen(Request(base + "/", headers={"Host": "evil.example"}))
        assert e.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_transitions_come_only_from_selected_view(tmp_path):
    store = write_bundle(tmp_path, [row(0), row(30, False), row(60)])
    assert store.frame(1, "radiant", 30)["players"][0]["transitions"] == ["disappeared"]
    assert store.frame(1, "radiant", 60)["players"][0]["transitions"] == ["appeared"]


def test_unclean_omniscient_coordinate_is_not_displayed():
    from dota_items.data.replay_viewer import project

    base = row(0) | {"quality_flags": ["state_ambiguous"], "x": 777, "y": 888, "life_state": 0}
    assert project(base, "omniscient")["current_position"] is None
    base["quality_flags"] = ["pause", "repeated_game_second"]
    assert project(base, "omniscient")["current_position"] == {"x": 777, "y": 888}


def test_break_reasons_do_not_call_displacement_bad_data(tmp_path):
    store = write_bundle(
        tmp_path, [row(0), row(30, current_position={"x": 20000, "y": 20000}), row(100, False)]
    )
    p = store.frame(1, "radiant", 100)["players"][0]
    assert p["break_reasons"] == {
        "position_jump": 1,
        "observation_unavailable": 1,
        "hidden": 1,
        "sampling_gap": 1,
    }


def test_store_never_calls_event_adapter_for_team(tmp_path):
    class ForbiddenEvents:
        def load(self, *args):
            raise AssertionError("event load in team view")

        def attach(self, *args):
            raise AssertionError("event attach in team view")

    store = write_bundle(tmp_path, [row(0)])
    store.events = ForbiddenEvents()
    assert "event_ticks" not in store.timeline(1, "radiant")
    assert "event_evidence_status" not in store.frame(1, "radiant", 0)


@pytest.mark.parametrize("life,reason", [(1, "dying"), (2, "dead"), (None, "state_missing")])
def test_dead_and_missing_trail_samples_are_distinct(tmp_path, life, reason):
    store = write_bundle(
        tmp_path, [row(0), row(30, current_position=None, visible_life_state=life)]
    )
    p = store.frame(1, "radiant", 30)["players"][0]
    assert p["position_status"] == reason
    assert p["break_reasons"][reason] == 1
    assert "hidden" not in p["break_reasons"]
