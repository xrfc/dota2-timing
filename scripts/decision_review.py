"""Build five manual review cases from immutable evidence; serve a local case page.

No labels, training, downloads, model predictions or existing-product overwrites.
"""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from dota_items.data.decision_evidence import DecisionEvidenceStore
from dota_items.data.replay_viewer import ReplayStore
from dota_items.data.source_io import parse_source_json, read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name("decision_review_assets")


def _read(path):
    return parse_source_json(read_source_bytes(path))


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def build(output, *, repo=ROOT, plan_path=None, replay_root=None):
    """Seal manual advice before reading any future frames; keep outputs separate."""
    if output.exists():
        raise ValueError("Output exists; use a new versioned directory")
    plan_path = plan_path or repo / "examples/decision-review-cases.json"
    replay_root = replay_root or repo / "data/replay-quality-2026-10-26-v1"
    plan_bytes = read_source_bytes(plan_path)
    plan = parse_source_json(plan_bytes)
    ids = [c["id"] for c in plan["cases"]]
    if (
        plan.get("schema") != "manual-decision-cases/1"
        or not ids
        or len(set(ids)) != len(ids)
        or any(not isinstance(i, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", i) for i in ids)
    ):
        raise ValueError("Invalid manual case plan")
    replay = ReplayStore(replay_root)  # No omniscient events adapter in advice path.
    evidence = DecisionEvidenceStore(replay, repo)
    names = {
        str(h["hero_id"]): h["name_zh"]
        for p in (repo / "knowledge/hero-capabilities/heroes").glob("*.json")
        for h in [_read(p)]
    }
    output.mkdir(parents=True)
    # This copy is the sealed prospective recommendation, not a train label.
    with (output / "advice-plan.json").open("xb") as stream:
        stream.write(plan_bytes)
    advice_sha = hashlib.sha256(plan_bytes).hexdigest()
    seal = {
        "advice_sha256": advice_sha,
        "sealed_at_utc": datetime.now(UTC).isoformat(),
        "future_read_started": False,
        "training_allowed": False,
    }
    _write(output / "advice-seal.json", seal)
    cards = []
    protected = {plan_path: advice_sha}
    for case in plan["cases"]:
        mid, view, tick, slot = (case[k] for k in ("match_id", "view", "tick", "slot"))
        package = evidence.build(mid, view, tick, slot)
        raw_path = Path(package["provenance"]["raw"])
        if not raw_path.is_absolute():
            raw_path = repo / raw_path
        protected[raw_path] = package["provenance"]["raw_sha256"]
        folder = replay_root / "aligned" / str(mid)
        protected[folder / "manifest.json"] = package["provenance"]["manifest_sha256"]
        protected[folder / (view + ".jsonl")] = package["provenance"]["view_sha256"]
        timeline = replay.timeline(mid, view)["frames"]
        prior = [f for f in timeline if tick - 1800 <= f["tick"] < tick]
        history = [
            replay.frame(mid, view, f["tick"], 0) for f in prior[:: max(1, len(prior) // 3)]
        ][-3:]
        cards.append({"case": case, "evidence": package, "past_frames": history})
    _write(
        output / "cases.json",
        {
            "schema": "manual-decision-review/1",
            "names": names,
            "advice_sha256": advice_sha,
            "cards": cards,
        },
    )
    # Strictly later phase. Advice generation above never reads this file/data.
    _write(
        output / "future-read-start.json",
        {"started_at_utc": datetime.now(UTC).isoformat(), "sealed_advice_sha256": advice_sha},
    )
    for case in plan["cases"]:
        mid, tick, view = case["match_id"], case["tick"], case["view"]
        timeline = replay.timeline(mid, view)["frames"]
        # Seconds are pause-sensitive; tick orders samples with repeated game seconds.
        now = next(f["time"] for f in timeline if f["tick"] == tick)
        future = [f for f in timeline if f["tick"] > tick and now < f["time"] <= now + 30]
        selected = (
            [future[i] for i in sorted({0, len(future) // 2, len(future) - 1})] if future else []
        )
        frames = [replay.frame(mid, view, f["tick"], 0) for f in selected]
        target_states = [
            {
                "tick": f["tick"],
                "time": f["time"],
                "target": next(p for p in f["players"] if p["player_slot"] == case["slot"]),
            }
            for f in frames
        ]
        _write(
            output / (case["id"] + "-after.json"),
            {
                "case_id": case["id"],
                "view": view,
                "frames": frames,
                "target_samples": target_states,
                "warning": "Later observed states only; not action correctness or causal benefit.",
                "coverage": "Up to 30 game seconds, three samples; not exhaustive event audit.",
                "sealed_advice_sha256": advice_sha,
            },
        )
    from dota_items.storage import file_hash

    changed = [str(p) for p, h in protected.items() if file_hash(p) != h]
    if changed:
        raise ValueError("Protected evidence changed during case build")
    _write(
        output / "verification.json",
        {
            "cases": len(cards),
            "protected_files": len(protected),
            "protected_unchanged": True,
            "training_allowed": False,
            "advice_sha256": advice_sha,
            "source_files": {str(p): h for p, h in protected.items()},
            "outputs": {p.name: file_hash(p) for p in sorted(output.glob("*.json"))},
            "implementation": {
                str(p.relative_to(repo)): file_hash(p)
                for p in [
                    repo / "scripts/decision_review.py",
                    repo / "src/dota_items/data/decision_evidence.py",
                    repo / "src/dota_items/data/replay_status.py",
                    repo / "src/dota_items/data/replay_viewer.py",
                    repo / "src/dota_items/data/source_io.py",
                ]
            },
        },
    )
    return {"output": str(output), "cases": len(cards), "protected_files": len(protected)}


def make_handler(output, repo=ROOT):
    """Only curated card assets and explicit after files; no arbitrary file access."""
    verification = _read(output / "verification.json")
    for name, expected in verification["outputs"].items():
        if Path(name).name != name:
            raise ValueError("Invalid package path")
        if hashlib.sha256(read_source_bytes(output / name)).hexdigest() != expected:
            raise ValueError("Case output hash mismatch")
    data = _read(output / "cases.json")
    image = repo / "data/map-reference-2026-10-26-v1/gem/assets/maps/Game_map_7.41.jpg"
    calibration = _read(repo / "data/replay-quality-2026-10-26-v1/map-calibration.json")
    map_bytes = read_source_bytes(image, max_bytes=32 * 1024**2)
    if hashlib.sha256(map_bytes).hexdigest() != calibration["image_sha256"]:
        raise ValueError("Map hash mismatch")
    routes = {
        "/": ("text/html; charset=utf-8", (ASSETS / "index.html").read_bytes()),
        "/app.js": ("text/javascript; charset=utf-8", (ASSETS / "app.js").read_bytes()),
        "/style.css": ("text/css; charset=utf-8", (ASSETS / "style.css").read_bytes()),
        "/map.jpg": ("image/jpeg", map_bytes),
        "/api/cases": ("application/json; charset=utf-8", (output / "cases.json").read_bytes()),
    }
    for card in data["cards"]:
        name = card["case"]["id"] + "-after.json"
        routes["/api/" + name] = ("application/json; charset=utf-8", (output / name).read_bytes())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.headers.get("Host") not in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }:
                self.send_error(403)
                return
            path = urlsplit(self.path)
            if path.query or path.path not in routes:
                self.send_error(404)
                return
            mime, content = routes[path.path]
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; "
                "style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    if args.build:
        print(json.dumps(build(args.output), ensure_ascii=False), flush=True)
    if args.serve:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.output))
        print(f"Decision review: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    if not args.build and not args.serve:
        parser.error("Choose --build or --serve")


if __name__ == "__main__":
    main()
