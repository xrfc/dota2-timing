"""Prepare decision-time wave samples from local, high-rank development matches."""

import argparse
import gzip
import hashlib
import json
import os
import pickle
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from math import dist
from pathlib import Path

from detect_ganks import read_match, source_key

from dota_items.data.awareness_split import is_holdout
from dota_items.data.death_risk import death_times
from dota_items.data.lane_decisions import farm_seconds, make_cases, wave_opportunities
from dota_items.data.vision_sim import Terrain, sees
from dota_items.storage import read_json

PATCH_WINDOW = (1789455600, 1794988800)
SEQUENCE = [
    "visible_enemies",
    "nearest_visible_enemy",
    "nearest_ally",
    "missing_10s",
    "self_x",
    "self_y",
    "wave_front_distance",
]
STATIC = [
    "time",
    "front_distance",
    "visible_creeps",
    "hp_fraction",
    "mana",
    "ready_saves",
    "recent_damage",
]


def fold_for(mid):
    return int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5


def candidates(root, *, min_rank=70, holdout=False):
    ready = []
    extra = []
    for receipt in sorted((root / "receipts").glob("*.json")):
        if not receipt.stem.isdigit():
            continue
        mid = int(receipt.stem)
        if is_holdout(mid) != holdout:
            continue
        rc = read_json(receipt)
        if rc.get("status") != "parsed" or (rc.get("avg_rank_tier") or 0) < min_rank:
            continue
        meta = read_json(root / "meta" / receipt.name)
        if not (
            rc.get("match_id") == meta.get("match_id") == mid
            and meta["patch"] == 60
            and PATCH_WINDOW[0] <= meta["start_time"] < PATCH_WINDOW[1]
            and meta["lobby_type"] == 7
            and meta["game_mode"] == 22
            and meta["duration"] >= 900
        ):
            continue
        if not all(
            (root / name / f"{mid}.{suffix}").is_file()
            for name, suffix in [("parsed", "normalized.json.gz"), ("state-v3", "jsonl.gz")]
        ):
            continue
        bucket = ready if (root / "extras-v1" / f"{mid}.jsonl.gz").is_file() else extra
        bucket.append(mid)
    return ready, extra


def normalized_end(path, mid):
    # The normalized producer emits its scalar header before the players array.
    # Read only that small prefix of the potentially hundreds-of-MB JSON.
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        prefix = stream.read(4096)

    first_players = prefix.find('"players"')
    if first_players > 0:
        scalar_json = prefix[:first_players].rstrip().removesuffix(",") + "}"
        try:
            header = json.loads(scalar_json)
        except json.JSONDecodeError:
            header = {}
    else:
        header = {}
    if "duration" not in header or "match_id" not in header:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            header = json.load(stream)
    if header["match_id"] != mid or type(header["duration"]) is not int or header["duration"] < 0:
        raise ValueError(f"Unexpected normalized header for {mid}")
    return header["duration"]


@lru_cache(maxsize=1)
def terrain(folder):
    trees = read_json(folder / "mapdata.json")["data"]["ent_dota_tree"]
    return Terrain(
        read_json(folder / "elevationdata.json")["data"], [(t["x"], t["y"]) for t in trees]
    )


