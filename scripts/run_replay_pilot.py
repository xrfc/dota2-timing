"""Execute a frozen three-match replay pilot; preserve failures and never train."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash, now


def save_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    plan_bytes = read_source_bytes(root / "plan.json")
    plan = parse_source_json(plan_bytes)
    candidates = plan["candidates"]
    if len(candidates) != 3 or len({r["match_id"] for r in candidates}) != 3:
        raise ValueError("Expected three unique frozen candidates")
    for row in candidates:
        if file_hash(Path(row["metadata_path"])) != row["metadata_sha256"]:
            raise ValueError("Metadata hash changed")
    save_new(
        root / "execution.json",
        {
            "started_at": now(),
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "script_sha256": file_hash(Path(__file__)),
            "training_executed": False,
        },
    )
    total = 0
    results = []
    with httpx.Client(timeout=60, follow_redirects=False, proxy="http://127.0.0.1:7890") as client:
        for candidate in candidates:
            mid = candidate["match_id"]
            row = dict(match_id=mid, started_at=now(), attempts=[])
            results.append(row)
            archive = root / f"{mid}.dem.bz2"
            try:
                original = candidate["replay_url"]
                url = urlsplit(original)
                if url.scheme not in ("http", "https") or not any(
                    (url.hostname or "").endswith("." + host)
                    for host in (
                        "valve.net",
                        "dota2.com.cn",
                        "steamcontent.com",
                        "valveusercontent.com",
                    )
                ):
                    raise ValueError("Unexpected replay host")
                # Use advertised transport; replay servers need not support TLS.
                effective = original
                attempt = dict(url=effective, advertised_url=original, started_at=now())
                row["attempts"].append(attempt)
                with client.stream("GET", effective, timeout=120) as response:
                    attempt["http_status"] = response.status_code
                    response.raise_for_status()
                    size = 0
                    with archive.open("xb") as stream:
                        for chunk in response.iter_bytes(1024**2):
                            size += len(chunk)
                            total += len(chunk)
                            if size > plan["max_archive_bytes"] or total > plan["max_total_bytes"]:
                                raise ValueError("Download byte budget exceeded")
                            stream.write(chunk)
                row.update(archive_bytes=size, archive_sha256=file_hash(archive))
                with archive.open("rb") as stream:
                    magic = stream.read(4)
                    if not (magic.startswith(b"BZh") or magic == bytes.fromhex("28b52ffd")):
                        raise ValueError("Not a bzip2 or zstd replay archive")
                workspace = root / "workspaces" / str(mid)
                started = time.monotonic()
                with (root / f"{mid}.prepare.log").open("x") as log:
                    proc = subprocess.run(
                        [
                            sys.executable,
                            "coach.py",
                            "--workspace",
                            str(workspace),
                            "prepare",
                            str(archive),
                        ],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=plan["parse_timeout_seconds"],
                        check=False,
                    )
                row.update(
                    prepare_seconds=time.monotonic() - started,
                    prepare_exit_code=proc.returncode,
                    status="prepared" if proc.returncode == 0 else "parse_failed",
                )
            except (ValueError, OSError, httpx.HTTPError, subprocess.TimeoutExpired) as exc:
                row.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            row["finished_at"] = now()
            save_new(root / f"{mid}.receipt.json", row)
            print(json.dumps(row), flush=True)
    save_new(
        root / "results.json",
        dict(results=results, download_bytes=total, finished_at=now(), training_admission=False),
    )


if __name__ == "__main__":
    main()
