"""Bounded, frozen replay expansion using existing metadata and isolated Gem."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from dota_items.data.source_io import parse_source_json, read_source_bytes

REPO = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return parse_source_json(read_source_bytes(Path(path)))


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def validate_url(url):
    parts = urlsplit(url)
    hosts = ("valve.net", "dota2.com.cn", "steamcontent.com", "valveusercontent.com")
    if (
        parts.scheme not in ("http", "https")
        or parts.username
        or parts.password
        or parts.port not in (None, 80, 443)
        or not any((parts.hostname or "").endswith("." + host) for host in hosts)
    ):
        raise ValueError("Unexpected replay URL")


def validate(plan):
    rows = plan["candidates"]
    if not 1 <= len(rows) <= 10 or len({r["match_id"] for r in rows}) != len(rows):
        raise ValueError("Expected 1 to 10 unique candidates")
    for r in rows:
        p = Path(r["metadata_path"])
        if digest(p) != r["metadata_sha256"]:
            raise ValueError("Metadata changed")
        data = read(p)
        if data["match_id"] != r["match_id"] or data.get("replay_url") != r["replay_url"]:
            raise ValueError("Metadata identity or URL mismatch")
        validate_url(r["replay_url"])
    compat = Path(plan["compat"])
    if digest(compat / "manifest.json") != plan["compat_manifest_sha256"]:
        raise ValueError("Compatibility manifest changed")
    for name, expected in read(compat / "manifest.json")["patched"].items():
        if digest(compat / "gem" / name) != expected:
            raise ValueError("Compatibility source changed")
    for name, expected in plan["implementation"].items():
        if digest(REPO / name) != expected:
            raise ValueError("Implementation changed")
    if not 0 < plan["max_archive_bytes"] <= 512 * 1024**2:
        raise ValueError("Archive limit invalid")
    if not 0 < plan["max_total_bytes"] <= 2 * 1024**3:
        raise ValueError("Total limit invalid")
    if not 0 < plan["parse_timeout_seconds"] <= 600:
        raise ValueError("Parse timeout invalid")


def copy_download(response, archive, budget, per_file):
    size = 0
    with archive.open("xb") as stream:
        for block in response.iter_bytes(1024**2):
            budget["bytes_received"] += len(block)
            size += len(block)
            if size > per_file or budget["bytes_received"] > budget["limit"]:
                raise ValueError("Download byte budget exceeded")
            stream.write(block)
    with archive.open("rb") as stream:
        magic = stream.read(4)
    if not (magic.startswith(b"BZh") or magic == bytes.fromhex("28b52ffd")):
        raise ValueError("Unknown compression magic")
    return size


def child(command, log, env, timeout):
    with log.open("x") as stream:
        result = subprocess.run(
            command,
            cwd=REPO,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    if result.returncode:
        raise ValueError(f"Child failed ({result.returncode}); see {log.name}")


def run(root):
    plan = read(root / "plan.json")
    validate(plan)
    if shutil.disk_usage(root).free < 10 * 1024**3:
        raise ValueError("Less than 10 GiB free")
    save(
        root / "execution.json",
        {
            "plan_sha256": digest(root / "plan.json"),
            "script_sha256": digest(__file__),
            "started_at": time.time(),
        },
    )
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join([plan["compat"], str(REPO / "src")]),
    }
    child(
        [
            sys.executable,
            "-c",
            "import gem; from pathlib import Path; "
            f'assert Path(gem.__file__).resolve().parent == Path({plan["compat"]!r}) / "gem"',
        ],
        root / "import-check.log",
        env,
        30,
    )
    budget = {"bytes_received": 0, "limit": plan["max_total_bytes"]}
    rows, stop, consecutive = [], None, 0
    with httpx.Client(
        proxy="http://127.0.0.1:7890",
        follow_redirects=False,
        timeout=httpx.Timeout(120, connect=30),
    ) as client:
        for candidate in plan["candidates"]:
            mid = candidate["match_id"]
            if stop:
                row = {"match_id": mid, "status": "not_attempted", "reason": stop}
                rows.append(row)
                save(root / f"{mid}.receipt.json", row)
                continue
            validate(plan)
            if shutil.disk_usage(root).free < 5 * 1024**3:
                stop = "disk_reserve"
                row = {"match_id": mid, "status": "not_attempted", "reason": stop}
                rows.append(row)
                save(root / f"{mid}.receipt.json", row)
                continue
            row = {"match_id": mid, "started_at": time.time(), "status": "started"}
            rows.append(row)
            save(
                root / f"{mid}.request.json",
                {"url": candidate["replay_url"], "reserved_requests": 1, "started_at": time.time()},
            )
            archive = root / f"{mid}.dem.bz2"
            stage = "download"
            try:
                with client.stream("GET", candidate["replay_url"]) as response:
                    row["http_status"] = response.status_code
                    response.raise_for_status()
                    row["archive_bytes"] = copy_download(
                        response, archive, budget, plan["max_archive_bytes"]
                    )
                row["archive_sha256"] = digest(archive)
                print(f"{mid} downloaded {row['archive_bytes']} bytes; parsing", flush=True)
                stage = "parse"
                ws = root / "workspaces" / str(mid)
                child(
                    [
                        sys.executable,
                        "-m",
                        "dota_items.workflow.cli",
                        "--workspace",
                        str(ws),
                        "prepare",
                        str(archive),
                    ],
                    root / f"{mid}.prepare.log",
                    env,
                    plan["parse_timeout_seconds"],
                )
                stage = "export"
                out = root / "exports" / str(mid)
                child(
                    [
                        sys.executable,
                        "scripts/audit_replay_tracks.py",
                        "--workspace",
                        str(ws),
                        "--metadata",
                        candidate["metadata_path"],
                        "--match-id",
                        str(mid),
                        "--output",
                        str(out),
                    ],
                    root / f"{mid}.audit.log",
                    env,
                    180,
                )
                a = read(out / "audit.json")
                row.update(
                    status="exported",
                    trajectory_rows=sum(p["rows"] for p in a["players"]),
                    visibility_rows=a["channel_rows"]["hero_visibility_events"],
                    audit_sha256=digest(out / "audit.json"),
                    max_gap_seconds=max(p["max_gap_seconds"] or 0 for p in a["players"]),
                    quarantined=a["quality"]["quarantined"],
                )
                consecutive = 0
            except (ValueError, OSError, httpx.HTTPError, subprocess.TimeoutExpired) as exc:
                row.update(
                    status="failed", stage=stage, error_type=type(exc).__name__, error=str(exc)
                )
                consecutive += 1
                if stage == "download" and row.get("http_status") != 404:
                    stop = "download_error_requires_review"
                elif consecutive >= 3:
                    stop = "three_consecutive_failures"
            row["finished_at"] = time.time()
            row["bytes_received_cumulative"] = budget["bytes_received"]
            save(root / f"{mid}.receipt.json", row)
            print(json.dumps(row), flush=True)
    validate(plan)
    result = {
        "results": rows,
        "bytes_received": budget["bytes_received"],
        "requests_reserved": len(list(root.glob("*.request.json"))),
        "training_admission": False,
        "semantic_review_required": True,
        "finished_at": time.time(),
        "stop_reason": stop,
    }
    save(root / "results.json", result)


def freeze(root, metadata, prior, compat):
    excluded = {r["match_id"] for r in read(prior)["candidates"]}
    files = sorted(
        (p for p in metadata.glob("*.json") if p.stem.isdigit() and int(p.stem) not in excluded),
        key=lambda p: int(p.stem),
        reverse=True,
    )
    candidates = []
    for p in files[:10]:
        d = read(p)
        candidates.append(
            {
                "match_id": int(p.stem),
                "metadata_path": str(p.resolve()),
                "metadata_sha256": digest(p),
                "replay_url": d.get("replay_url"),
            }
        )
    sources = [
        *sorted((REPO / "src").rglob("*.py")),
        Path(__file__).resolve(),
        REPO / "scripts/audit_replay_tracks.py",
    ]
    plan = {
        "schema": "replay-expansion/1",
        "created_at": time.time(),
        "selection": "Next 10 descending cached IDs excluding prior pilot; no replacements",
        "source_inventory": {p.name: digest(p) for p in files},
        "prior_plan_sha256": digest(prior),
        "candidates": candidates,
        "compat": str(compat.resolve()),
        "compat_manifest_sha256": digest(compat / "manifest.json"),
        "implementation": {str(p.relative_to(REPO)): digest(p) for p in sources},
        "max_archive_bytes": 512 * 1024**2,
        "max_total_bytes": 2 * 1024**3,
        "parse_timeout_seconds": 600,
        "max_http_requests": 10,
        "training_admission": False,
        "selection_is_representative": False,
    }
    validate(plan)
    root.mkdir(parents=True, exist_ok=False)
    save(root / "plan.json", plan)
    print(json.dumps({"frozen": len(candidates), "root": str(root)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "run"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--metadata",
        type=Path,
        default=REPO / "data/purchase-until-daily-2026-10-22-proxy-resume-01/matches",
    )
    parser.add_argument(
        "--prior", type=Path, default=REPO / "data/replay-pilot-2026-10-22/plan.json"
    )
    parser.add_argument(
        "--compat", type=Path, default=REPO / "data/replay-pilot-2026-10-22/compat-v1"
    )
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.root.resolve(), args.metadata, args.prior, args.compat)
    else:
        run(args.root.resolve())