def capture(root, name, mid, schema):
    with gzip.open(root / name / f"{mid}.jsonl.gz", "rt", encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if header.get("match_id") != mid or header.get("schema") != schema:
            raise ValueError(f"{mid}: unexpected {name} header")
        previous = None
        count = 0
        for row in map(json.loads, stream):
            if previous is not None and row["t"] <= previous:
                raise ValueError(f"{mid}: non-increasing {name} clock")
            previous = row["t"]
            count += 1
            yield row
        if count != header["seconds"]:
            raise ValueError(f"{mid}: incomplete {name}")


def frame_values(frame):
    if frame is None:
        return [None] * len(SEQUENCE)
    t = frame["t"]
    enemies = [e for e in frame["enemies"] if not e.get("dead")]
    if any(
        e["last_seen"] is not None
        and e["last_seen"] > t
        or e["distance"] is not None
        and e["last_seen"] != t
        for e in enemies
    ):
        raise ValueError("Invalid enemy sight timestamp")
    distances = [e["distance"] for e in enemies if e["distance"] is not None]
    own = next(m["pos"] for m in frame["markers"] if m["side"] == "self")
    return [
        len(distances),
        min(distances, default=None),
        frame["ally"][0] if frame["ally"] else None,
        sum(e["last_seen"] is None or t - e["last_seen"] >= 10 for e in enemies),
        *own,
        dist(own, frame["wave"]) if frame.get("wave") else None,
    ]


def sample(e, a, y, end):
    t = e["t"]
    history = {f["t"]: f for f in e["history"]}
    if not history.keys() <= {t - 10, t - 5, t} or t not in history:
        raise ValueError("Invalid decision history")
    seq = [frame_values(history.get(sec)) for sec in (t - 10, t - 5, t)]
    action = a["action"] if t + 6 <= end else "unknown"
    known = action in ("farm", "retreat")
    early = any(t < s <= t + 6 for s in y["death_seconds"])
    outcome_ok = known and t + 20 <= end and not early
    hp, maximum = e["hp"]
    damage = e["recent_hero_damage"]
    return dict(
        match=e["match"],
        hero=e["hero"],
        t=t,
        fold=fold_for(e["match"]),
        action=action,
        recent_damage=damage,
        static=[
            t,
            e["front_distance"],
            e["nearby_creeps"],
            hp / maximum if hp is not None and maximum else None,
            e["mana"],
            len(e["ready_names"]),
            int(damage),
        ],
        sequence=seq,
        hits=y["lane_last_hits"] - y["action_window_hits"] if outcome_ok else None,
        death=int(any(t + 6 < s <= t + 20 for s in y["death_seconds"])) if outcome_ok else None,
        action_complete=t + 6 <= end,
        window_complete=t + 20 <= end,
        early_death=early,
        behavior_eligible=known,
        outcome_eligible=outcome_ok,
        exclusion=(
            "unknown_action"
            if not known
            else "truncated"
            if t + 20 > end
            else "early_death"
            if early
            else None
        ),
    )


def readonly_match(root, mid):
    """Reuse a valid replay cache without writing into the source worktree."""
    cached = root / "gank-inputs-v2" / f"{mid}.pkl"
    match = None
    if cached.is_file():
        with cached.open("rb") as stream:
            match = pickle.load(stream)
    if not match or match["key"] != source_key(root, mid):
        match = read_match(root, mid)
    return match


def match_rows(job, *, holdout=False):
    mid, root, map_dir, extras_root = job
    if is_holdout(mid) != holdout:
        raise ValueError("reserved match or wrong partition")
    match = readonly_match(root, mid)
    duration = normalized_end(root / "parsed" / f"{mid}.normalized.json.gz", mid)
    end = min(match["last"], duration)
    heroes = sorted(h for h, p in match["positions"].items() if p == 1)
    visibility = {k: sorted(v) for k, v in match["seen"].items()}
    extras = {
        row["t"]: row for row in capture(extras_root, "extras-v1", mid, "gem-extras-capture/1")
    }
    hits = {h: farm_seconds(match["combat"], h, match["tracks"][h]["team"]) for h in heroes}

    def can_see(origin, target, t):
        return sees(origin, target, "hero", t, terrain(map_dir), "sight")

    opp = {h: wave_opportunities(match, h, hits[h], extras, can_see) for h in heroes}
    states = {h: {} for h in heroes}
    match["dead_at"] = {}
    for row in capture(root, "state-v3", mid, "gem-state-capture/3"):
        t = row["t"]
        for state in row["heroes"]:
            h = state["hero"]
            if h in opp and t in opp[h]:
                states[h][t] = state
            if state.get("life_state") in (1, 2):
                match["dead_at"].setdefault(t, set()).add(h)
    means = read_json(
        Path(__file__).resolve().parents[1] / "knowledge/awareness/save-means-v2.json"
    )["means"]
    rows = []
    for h in heroes:
        cases = make_cases(
            match,
            mid,
            h,
            hits[h],
            visibility,
            states[h],
            means,
            death_times(match["combat"], h),
            opportunities=opp[h],
        )
        rows.extend(sample(e, a, y, end) for e, a, y in cases if e["t"] <= end)
    return rows


def supported(rows):
    return all(
        {r["action"] for r in rows if r["fold"] == f and r["behavior_eligible"]}
        == {"farm", "retreat"}
        and {r["death"] for r in rows if r["fold"] == f and r["outcome_eligible"]} == {0, 1}
        for f in range(5)
    )


def checked_match(job):
    try:
        return match_rows(job), None
    except (ValueError, EOFError) as error:
        return [], str(error)


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sources(root, extras_root, mid):
    paths = [
        root / d / f"{mid}.{ext}"
        for d, ext in [
            ("receipts", "json"),
            ("meta", "json"),
            ("parsed", "normalized.json.gz"),
            ("state-v3", "jsonl.gz"),
            ("gank-inputs-v2", "pkl"),
        ]
    ]
    if extras_root is not None:
        paths.append(extras_root / "extras-v1" / f"{mid}.jsonl.gz")
    return {f"{p.parent.name}/{p.name}": file_hash(p) for p in paths if p.is_file()}


def derive_batch(root, batch_root, batch, workers, compat):
    """Publish expansions only inside this experiment's private staging folder."""
    demos = batch_root / "demos"
    demos.mkdir(parents=True)
    available = []
    rejected = {}
    for mid in batch:
        original = next(
            (
                p
                for suffix in ("dem.bz2", "dem.zst")
                if (p := root / "demos" / f"{mid}.{suffix}").is_file()
            ),
            None,
        )
        if original is None:
            rejected[mid] = "missing local compressed replay"
            continue
        (demos / f"{mid}.dem.bz2").symlink_to(original.resolve())
        available.append(mid)
    if not available:
        return [], rejected
    env = os.environ.copy()
    if compat is not None:
        env["PYTHONPATH"] = os.pathsep.join([str(compat.resolve()), env.get("PYTHONPATH", "")])
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("extract_creeps.py")),
            "run",
            "--root",
            str(batch_root),
            "--kind",
            "extras",
            "--workers",
            str(workers),
        ],
        env=env,
        check=True,
    )
    good = []
    for mid in available:
        receipt = read_json(batch_root / "extras-v1" / "receipts" / f"{mid}.json")
        if receipt["status"] == "extracted":
            good.append(mid)
        else:
            rejected[mid] = receipt["error"]
    return good, rejected


