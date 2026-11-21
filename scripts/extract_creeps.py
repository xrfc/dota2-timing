"""Side pass to parser v3: creeps, and with `--kind extras` also watchers, outposts, scan.

`--kind creeps` (U153, the default) writes `creeps-v1/`; `--kind extras` (U154) writes
`extras-v1/` with the creeps plus who holds each Watcher and outpost and the Scan state
(sources.gem_capture_extras). The rest of this text describes the creeps kind; extras
works the same way with its own folder.

Every lane creep's position per second (U153).

    PYTHONPATH=data/replay-pilot-2026-10-22/compat-v1:src .venv/bin/python \
        scripts/extract_creeps.py run --root data/demos-2026-11 --with-wards --workers 6

Reads `<root>/demos/<id>.dem.bz2`, writes `<root>/creeps-v1/<id>.jsonl.gz` (a header line,
then one JSON object per game second: `{"t", "creeps": [[team, x, y], ...]}`) and a
receipt. Resumable; never overwrites. `--with-wards` limits the run to matches that
already have the ward cache of `gank_review.py build`, which is what the vision check
uses; `--match` names matches; without either every demo is done. Several workers may run
at once, each unpacking into its own folder.
"""

import argparse
import gzip
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from dota_items.sources.gem_capture_creeps import CAPTURE_VERSION, capture_creeps
from dota_items.sources.gem_capture_extras import CAPTURE_VERSION as EXTRAS_VERSION
from dota_items.sources.gem_capture_extras import capture_extras
from dota_items.sources.gem_replay import prepared_demo


def now():
    return datetime.now(UTC).isoformat()


KINDS = {
    "creeps": ("creeps-v1", CAPTURE_VERSION, capture_creeps),
    "extras": ("extras-v1", EXTRAS_VERSION, capture_extras),
}


def extract(root, mid, kind="creeps"):
    folder, schema, capture = KINDS[kind]
    out_dir = root / folder
    target = out_dir / f"{mid}.jsonl.gz"
    if target.exists():
        raise ValueError(f"{target} exists; not overwriting")
    started = time.time()
    with prepared_demo(root / "demos" / f"{mid}.dem.bz2", out_dir / ".unpack" / str(mid)) as raw:
        header, rows = capture(raw)
    if header.get("match_id") != mid:
        raise ValueError(f"{mid}: {kind} capture belongs to match {header.get('match_id')}")
    part = target.with_name(target.name + ".part")
    with gzip.open(part, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(header) + "\n")
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    part.replace(target)
    return {
        "match_id": mid,
        "schema": schema,
        "status": "extracted",
        "seconds": len(rows),
        "bytes": target.stat().st_size,
        "elapsed_seconds": round(time.time() - started, 1),
        "finished_at": now(),
    }


def attempt(root, mid, kind="creeps"):
    try:
        return extract(root, mid, kind)
    except (ValueError, OSError) as error:
        return {
            "match_id": mid,
            "status": "failed",
            "error": str(error)[:300],
            "finished_at": now(),
        }


def run(args):
    root = args.root.resolve()
    receipts = root / KINDS[args.kind][0] / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    done = {p.stem for p in receipts.glob("*.json")}
    todo = sorted(
        int(p.name.split(".")[0])
        for p in (root / "demos").glob("*.dem.bz2")
        if p.name.split(".")[0] not in done
    )
    if args.with_wards:
        cached = {int(p.stem) for p in (root / "gank-clip-inputs-v1").glob("*.pkl")}
        todo = [m for m in todo if m in cached]
    if args.match:
        todo = [m for m in todo if m in set(args.match)]
    if args.limit:
        todo = todo[: args.limit]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(attempt, root, mid, args.kind) for mid in todo]
        for count, job in enumerate(as_completed(jobs), 1):
            receipt = job.result()
            path = receipts / f"{receipt['match_id']}.json"
            path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n", "utf-8")
            print(
                f"{now()} {receipt['match_id']} {receipt['status']} "
                f"{receipt.get('elapsed_seconds', '')}s [{count}/{len(todo)}]",
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--root", type=Path, required=True)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--match", type=int, action="append", default=[])
    r.add_argument("--with-wards", action="store_true")
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--kind", choices=sorted(KINDS), default="creeps")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
