"""Unified local coach app (M2-T5 shell): item-timing reference and 针对装 reference pages.

Loopback only, Host-checked, fixed routes, no file access beyond the bound run.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dota_items.data.item_registry import display_name, load_registry
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.modeling import item_timing
from dota_items.modeling import situational_items as si
from dota_items.modeling import situational_reference as sr
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / "coach_app_assets"
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
DEFAULT_RUN = "reports/m2-item-timing-2026-10-30-r2"
SITUATIONAL_RUN = "reports/m2b-situational-2026-10-31-v1"
SITUATIONAL_REFERENCE = "reports/m2b-situational-reference-2026-10-31-v1"
SMALL_COUNT = 10
ITEM_REGISTRY = "knowledge/items/item-registry.json"
NOTES = [
    "数据：超凡及以上段位、30分钟以上的比赛（2026-10-12至13，补丁7.41），节奏快于传奇段常见对局（U7）。",
    "主宰排除10分钟补刀<35的对线崩盘局（U8）。",
    "出装时间主要取决于自己和队友的线上经济，而不是敌方阵容（U13，10分钟经济可解释狂战斧时间的61%）；按你本局表现的时间参照将在赛后复盘中提供。",
    "敌方阵容影响的是“出什么”，见“赛前 · 针对装”页。",
]
SITUATIONAL_NOTES = [
    "数据：M1训练集（超凡及以上、30分钟以上的比赛，补丁7.41）；与模型基线所用比赛相同。",
    "主宰：排除对线崩盘局（U8）；“第一件”只在出过针对装的局里统计，同秒按购买顺序；散魂剑并入净魂之刃路线（U16）。",
    "辅助：只显示整局出现率，不建模（U17）；清单为U21。标“固定装”的是该英雄的常规关键装，出现率不代表针对性。",
    "高分段常出不等于“该出”；出现率也受局势和经济影响，不只由阵容决定。",
]


def _read(path):
    return parse_source_json(read_source_bytes(path))


def _verified(path):
    manifest = _read(path / "manifest.json")
    for name, expected in manifest["outputs"].items():
        if file_hash(path / name) != expected:
            raise ValueError(f"Run artifact changed: {name}")
    return manifest


def situational_view(reference, model, result, items, hero_names):
    """Baseline 针对装 page (U20). The frozen model is not shown unless it passed."""
    if result["passed"]:
        raise ValueError("Model passed; the page must be redesigned before showing it")
    jugg = reference["juggernaut"]
    if [jugg["first_counts"][c] for c in si.CLASSES] != model["train_class_counts"]:
        raise ValueError("Reference does not match the M2b baseline priors")

    def name(key):
        return "净魂之刃路线（含散魂剑）" if key == "diffusal" else display_name(items, key)

    with_any = jugg["games_with_any"]
    return {
        "verdict": {
            "passed": False,
            "valid_n": result["valid_n"],
            "improvement": result["log_loss_improvement"],
            "ci95": result["log_loss_improvement_ci95"],
            "min_improvement": result["min_improvement"],
        },
        "juggernaut": {
            "spec": jugg["spec"],
            "name": hero_names[jugg["spec"][0]],
            "games": jugg["games"],
            "games_with_any": with_any,
            "items": sorted(
                (
                    {
                        "item": c,
                        "name": name(c),
                        "first_n": jugg["first_counts"][c],
                        "first_share": jugg["first_counts"][c] / with_any,
                        "bought_n": jugg["bought_counts"][c],
                        "bought_rate": jugg["bought_counts"][c] / jugg["games"],
                    }
                    for c in si.CLASSES
                ),
                key=lambda r: -r["first_n"],
            ),
        },
        "supports": [
            {
                "spec": s["spec"],
                "name": hero_names[s["spec"][0]],
                "games": s["games"],
                "items": sorted(
                    (
                        {
                            "item": i,
                            "name": name(i),
                            "n": n,
                            "rate": n / s["games"],
                            "small": n < SMALL_COUNT,
                            "fixed": i in item_timing.HERO_ITEMS[tuple(s["spec"])],
                        }
                        for i, n in s["bought_counts"].items()
                    ),
                    key=lambda r: (-r["n"], sr.SUPPORT_ITEMS.index(r["item"])),
                ),
            }
            for s in reference["supports"]
        ],
        "notes": SITUATIONAL_NOTES,
        "runs": [SITUATIONAL_RUN, SITUATIONAL_REFERENCE],
    }


def load_state(
    run=DEFAULT_RUN,
    repo=ROOT,
    situational_run=SITUATIONAL_RUN,
    situational_reference=SITUATIONAL_REFERENCE,
):
    run = repo / run
    manifest = _verified(run)
    if manifest.get("protocol_revision") != 2:
        raise ValueError("Page requires the revision-2 run")
    registry = _read(repo / REGISTRY)
    heroes = sorted(
        ({"id": h["hero_id"], "name": h["name_zh"]} for h in registry["heroes"]),
        key=lambda h: h["id"],
    )
    items = load_registry(repo / ITEM_REGISTRY)
    model = _read(run / "model.json")
    rows = _read(run / "results.json")["rows"]
    hero_names = {h["id"]: h["name"] for h in heroes}
    _verified(repo / situational_run)
    _verified(repo / situational_reference)
    situational = situational_view(
        _read(repo / situational_reference / "reference.json"),
        _read(repo / situational_run / "model.json"),
        _read(repo / situational_run / "results.json"),
        items,
        hero_names,
    )
    meta = {
        "heroes": heroes,
        "my_heroes": [
            {"hero_id": h, "position": p, "name": hero_names[h]} for h, p in item_timing.HERO_ITEMS
        ],
        "item_names": {
            item: display_name(items, item)
            for item_list in item_timing.HERO_ITEMS.values()
            for item in item_list
        },
        "minutes": list(item_timing.MINUTES),
        "notes": NOTES,
        "run": str(run.relative_to(repo)),
    }
    return {
        "meta": meta,
        "model": model,
        "rows": rows,
        "hero_ids": set(hero_names),
        "situational": situational,
    }


def parse_timing_query(query):
    """Strict validation: exactly hero and position, a supported pair, nothing else.

    U13: the page is a high-rank baseline reference; lineup inputs are not accepted.
    """
    params = parse_qs(query, keep_blank_values=True, strict_parsing=bool(query))
    if set(params) != {"hero", "position"} or any(len(v) != 1 for v in params.values()):
        raise ValueError("Bad parameters")
    try:
        spec = (int(params["hero"][0]), int(params["position"][0]))
    except ValueError as error:
        raise ValueError("Bad parameters") from error
    if spec not in item_timing.HERO_ITEMS:
        raise ValueError("Bad parameters")
    return spec


def make_handler(state):
    static = {
        "/": ("text/html; charset=utf-8", (ASSETS / "index.html").read_bytes()),
        "/app.js": ("text/javascript; charset=utf-8", (ASSETS / "app.js").read_bytes()),
        "/style.css": ("text/css; charset=utf-8", (ASSETS / "style.css").read_bytes()),
        "/api/meta": (
            "application/json; charset=utf-8",
            json.dumps(state["meta"], ensure_ascii=False).encode(),
        ),
        "/api/situational": (
            "application/json; charset=utf-8",
            json.dumps(state["situational"], ensure_ascii=False).encode(),
        ),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, status, mime, content):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            port = self.server.server_port
            if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.send_error(403)
                return
            url = urlsplit(self.path)
            if url.path == "/favicon.ico" and not url.query:
                self.send_response(204)
                self.end_headers()
                return
            if url.path in static and not url.query:
                self._send(200, *static[url.path])
                return
            if url.path == "/api/item-timing":
                try:
                    spec = parse_timing_query(url.query)
                except ValueError:
                    self.send_error(400)
                    return
                view = item_timing.timing_view(state["model"], state["rows"], spec, [], True)
                body = json.dumps(view, ensure_ascii=False).encode()
                self._send(200, "application/json; charset=utf-8", body)
                return
            self.send_error(404)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=DEFAULT_RUN)
    parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(load_state(args.run)))
    print(f"Coach app: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