def cache_batch(root, batch, wait_seconds):
    """Consume completed receipts from an independent local extractor."""
    folder = root / "extras-v1"
    deadline = time.monotonic() + wait_seconds
    ready, rejected = [], {}
    for mid in batch:
        receipt = folder / "receipts" / f"{mid}.json"
        while True:
            try:
                record = read_json(receipt)
                break
            except (FileNotFoundError, json.JSONDecodeError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(2)
        if record["match_id"] != mid:
            raise ValueError(f"{mid}: incorrect expansion receipt")
        if record["status"] == "failed":
            rejected[mid] = record["error"]
        elif record["status"] == "extracted" and (folder / f"{mid}.jsonl.gz").is_file():
            ready.append(mid)
        else:
            raise ValueError(f"{mid}: incomplete expansion")
    return ready, rejected


def cohort_batches(ready, missing, *, full, has_support):
    yield ready
    for i in range(0, len(missing), 100):
        if not full and has_support():
            return
        yield missing[i : i + 100]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--map-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--expansion-compat", type=Path, help="existing compatible Gem import directory"
    )
    parser.add_argument(
        "--full", action="store_true", help="continue through every eligible development match"
    )
    parser.add_argument(
        "--extras-cache",
        type=Path,
        help="read precomputed expansion extras from DIR/extras-v1 (requires every expansion)",
    )
    parser.add_argument(
        "--wait-for-extras",
        type=int,
        default=0,
        metavar="SECONDS",
        help="maximum time per expansion batch to wait for an in-progress extras cache",
    )
    args = parser.parse_args()
    if args.wait_for_extras < 0 or (args.wait_for_extras and not args.extras_cache):
        parser.error("--wait-for-extras requires an extras cache and a nonnegative timeout")
    if args.workers < 1:
        parser.error("workers must be positive")
    if args.out.exists():
        parser.error("choose a new output directory")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ready, extra = candidates(args.root)
    rows = []
    failures = {}
    empty = []
    attempted = []
    input_hashes = {}
    batches = []
    compat = args.expansion_compat or args.root.parent / "replay-pilot-2026-10-22" / "compat-v1"
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        for batch_no, batch in enumerate(
            cohort_batches(ready, extra, full=args.full, has_support=lambda: supported(rows))
        ):
            attempted.extend(batch)
            batches.append(batch)
            batch_root = args.root
            if batch_no and args.extras_cache:
                batch_root = args.extras_cache
                batch, rejected = cache_batch(batch_root, batch, args.wait_for_extras)
                failures.update(rejected)
            elif batch_no:
                batch_root = Path(temp) / f"batch-{batch_no}"
                batch, rejected = derive_batch(args.root, batch_root, batch, args.workers, compat)
                failures.update(rejected)
            jobs = [(mid, args.root, args.map_dir, batch_root) for mid in batch]
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                for i, (job, result) in enumerate(
                    zip(jobs, pool.map(checked_match, jobs), strict=True), 1
                ):
                    result, reason = result
                    if reason:
                        failures[job[0]] = reason
                    elif not result:
                        empty.append(job[0])
                    rows.extend(result)
                    input_hashes[job[0]] = sources(args.root, batch_root, job[0])
                    print(i, job[0], len(result), flush=True)
    repo = Path(__file__).resolve().parents[1]
    code = [
        repo / name
        for name in (
            "scripts/lane_study_data.py",
            "scripts/detect_ganks.py",
            "src/dota_items/data/lane_decisions.py",
            "src/dota_items/data/gank_events.py",
            "src/dota_items/data/vision_sim.py",
            "src/dota_items/data/death_risk.py",
            "src/dota_items/data/awareness_split.py",
            "knowledge/awareness/save-means-v2.json",
        )
    ]
    manifest = dict(
        schema="lane-study/1",
        cohort_mode="full" if args.full else "pilot",
        matches=attempted,
        folds={m: fold_for(m) for m in attempted},
        batches=batches,
        inputs_sha256=input_hashes,
        code_sha256={str(p.relative_to(repo)): file_hash(p) for p in code},
        map_sha256={p: file_hash(args.map_dir / p) for p in ("mapdata.json", "elevationdata.json")},
        rejected_matches=failures,
        empty_matches=empty,
        expansion_candidates=len(extra),
        supported=supported(rows),
        static_features=STATIC,
        sequence_features=SEQUENCE,
        exclusions=dict(Counter(r["exclusion"] for r in rows if r["exclusion"])),
        rows=len(rows),
    )
    with tempfile.TemporaryDirectory(dir=args.out.parent) as staging:
        result_dir = Path(staging) / "dataset"
        result_dir.mkdir()
        row_file = result_dir / "rows.jsonl"
        with row_file.open("x", encoding="utf-8") as stream:
            for row in rows:
                print(json.dumps(row, allow_nan=False), file=stream)
        manifest["rows_sha256"] = hashlib.sha256(row_file.read_bytes()).hexdigest()
        (result_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        result_dir.rename(args.out)


if __name__ == "__main__":
    main()
