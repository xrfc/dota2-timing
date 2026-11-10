"""Parser v3 second pass: per-second state from kept demos (docs/parser-v3-design.md, U130).

    PYTHONPATH=data/replay-pilot-2026-10-22/compat-v1:src .venv/bin/python \
        scripts/extract_state_v3.py run --root data/demos-2026-11
    PYTHONPATH=src .venv/bin/python scripts/extract_state_v3.py report --root data/demos-2026-11

Reads `<root>/demos/<id>.dem.bz2`, writes `<root>/state-v3/<id>.jsonl.gz` (first line a
header, then one JSON object per game second) and a receipt. When the collector's parse
(`<root>/parsed/<id>.normalized.json.gz`) exists, the receipt also says how many combat-log
casts started a cooldown in the captured state. Resumable; never overwrites; one match at a
time (about 40 s and 0.4 GB of memory each), so it can run next to the collector.
"""

import argparse
import fcntl
import gzip
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dota_items.sources.gem_capture_v3 import CAPTURE_VERSION, capture_state_v3, check_cooldowns
from dota_items.sources.gem_replay import prepared_demo


def now():
    return datetime.now(UTC).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temp.replace(path)


def extract(root, mid, capture=capture_state_v3):
    demo = root / "demos" / f"{mid}.dem.bz2"
    out_dir = root / "state-v3"
    target = out_dir / f"{mid}.jsonl.gz"
    if target.exists():
        raise ValueError(f"{target} exists; not overwriting")
    started = time.time()
    with prepared_demo(demo, out_dir / ".unpack") as raw:
        header, rows = capture(raw)
    header = {**header, "match_id": mid}
    part = target.with_name(target.name + ".part")
    with gzip.open(part, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(header, ensure_ascii=False) + "\n")
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    part.replace(target)
    receipt = {
        "match_id": mid,
        "schema": CAPTURE_VERSION,
        "status": "extracted",
        "seconds": len(rows),
        "bytes": target.stat().st_size,
        "elapsed_seconds": round(time.time() - started, 1),
        "finished_at": now(),
    }
    parsed = root / "parsed" / f"{mid}.normalized.json.gz"
    if parsed.exists():
        with gzip.open(parsed, "rt", encoding="utf-8") as stream:
            combat = json.load(stream)["context"]["channels"]["combat_log"]
        receipt["cooldown_check"] = check_cooldowns(rows, combat)
    return receipt


def run(args):
    root = args.root.resolve()
    lock = (root / ".state-v3.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another state-v3 extraction is running on this folder") from None
    receipts = root / "state-v3" / "receipts"
    done = {p.stem for p in receipts.glob("*.json")} if receipts.exists() else set()
    demos = sorted((root / "demos").glob("*.dem.bz2"), reverse=True)
    todo = [int(p.name.split(".")[0]) for p in demos if p.name.split(".")[0] not in done]
    if args.match:
        todo = [m for m in todo if m in set(args.match)]
    for count, mid in enumerate(todo[: args.limit] if args.limit else todo, 1):
        try:
            receipt = extract(root, mid)
        except (ValueError, OSError) as error:
            receipt = {
                "match_id": mid,
                "status": "failed",
                "error": str(error)[:300],
                "finished_at": now(),
            }
        write_json(receipts / f"{mid}.json", receipt)
        check = receipt.get("cooldown_check") or {}
        print(
            f"{now()} {mid} {receipt['status']} {receipt.get('elapsed_seconds', '')}s "
            f"冷却核对 {check.get('cooldown_seen')}/{check.get('checked')} [{count}/{len(todo)}]",
            flush=True,
        )


def report(args):
    receipts = [
        json.loads(p.read_text()) for p in (args.root / "state-v3" / "receipts").glob("*.json")
    ]
    ok = [r for r in receipts if r["status"] == "extracted"]
    checks = [r["cooldown_check"] for r in ok if r.get("cooldown_check")]
    checked = sum(c["checked"] for c in checks)
    seen = sum(c["cooldown_seen"] for c in checks)
    print(
        json.dumps(
            {
                "extracted": len(ok),
                "statuses": dict(Counter(r["status"] for r in receipts)),
                "mean_mb": round(sum(r["bytes"] for r in ok) / len(ok) / 1e6, 2) if ok else None,
                "mean_seconds": round(sum(r["elapsed_seconds"] for r in ok) / len(ok), 1)
                if ok
                else None,
                "cooldown_check": {
                    "casts": checked,
                    "cooldown_seen": seen,
                    "share": round(seen / checked, 4) if checked else None,
                },
            },
            ensure_ascii=False,
            indent=1,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--root", type=Path, required=True)
    r.add_argument("--limit", type=int, default=0, help="stop after this many matches (0 = all)")
    r.add_argument("--match", type=int, action="append", default=[])
    p = sub.add_parser("report")
    p.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    run(args) if args.command == "run" else report(args)


if __name__ == "__main__":
    main()
