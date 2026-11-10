"""Collect and parse Dota 2 demos for all heroes, unattended (U128, U129).

Start it, leave it running, check progress any time:

    PYTHONPATH=src .venv/bin/python scripts/collect_demos.py run --root data/demos-2026-11
    PYTHONPATH=src .venv/bin/python scripts/collect_demos.py report --root data/demos-2026-11

What one match goes through:
1. Discovery: recent ranked All Pick matches on the current patch, lobby average Divine or
   higher (rank tier >= 70), at least 15 minutes, no hero filter (OpenDota explorer).
2. Metadata: one OpenDota request (`/api/matches/<id>`), anonymous, through the shared
   rolling budget (1,900 requests a day, 1.5 s apart, 24 h pause after a 429).
3. Demo: downloaded from Valve's replay server (not counted against OpenDota) and kept.
4. Parse: the pinned Gem parser (`dota_items.workflow.cli prepare`). Every parsed channel,
   combat log included, is kept gzip-compressed as `parsed/<id>.normalized.json.gz`.
5. Compaction: the parser's intermediate folder for that match (about 0.8 GB of duplicate
   uncompressed JSON) is removed only after the compressed copy reads back identical.
   `--keep-workspace` keeps it instead.

It resumes where it stopped (a receipt per match), never overwrites a file, stops on its
own at the target, when the disk falls below the reserve, or after repeated download
errors, and waits out OpenDota's daily budget instead of failing. Nothing is trained and
nothing is uploaded. Repeat `--hero <id>` to top up rare heroes later.
"""

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from dota_items.data.patch_time import OFFICIAL_PATCH_URL
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget

REPO = Path(__file__).resolve().parents[1]
GEM_COMPAT = REPO / "data/replay-pilot-2026-10-22/compat-v1"
BUDGETS = {
    "proxy": REPO / "data/purchase-proxy-trial-2026-10-15/request-budget.json",
    "direct": REPO / "reports/collection-runtime/request-budget.json",
}
PROXY = "http://127.0.0.1:7890"
MIN_RANK, MIN_DURATION, LOBBY, MODE = 70, 900, 7, 22
ID_SPAN, ID_RATE_PER_HOUR, PAGE = 1_000_000, 52_000, 100
REPLAY_HOSTS = ("valve.net", "dota2.com.cn", "steamcontent.com", "valveusercontent.com")
MAX_DEMO_BYTES = 512 * 1024**2
DISK_RESERVE = 30 * 1024**3
IDLE_SECONDS = 1800
OK = "parsed"
# Long games give a normalized file above the cleaning step's 256 MiB input limit. The full
# normalized file is already written by then; the collector keeps it and skips cleaning.
SIZE_LIMIT_ERROR = "Normalized JSON exceeds 256 MiB input limit"


def now():
    return datetime.now(UTC).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temp.replace(path)


