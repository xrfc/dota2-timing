"""Local replay map viewer, read-only. Defaults to loopback; no arbitrary file routes."""

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dota_items.data.replay_viewer import ReplayStore, read_json
from dota_items.data.replay_viewer_events import EventEvidence
from dota_items.data.source_io import read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name("replay_viewer_assets")


def make_handler(store, map_path, calibration, names=None):
    map_bytes = read_source_bytes(map_path, max_bytes=32 * 1024**2)
    if hashlib.sha256(map_bytes).hexdigest() != calibration["image_sha256"]:
        raise ValueError("Map image hash mismatch")
    assets = {
        "/": ("text/html; charset=utf-8", (ASSETS / "index.html").read_bytes()),
        "/app.js": ("text/javascript; charset=utf-8", (ASSETS / "app.js").read_bytes()),
        "/style.css": ("text/css; charset=utf-8", (ASSETS / "style.css").read_bytes()),
        "/map.jpg": ("image/jpeg", map_bytes),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            # Local application, not an authenticated multi-user service.
            if self.headers.get("Host") not in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }:
                self.send_error(403)
                return
            parsed = urlsplit(self.path)
            try:
                if parsed.path in assets and not parsed.query:
                    mime, content = assets[parsed.path]
                elif parsed.path == "/api/catalog" and not parsed.query:
                    mime = "application/json"
                    content = json.dumps(
                        {
                            "matches": store.catalog(),
                            "names": names or {},
                            "image_size": calibration["image_size"],
                        }
                    ).encode()
                elif parsed.path in {"/api/timeline", "/api/frame"}:
                    q = parse_qs(parsed.query, strict_parsing=True)
                    allowed = (
                        {"match", "view"}
                        if parsed.path.endswith("timeline")
                        else {"match", "view", "tick", "trail"}
                    )
                    if set(q) != allowed or any(len(v) != 1 for v in q.values()):
                        raise ValueError("Invalid query")
                    mid, view = int(q["match"][0]), q["view"][0]
                    result = (
                        store.timeline(mid, view)
                        if parsed.path.endswith("timeline")
                        else store.frame(mid, view, int(q["tick"][0]), int(q["trail"][0]))
                    )
                    content = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
                    mime = "application/json; charset=utf-8"
                else:
                    self.send_error(404)
                    return
            except (ValueError, KeyError, OSError, TypeError):
                self.send_error(400, "Replay data unavailable or invalid; check frozen inputs")
                return
            self.send_response(200)
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

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "data/replay-quality-2026-10-26-v1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    calibration = read_json(args.root / "map-calibration.json")
    names = {}
    for path in (ROOT / "knowledge/hero-capabilities/heroes").glob("*.json"):
        hero = read_json(path)
        names[str(hero["hero_id"])] = hero["name_zh"]
    handler = make_handler(
        ReplayStore(
            args.root,
            EventEvidence(
                [
                    ROOT / "data/replay-jump-events-2026-10-23-v2",
                    ROOT / "data/replay-expansion-2026-10-26-v1/jump-events",
                ],
                ROOT,
            ),
        ),
        ROOT / "data/map-reference-2026-10-26-v1/gem/assets/maps/Game_map_7.41.jpg",
        calibration,
        names,
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Replay viewer: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
