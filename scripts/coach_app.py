"""Unified local coach app (M2-T5 shell). Currently serves the pre-game item-timing page.

Loopback only, Host-checked, fixed routes, no file access beyond the bound run.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.modeling import item_timing
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / "coach_app_assets"
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
DEFAULT_RUN = "reports/m2-item-timing-2026-10-30-r2"
ITEM_NAMES = {
    "magic_wand": "魔杖",
    "power_treads": "动力鞋",
    "bfury": "狂战斧",
    "yasha": "夜叉",
    "manta": "分身斧",
    "butterfly": "蝴蝶",
    "blink": "跳刀",
    "ultimate_scepter": "阿哈利姆神杖",
    "arcane_boots": "秘法鞋",
    "glimmer_cape": "微光披风",
    "aghanims_shard": "阿哈利姆魔晶",
    "ghost": "幽魂权杖",
    "cyclone": "Eul的神圣法杖",
    "aether_lens": "以太透镜",
}
NOTES = [
    "数据：超凡及以上段位、30分钟以上的比赛（2026-10-12至13，补丁7.41），节奏快于传奇段常见对局（U7）。",
    "主宰排除10分钟补刀<35的对线崩盘局（U8）。",
    "阵容调整只来自一次“看过验证集后的第二次尝试”，标为初步；独立评估在M4。",
]


def _read(path):
    return parse_source_json(read_source_bytes(path))


def load_state(run=DEFAULT_RUN, repo=ROOT):
    run = repo / run
    manifest = _read(run / "manifest.json")
    for name, expected in manifest["outputs"].items():
        if file_hash(run / name) != expected:
            raise ValueError(f"Run artifact changed: {name}")
    if manifest.get("protocol_revision") != 2:
        raise ValueError("Page requires the revision-2 run")
    registry = _read(repo / REGISTRY)
    heroes = sorted(
        ({"id": h["hero_id"], "name": h["name_zh"]} for h in registry["heroes"]),
        key=lambda h: h["id"],
    )
    model = _read(run / "model.json")
    rows = _read(run / "results.json")["rows"]
    hero_names = {h["id"]: h["name"] for h in heroes}
    meta = {
        "heroes": heroes,
        "my_heroes": [
            {"hero_id": h, "position": p, "name": hero_names[h]} for h, p in item_timing.HERO_ITEMS
        ],
        "item_names": ITEM_NAMES,
        "minutes": list(item_timing.MINUTES),
        "notes": NOTES,
        "run": str(run.relative_to(repo)),
    }
    return {"meta": meta, "model": model, "rows": rows, "hero_ids": set(hero_names)}


def parse_timing_query(query, hero_ids):
    """Strict validation: exactly one of each parameter, known ids, distinct enemies."""
    params = parse_qs(query, keep_blank_values=True, strict_parsing=bool(query))
    if set(params) - {"hero", "position", "radiant", "enemies"} or any(
        len(v) != 1 for v in params.values()
    ):
        raise ValueError("Bad parameters")
    try:
        spec = (int(params["hero"][0]), int(params["position"][0]))
        radiant = {"1": True, "0": False}[params["radiant"][0]]
        raw = params.get("enemies", [""])[0]
        enemies = [int(v) for v in raw.split(",")] if raw else []
    except (KeyError, ValueError) as error:
        raise ValueError("Bad parameters") from error
    if (
        spec not in item_timing.HERO_ITEMS
        or len(enemies) > 5
        or len(set(enemies)) != len(enemies)
        or any(e not in hero_ids or e == spec[0] for e in enemies)
    ):
        raise ValueError("Bad parameters")
    return spec, radiant, enemies


def make_handler(state):
    static = {
        "/": ("text/html; charset=utf-8", (ASSETS / "index.html").read_bytes()),
        "/app.js": ("text/javascript; charset=utf-8", (ASSETS / "app.js").read_bytes()),
        "/style.css": ("text/css; charset=utf-8", (ASSETS / "style.css").read_bytes()),
        "/api/meta": (
            "application/json; charset=utf-8",
            json.dumps(state["meta"], ensure_ascii=False).encode(),
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
                    spec, radiant, enemies = parse_timing_query(url.query, state["hero_ids"])
                except ValueError:
                    self.send_error(400)
                    return
                view = item_timing.timing_view(
                    state["model"], state["rows"], spec, enemies, radiant
                )
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