def log(root, message):
    line = f"{now()} {message}"
    print(line, flush=True)
    with (root / "log.txt").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def receipts(root):
    out = {}
    for path in (root / "receipts").glob("*.json"):
        out[int(path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    return out


def meets_rank(record):
    rank = record.get("avg_rank_tier")
    return isinstance(rank, (int, float)) and rank >= MIN_RANK


def counts_toward_target(receipt):
    return receipt["status"] == OK and meets_rank(receipt)


# Discovery -------------------------------------------------------------------------------
def latest_patch_start(client):
    """Release time of the newest patch in Valve's official list."""
    patches = client.get(OFFICIAL_PATCH_URL).raise_for_status().json()["patches"]
    latest = max(patches, key=lambda p: p["patch_timestamp"])
    return latest["patch_number"], int(latest["patch_timestamp"])


def discovery_sql(lower, upper, cursor, heroes):
    hero_clause = ""
    if heroes:
        parts = [f"{h}=ANY(radiant_team) OR {h}=ANY(dire_team)" for h in heroes]
        hero_clause = " AND (" + " OR ".join(parts) + ")"
    return (
        "SELECT match_id,start_time,duration,avg_rank_tier FROM public_matches "
        f"WHERE match_id>{cursor - ID_SPAN} AND match_id<{cursor} "
        f"AND start_time>={lower} AND start_time<{upper} "
        f"AND duration>={MIN_DURATION} AND lobby_type={LOBBY} AND game_mode={MODE} "
        f"AND avg_rank_tier>={MIN_RANK}{hero_clause} ORDER BY match_id DESC LIMIT {PAGE}"
    )


def explorer(client, sql):
    response = client.get("https://api.opendota.com/api/explorer", params={"sql": sql})
    response.raise_for_status()
    payload = response.json()
    if payload.get("err") or not isinstance(payload.get("rows"), list):
        raise ValueError(f"Explorer query failed: {payload.get('err')}")
    return payload["rows"]


def discover(client, lower, upper, seen, heroes, want, max_pages=6):
    """Newest-first match rows in [lower, upper) that are not yet seen."""
    anchor = explorer(client, "SELECT max(match_id) AS max_id FROM public_matches")
    max_id = anchor[0]["max_id"]
    hours_back = max(0, (time.time() - upper) / 3600)
    cursor = int(max_id - ID_RATE_PER_HOUR * hours_back)
    found, empty = [], 0
    for _ in range(max_pages):
        rows = explorer(client, discovery_sql(lower, upper, cursor, heroes))
        for row in rows:
            if row["match_id"] not in seen and lower <= row["start_time"] < upper:
                seen.add(row["match_id"])
                found.append(row)
        if len(found) >= want:
            break
        empty = 0 if rows else empty + 1
        if empty == 3:
            break
        cursor = min(r["match_id"] for r in rows) if rows else cursor - ID_SPAN + 1
    return found[:want]


# One match ---------------------------------------------------------------------------------
def check_metadata(meta, match_id, patch_start):
    """Reasons to skip a match, from its OpenDota record (empty list means usable)."""
    if not isinstance(meta, dict) or meta.get("match_id") != match_id:
        raise ValueError("OpenDota returned another match")
    reasons = []
    players = meta.get("players") or []
    heroes = [p.get("hero_id") for p in players]
    if len(players) != 10 or len(set(heroes)) != 10 or not all(heroes):
        reasons.append("players_incomplete")
    if meta.get("lobby_type") != LOBBY or meta.get("game_mode") != MODE:
        reasons.append("not_ranked_all_pick")
    if (meta.get("duration") or 0) < MIN_DURATION:
        reasons.append("too_short")
    if (meta.get("start_time") or 0) < patch_start + 3600:
        reasons.append("before_patch")
    parts = urlsplit(meta.get("replay_url") or "")
    if parts.scheme not in ("http", "https") or not any(
        (parts.hostname or "").endswith("." + host) for host in REPLAY_HOSTS
    ):
        reasons.append("no_replay_url")
    return reasons


def download(client, url, target):
    part = target.with_name(target.name + ".part")
    size = 0
    with client.stream("GET", url) as response:
        if response.status_code == 404:
            return None
        response.raise_for_status()
        with part.open("wb") as stream:
            for chunk in response.iter_bytes(1024 * 1024):
                size += len(chunk)
                if size > MAX_DEMO_BYTES:
                    raise ValueError("Demo larger than the limit")
                stream.write(chunk)
    part.replace(target)
    return size


def parse(demo, workspace, timeout, runner=subprocess.run):
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join([str(GEM_COMPAT), str(REPO / "src")]),
    }
    command = [sys.executable, "-m", "dota_items.workflow.cli", "--workspace", str(workspace)]
    result = runner(
        [*command, "prepare", str(demo)],
        env=env,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )
    found = sorted(workspace.glob("cache/matches/*/normalized.json"))
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        only_size = SIZE_LIMIT_ERROR in output and output.count('"status": "failed"') == 1
        if not (only_size and len(found) == 1 and _complete_json(found[0])):
            raise ValueError(f"Parser failed: {output[-400:]}")
        return found[0], "normalized_only_over_256mib"
    if len(found) != 1:
        raise ValueError(f"Expected one parsed file, found {len(found)}")
    return found[0], "prepared"


def _complete_json(path):
    """Cheap completeness check for a large JSON object: it ends with a closing brace."""
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 64))
        return stream.read().rstrip().endswith(b"}")


