"""Coach app server: strict query validation, fixed routes, bound artifacts."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from dota_items.modeling import item_timing as it
from dota_items.modeling import situational_items as si
from dota_items.modeling import situational_reference as sr
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def load():
    spec = importlib.util.spec_from_file_location("coach_app", ROOT / "scripts/coach_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_repo(tmp_path, revision=2):
    repo = tmp_path / "repo"
    run = repo / "reports/run"
    run.mkdir(parents=True)
    heroes = [{"hero_id": h, "name_zh": f"英雄{h}"} for h in (8, 30, 87, 111, 1, 2, 3, 4, 5)]
    registry = repo / "knowledge/hero-capabilities/hero-registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"heroes": heroes}))
    item_registry = repo / "knowledge/items/item-registry.json"
    item_registry.parent.mkdir(parents=True)
    item_registry.write_text(
        json.dumps(
            {
                "schema": "item-registry/1",
                "items": {"bfury": {"name_zh": "狂战斧"}, "skadi": {"name_zh": "斯嘉蒂之眼"}},
            }
        )
    )
    vocab = {"sides": ["enemies"], "heroes": [1, 2, 3, 4, 5], "min_count": 30}
    entries = {
        f"{s[0]}:{s[1]}|{i}|{m}": {"n": 100, "positives": 50, "base_rate": 0.5, "model": None}
        for s, items in it.HERO_ITEMS.items()
        for i in items
        for m in it.MINUTES
    }
    (run / "model.json").write_text(json.dumps({"vocab": vocab, "entries": entries}))
    (run / "results.json").write_text(json.dumps({"rows": []}))
    outputs = {n: file_hash(run / n) for n in ("model.json", "results.json")}
    (run / "manifest.json").write_text(
        json.dumps({"outputs": outputs, "protocol_revision": revision})
    )
    write_situational(repo)
    return repo


def write_run(path, files):
    path.mkdir(parents=True)
    for name, value in files.items():
        (path / name).write_text(json.dumps(value))
    outputs = {n: file_hash(path / n) for n in files}
    (path / "manifest.json").write_text(json.dumps({"outputs": outputs}))


def write_situational(repo, passed=False, counts=(5, 4, 3, 2, 1, 1)):
    first = dict(zip(si.CLASSES, counts, strict=True))
    reference = {
        "juggernaut": {
            "spec": [8, 1],
            "games": 30,
            "games_with_any": 16,
            "first_counts": first,
            "bought_counts": {c: n + 1 for c, n in first.items()},
        },
        "supports": [
            {"spec": [h, 5], "games": 20, "bought_counts": {i: 12 for i in sr.SUPPORT_ITEMS}}
            for h, _ in sr.SUPPORTS
        ],
    }
    reference["supports"][0]["bought_counts"]["pipe"] = 3
    write_run(
        repo / "reports/m2b-situational-2026-10-31-v1",
        {
            "model.json": {"train_class_counts": [5, 4, 3, 2, 1, 1]},
            "results.json": {
                "passed": passed,
                "valid_n": 9,
                "log_loss_improvement": 0.04,
                "log_loss_improvement_ci95": [-0.01, 0.09],
                "min_improvement": 0.01,
            },
        },
    )
    write_run(
        repo / "reports/m2b-situational-reference-2026-10-31-v1", {"reference.json": reference}
    )


def test_query_validation_accepts_only_hero_and_position():
    module = load()
    assert module.parse_timing_query("hero=8&position=1") == (8, 1)
    for bad in (
        "hero=8&position=5",  # unsupported spec
        "hero=8&position=1&enemies=1,2",  # U13: lineup no longer accepted
        "hero=8&position=1&radiant=1",
        "hero=8&hero=8&position=1",
        "hero=x&position=1",
        "position=1",
        "",
    ):
        with pytest.raises(ValueError):
            module.parse_timing_query(bad)


def test_load_state_rejects_tampered_or_wrong_revision(tmp_path):
    module = load()
    repo = fixture_repo(tmp_path)
    state = module.load_state("reports/run", repo)
    assert state["meta"]["item_names"]["bfury"] == "狂战斧"
    assert state["meta"]["item_names"]["blink"] == "blink"  # unknown -> raw key, never guessed
    assert [h["name"] for h in state["meta"]["my_heroes"]] == [
        "英雄8",
        "英雄30",
        "英雄87",
        "英雄111",
    ]
    (repo / "reports/run/results.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        module.load_state("reports/run", repo)
    with pytest.raises(ValueError, match="revision"):
        module.load_state("reports/run", fixture_repo(tmp_path / "r1", revision=1))


def test_situational_view_is_baseline_only_and_bound_to_the_frozen_priors(tmp_path):
    module = load()
    view = module.load_state("reports/run", fixture_repo(tmp_path))["situational"]
    assert view["verdict"]["passed"] is False and view["verdict"]["ci95"][0] < 0
    jugg = view["juggernaut"]
    assert jugg["name"] == "英雄8" and [r["first_n"] for r in jugg["items"]] == [5, 4, 3, 2, 1, 1]
    assert jugg["items"][1]["name"] == "斯嘉蒂之眼" and jugg["items"][1]["first_share"] == 4 / 16
    assert any(r["name"] == "净魂之刃路线（含散魂剑）" for r in jugg["items"])
    wd = view["supports"][0]
    assert wd["name"] == "英雄30" and wd["items"][-1]["item"] == "pipe"
    assert wd["items"][-1]["small"] and not wd["items"][0]["small"]
    fixed = {r["item"] for r in wd["items"] if r["fixed"]}
    assert fixed == {"glimmer_cape"}
    oracle = view["supports"][2]
    assert {r["item"] for r in oracle["items"] if r["fixed"]} == {"glimmer_cape", "cyclone"}
    for kwargs, message in (
        ({"counts": (1, 1, 1, 1, 1, 1)}, "priors"),
        ({"passed": True}, "passed"),
    ):
        repo = fixture_repo(tmp_path / message)
        for name in ("m2b-situational-2026-10-31-v1", "m2b-situational-reference-2026-10-31-v1"):
            for f in (repo / "reports" / name).iterdir():
                f.unlink()
            (repo / "reports" / name).rmdir()
        write_situational(repo, **kwargs)
        with pytest.raises(ValueError, match=message):
            module.load_state("reports/run", repo)
    repo = fixture_repo(tmp_path / "tamper")
    (repo / "reports/m2b-situational-reference-2026-10-31-v1/reference.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        module.load_state("reports/run", repo)


def test_http_routes(tmp_path):
    module = load()
    state = module.load_state("reports/run", fixture_repo(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for route in ("/", "/app.js", "/style.css", "/api/meta", "/api/situational"):
            assert OPENER.open(base + route).status == 200
        assert OPENER.open(base + "/favicon.ico").status == 204
        body = json.loads(OPENER.open(base + "/api/item-timing?hero=8&position=1").read())
        assert body["full_lineup"] is False and len(body["items"]) == 8
        for route, code in (
            ("/api/item-timing?hero=8&position=1&enemies=1", 400),
            ("/../knowledge/hero-capabilities/hero-registry.json", 404),
            ("/api/meta?x=1", 404),
            ("/api/situational?hero=8", 404),
            ("/model.json", 404),
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                OPENER.open(base + route)
            assert error.value.code == code
        request = urllib.request.Request(base + "/", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as error:
            OPENER.open(request)
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