def compress(source, target):
    """gzip `source` to `target`, then confirm the compressed copy reads back identical."""
    part = target.with_name(target.name + ".part")
    with source.open("rb") as raw, gzip.open(part, "wb", compresslevel=6) as packed:
        shutil.copyfileobj(raw, packed, 1024 * 1024)
    expected = sha256(source)
    digest = hashlib.sha256()
    with gzip.open(part, "rb") as packed:
        for block in iter(lambda: packed.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("Compressed copy differs from the parsed file")
    part.replace(target)
    return expected


def process(root, row, api, valve, patch_start, args, runner=subprocess.run):
    mid = row["match_id"]
    receipt = {"match_id": mid, "avg_rank_tier": row.get("avg_rank_tier"), "started_at": now()}
    if not meets_rank(receipt):
        return {**receipt, "status": "skipped", "reasons": ["rank_below_threshold_or_unknown"]}
    meta_path = root / "meta" / f"{mid}.json"
    if meta_path.exists():  # resumed after an interruption: reuse, do not request again
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        response = api.get(f"https://api.opendota.com/api/matches/{mid}")
        if response.status_code >= 500 or response.status_code in (401, 403):
            raise ValueError(f"OpenDota service error {response.status_code}")
        if response.status_code != 200:
            return {**receipt, "status": "skipped", "reasons": [f"http_{response.status_code}"]}
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_bytes(response.content)
        meta = response.json()
    receipt["heroes"] = sorted(p.get("hero_id") for p in meta.get("players") or [])
    receipt["start_time"] = meta.get("start_time")
    reasons = check_metadata(meta, mid, patch_start)
    if reasons:
        return {**receipt, "status": "skipped", "reasons": reasons}
    demo = root / "demos" / f"{mid}.dem.bz2"
    demo.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    size = demo.stat().st_size if demo.exists() else download(valve, meta["replay_url"], demo)
    if size is None:
        return {**receipt, "status": "skipped", "reasons": ["demo_not_found"]}
    receipt.update(
        demo_bytes=size, demo_sha256=sha256(demo), download_seconds=round(time.time() - started, 1)
    )
    workspace = root / "work" / str(mid)
    if workspace.exists():  # half-finished parse from an interrupted run
        shutil.rmtree(workspace)
    started = time.time()
    try:
        parsed, parse_mode = parse(demo, workspace, args.parse_timeout, runner)
    except (ValueError, subprocess.TimeoutExpired) as error:
        return {**receipt, "status": "parse_failed", "error": str(error)[:300]}
    receipt["parse_seconds"] = round(time.time() - started, 1)
    receipt["parse_mode"] = parse_mode
    target = root / "parsed" / f"{mid}.normalized.json.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt["parsed_sha256"] = compress(parsed, target)
    receipt["parsed_gz_bytes"] = target.stat().st_size
    if not args.keep_workspace:
        work_root = (root / "work").resolve()
        if workspace.resolve().parent != work_root:
            raise ValueError("Refusing to remove a folder outside the work directory")
        shutil.rmtree(workspace)
        receipt["workspace_removed"] = True
    return {**receipt, "status": OK, "finished_at": now()}


# Main loop ---------------------------------------------------------------------------------
def clients(route, budget):
    proxy = PROXY if route == "proxy" else None
    api = httpx.Client(
        trust_env=False,
        timeout=60,
        follow_redirects=False,
        proxy=proxy,
        event_hooks={"request": [budget.before], "response": [budget.after]},
    )
    plain = httpx.Client(
        trust_env=False, timeout=httpx.Timeout(120, connect=30), follow_redirects=False, proxy=proxy
    )
    return api, plain


def run(args):
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if os.environ.get("OPENDOTA_API_KEY"):
        raise SystemExit("Anonymous only; unset OPENDOTA_API_KEY")
    lock = (root / ".lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another collector is already running on this folder") from None
    config = {
        "schema": "demo-collection/1",
        "decisions": "U110-U112, U116, U128, U129",
        "target": args.target,
        "min_avg_rank_tier": MIN_RANK,
        "min_duration_s": MIN_DURATION,
        "lobby_type": LOBBY,
        "game_mode": MODE,
        "hero_filter": sorted(args.hero),
        "max_age_hours": args.max_age_hours,
        "min_age_hours": args.min_age_hours,
        "keep_workspace": args.keep_workspace,
        "retry_failed": args.retry_failed,
        "training_allowed": False,
        "script_sha256": sha256(__file__),
    }
    history = root / "runs.jsonl"
    with history.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({**config, "started_at": now()}, ensure_ascii=False) + "\n")
    # The OpenDota budget file is shared with the other collectors; hold their lock too.
    runtime = REPO / "reports/collection-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    budget_lock = (runtime / "request-budget.lock").open("a")
    try:
        fcntl.flock(budget_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another OpenDota collector is running; try again later") from None
    budget = RequestBudget(BUDGETS[args.route])
    api, plain = clients(args.route, budget)
    failures = 0
    try:
        patch, patch_start = latest_patch_start(plain)
        log(
            root,
            f"patch {patch}; target {args.target} parsed matches with avg_rank_tier >= {MIN_RANK}",
        )
        if args.retry_failed:
            retry(root, api, plain, patch_start, args)
        log(root, progress(root, args.target))
        while True:
            done = receipts(root)
            parsed = sum(map(counts_toward_target, done.values()))
            if parsed >= args.target:
                log(root, f"target reached: {parsed} parsed")
                break
            if shutil.disk_usage(root).free < DISK_RESERVE:
                log(root, "stopping: less than 30 GiB free")
                break
            upper = int(time.time() - args.min_age_hours * 3600)
            lower = max(patch_start + 3600, int(time.time() - args.max_age_hours * 3600))
            try:
                rows = discover(api, lower, upper, set(done), sorted(args.hero), want=50)
            except BudgetPaused as pause:
                wait_out(root, budget, pause, args)
                continue
            except (httpx.HTTPError, OSError, ValueError) as error:
                failures += 1
                log(root, f"discovery error {type(error).__name__}: {error}")
                if not back_off(root, failures, args):
                    return
                continue
            if not rows:
                if args.once:
                    break
                log(root, f"no new matches yet; waiting {IDLE_SECONDS // 60} minutes")
                time.sleep(IDLE_SECONDS)
                continue
            for row in rows:
                if parsed >= args.target:
                    break
                try:
                    receipt = process(root, row, api, plain, patch_start, args)
                except BudgetPaused as pause:
                    wait_out(root, budget, pause, args)
                    break
                except (httpx.HTTPError, OSError, ValueError) as error:
                    failures += 1
                    log(root, f"{row['match_id']} error {type(error).__name__}: {error}")
                    if not back_off(root, failures, args):
                        return
                    break  # rediscover after waiting; this match was not marked done
                failures = 0
                write_new(root / "receipts" / f"{row['match_id']}.json", receipt)
                parsed += counts_toward_target(receipt)
                log(root, f"{row['match_id']} {receipt['status']} {receipt.get('reasons', '')}")
                log(root, progress(root, args.target))
            if args.once:
                break
    finally:
        api.close()
        plain.close()
        write_new(root / "summary.json", summary(root))


def retry(root, api, plain, patch_start, args, runner=subprocess.run):
    """Process parse failures again; their metadata and demo are reused, not downloaded."""
    done = receipts(root)
    parsed = sum(map(counts_toward_target, done.values()))
    for mid, old in sorted(done.items()):
        if parsed >= args.target:
            break
        if old["status"] != "parse_failed" or not meets_rank(old):
            continue
        receipt = process(
            root,
            {"match_id": mid, "avg_rank_tier": old.get("avg_rank_tier")},
            api,
            plain,
            patch_start,
            args,
            runner,
        )
        receipt["retried_from"] = old.get("error", "")[:200]
        write_new(root / "receipts" / f"{mid}.json", receipt)
        parsed += counts_toward_target(receipt)
        log(root, f"{mid} retried: {receipt['status']}")


MAX_FAILURES = 8


def back_off(root, failures, args, sleep=time.sleep):
    """Wait 1, 2, 4, 8 ... (at most 30) minutes after network errors; False means stop."""
    if failures >= MAX_FAILURES or args.once:
        log(root, f"stopping after {failures} errors in a row; check log.txt and rerun")
        return False
    minutes = min(30, 2 ** (failures - 1))
    log(root, f"network trouble ({failures} in a row); waiting {minutes} minutes, then retrying")
    sleep(minutes * 60)
    return True


def wait_out(root, budget, pause, args):
    until = budget.state.get("blocked_until", time.time() + 3600)
    if args.once:
        raise SystemExit(f"OpenDota budget paused ({pause}); rerun later")
    minutes = max(1, int((until - time.time()) / 60))
    log(root, f"OpenDota budget paused ({pause}); sleeping {minutes} minutes")
    time.sleep(max(60, until - time.time()))


def progress(root, target):
    """One line: parsed so far, skips, average time per match and the time still needed."""
    done = list(receipts(root).values())
    parsed = [r for r in done if counts_toward_target(r)]
    secs = [r.get("download_seconds", 0) + r.get("parse_seconds", 0) for r in parsed[-50:]]
    each = sum(secs) / len(secs) if secs else 0
    left = max(0, target - len(parsed)) * each / 3600
    return (
        f"进度 {len(parsed)}/{target}（跳过 {sum(r['status'] == 'skipped' for r in done)}，"
        f"失败 {sum(r['status'] == 'parse_failed' for r in done)}）；"
        f"每场约 {each:.0f} 秒，预计还要 {left:.1f} 小时"
    )


def summary(root):
    done = receipts(root)
    saved = [r for r in done.values() if r["status"] == OK]
    parsed = [r for r in saved if counts_toward_target(r)]
    heroes = Counter(h for r in parsed for h in r.get("heroes", []))
    return {
        "updated_at": now(),
        "parsed": len(parsed),
        "parsed_total": len(saved),
        "parsed_outside_rank": len(saved) - len(parsed),
        "statuses": dict(Counter(r["status"] for r in done.values())),
        "skip_reasons": dict(Counter(x for r in done.values() for x in r.get("reasons", []))),
        "demo_gb": round(sum(r.get("demo_bytes", 0) for r in saved) / 1024**3, 2),
        "parsed_gb": round(sum(r.get("parsed_gz_bytes", 0) for r in saved) / 1024**3, 2),
        "mean_parse_seconds": round(sum(r["parse_seconds"] for r in parsed) / len(parsed), 1)
        if parsed
        else None,
        "heroes_seen": len(heroes),
        "rarest_heroes": sorted(heroes.items(), key=lambda kv: kv[1])[:15],
        "hero_games": dict(sorted(heroes.items())),
    }


def report(args):
    result = summary(args.root.resolve())
    shown = {k: v for k, v in result.items() if k != "hero_games"}
    print(json.dumps(shown, ensure_ascii=False, indent=1))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="collect until the target is reached")
    r.add_argument("--root", type=Path, required=True)
    r.add_argument("--target", type=int, default=1500)
    r.add_argument("--hero", type=int, action="append", default=[], help="top up one hero")
    r.add_argument("--route", choices=("proxy", "direct"), default="proxy")
    r.add_argument("--min-age-hours", type=float, default=2, help="replays appear after a while")
    r.add_argument("--max-age-hours", type=float, default=96, help="older demos expire")
    r.add_argument("--parse-timeout", type=int, default=900)
    r.add_argument("--keep-workspace", action="store_true")
    r.add_argument("--once", action="store_true", help="one discovery round, no waiting")
    r.add_argument("--retry-failed", action="store_true", help="parse earlier failures again")
    p = sub.add_parser("report", help="print progress")
    p.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    run(args) if args.command == "run" else report(args)


if __name__ == "__main__":
    main()
