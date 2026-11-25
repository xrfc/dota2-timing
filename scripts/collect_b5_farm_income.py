"""Plan, resume and audit farm-gold extraction for the frozen B5 development population."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.gem_replay import prepared_demo
from dota_items.storage import digest, file_hash, write_json, writer_lock

ROOT = Path(__file__).resolve().parents[1]
ROWS_SHA = "f2f1254c33158b6923fa7185dd1454414fc8483baaa7c8f69d5cf88d6eb395ca"
ROUTES_SHA = "fcc370fdcedaa19440d5a72bdd90a6743883710495894232ffaacb746415bda2"
POPULATION_SHA = "4909b7905e5d5568831f96ca5cff385302fd28cd9a9228fde2c31c9746a80d42"
IMPLEMENTATION = (
    "scripts/collect_b5_farm_income.py",
    "src/dota_items/sources/gem_farm_income.py",
    "src/dota_items/sources/gem_capture.py",
    "src/dota_items/sources/gem_capture_v3.py",
    "src/dota_items/sources/gem_replay.py",
    "src/dota_items/data/awareness_split.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/storage.py",
)


def verified(path, sha):
    raw = read_source_bytes(path)
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError(f"input fingerprint mismatch: {path.name}")
    return raw


def key(row):
    return row["match"], row["hero"], row["t"]


def population(rows_path, routes_path):
    source = [parse_source_json(line) for line in verified(rows_path, ROWS_SHA).splitlines()]
    routes = parse_source_json(verified(routes_path, ROUTES_SHA))
    lookup = {key(r): r for r in routes}
    if len(lookup) != len(routes) or len({key(r) for r in source}) != len(source):
        raise ValueError("duplicate opportunity")
    if set(lookup) != {key(r) for r in source}:
        raise ValueError("opportunity population mismatch")
    for r in source:
        mid = r["match"]
        fold = int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5
        if is_holdout(mid) or r["fold"] != fold or lookup[key(r)]["fold"] != fold:
            raise ValueError("reserved match or wrong development fold")
    return routes


def build_plan(rows_path, routes_path, data_root):
    grouped = defaultdict(list)
    for r in population(rows_path, routes_path):
        grouped[r["match"]].append({k: r[k] for k in ("match", "hero", "t", "fold", "action")})
    matches = []
    for mid, cases in sorted(grouped.items()):
        receipt_path = data_root / "receipts" / f"{mid}.json"
        meta_path = data_root / "meta" / f"{mid}.json"
        receipt_raw, meta_raw = read_source_bytes(receipt_path), read_source_bytes(meta_path)
        receipt, meta = parse_source_json(receipt_raw), parse_source_json(meta_raw)
        if receipt["match_id"] != mid or meta["match_id"] != mid or meta["patch"] != 60:
            raise ValueError("source match/patch mismatch")
        if type(meta["duration"]) is not int or meta["duration"] <= 0:
            raise ValueError("missing match duration")
        matches.append(
            dict(
                match=mid,
                duration=meta["duration"],
                patch=meta["patch"],
                demo_sha256=receipt["demo_sha256"],
                receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
                meta_sha256=hashlib.sha256(meta_raw).hexdigest(),
                cases=cases,
            )
        )
    return dict(
        schema="b5-farm-plan/1", rows_sha256=ROWS_SHA, routes_sha256=ROUTES_SHA, matches=matches
    )


def validate_plan(plan):
    if (plan.get("schema"), plan.get("rows_sha256"), plan.get("routes_sha256")) != (
        "b5-farm-plan/1",
        ROWS_SHA,
        ROUTES_SHA,
    ):
        raise ValueError("unsupported plan/population")
    mids, cases = set(), set()
    for match in plan["matches"]:
        mid = match["match"]
        if mid in mids or is_holdout(mid) or match["patch"] != 60:
            raise ValueError("duplicate, reserved match or patch mismatch")
        mids.add(mid)
        for row in match["cases"]:
            identity = key(row)
            if row["match"] != mid or identity in cases:
                raise ValueError("invalid opportunity identity")
            cases.add(identity)
    # Closed plan, not a facility for adding arbitrary matches under a development label.
    if len(mids) != 1169 or len(cases) != 15005:
        raise ValueError("incomplete frozen development plan")
    population_rows = sorted((r for m in plan["matches"] for r in m["cases"]), key=key)
    if digest(population_rows) != POPULATION_SHA:
        raise ValueError("plan changed frozen identities, actions or folds")


def score_windows(cases, captured, duration):
    bounds = {(r["hero"], r["t"]): r for r in captured["boundaries"]}
    if len(bounds) != len(captured["boundaries"]):
        raise ValueError("duplicate gold endpoint")
    events = defaultdict(list)
    for event in captured["events"]:
        events[event["hero"], event["kind"]].append((event["t"], event["value"]))
    rows = []
    for case in cases:
        hero, t = case["hero"], case["t"]
        windows = {}
        for n in (30, 20):
            start, end = bounds.get((hero, t)), bounds.get((hero, t + n))
            status = "complete"
            if t + n > duration:
                status = "truncated"
            elif (
                not start
                or not end
                or start["status"] == "missing_endpoint"
                or end["status"] == "missing_endpoint"
            ):
                status = "missing_endpoint"
            amounts = {}
            for kind in ("creep", "neutral"):
                counter = None
                if (
                    status == "complete"
                    and start.get(kind) is not None
                    and end.get(kind) is not None
                ):
                    counter = end[kind] - start[kind]
                    if counter < 0:
                        raise ValueError("decreasing cumulative farm gold")
                logged = (
                    sum(v for s, v in events[hero, kind] if t <= s < t + n)
                    if t + n <= duration
                    else None
                )
                amounts[kind] = dict(
                    counter=counter,
                    event=logged,
                    difference=None if counter is None else counter - logged,
                )
            if status == "complete" and any(a["counter"] is None for a in amounts.values()):
                status = "missing_counter"
            windows[str(n)] = dict(status=status, **amounts)
        rows.append(dict(**case, windows=windows))
    return rows


def implementation_hashes():
    return {p: file_hash(ROOT / p) for p in IMPLEMENTATION}


def binding(plan):
    return dict(
        schema="b5-farm-run/1",
        plan_sha256=digest(plan),
        implementation_sha256=implementation_hashes(),
    )


def verify_result(record, match, bound):
    checksum = record.get("payload_sha256")
    if checksum != digest({k: v for k, v in record.items() if k != "payload_sha256"}):
        raise ValueError("saved result checksum mismatch")
    if record["binding"] != bound or record["source"] != match:
        raise ValueError("saved result source/implementation mismatch")


def execute_match(match, data_root, output, bound):
    import gem

    from dota_items.sources.gem_farm_income import capture_farm_income, verify_compatibility

    def check_producer():
        if implementation_hashes() != bound["implementation_sha256"]:
            raise ValueError("implementation changed during extraction")
        verify_compatibility(Path(gem.__file__).resolve().parent)

    check_producer()

    mid = match["match"]
    # Recheck receipts and raw bytes even on resume; don't silently reuse changed sources.
    receipt = parse_source_json(
        verified(data_root / "receipts" / f"{mid}.json", match["receipt_sha256"])
    )
    meta = parse_source_json(verified(data_root / "meta" / f"{mid}.json", match["meta_sha256"]))
    if (
        receipt["match_id"] != mid
        or meta["match_id"] != mid
        or receipt["demo_sha256"] != match["demo_sha256"]
        or meta["patch"] != match["patch"]
        or meta["duration"] != match["duration"]
    ):
        raise ValueError("plan metadata disagrees with pinned sources")
    demo = data_root / "demos" / f"{mid}.dem.bz2"
    if file_hash(demo) != match["demo_sha256"]:
        raise ValueError("raw replay hash mismatch")
    target = output / f"{mid}.json"
    if target.exists():
        record = parse_source_json(read_source_bytes(target))
        verify_result(record, match, bound)
        check_producer()
        if file_hash(demo) != match["demo_sha256"]:
            raise ValueError("raw replay changed during resume")
        return "reused"
    with prepared_demo(demo, output / "scratch") as raw:
        captured = capture_farm_income(raw, [(r["hero"], r["t"]) for r in match["cases"]])
    if captured["match_id"] != mid:
        raise ValueError("parsed replay identity mismatch")
    record = dict(
        binding=bound,
        source=match,
        capture=captured,
        rows=score_windows(match["cases"], captured, match["duration"]),
    )
    record["payload_sha256"] = digest(record)
    check_producer()
    if file_hash(demo) != match["demo_sha256"]:
        raise ValueError("raw replay changed during extraction")
    write_json(target, record)  # The caller owns the single-writer lock; target was absent.
    return "extracted"


def _parallel(candidates, data_root, output, bound, workers):
    # Bound in-flight tasks so an error stops scheduling the rest of a long batch.
    iterator = iter(candidates)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {}

        def enqueue():
            match = next(iterator, None)
            if match is not None:
                pending[pool.submit(execute_match, match, data_root, output, bound)] = match

        for _ in range(workers):
            enqueue()
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            results = [(pending.pop(future), future.result()) for future in finished]
            for match, status in results:
                print(json.dumps(dict(match=match["match"], status=status)), flush=True)
                enqueue()


def run(plan, data_root, output, selected, limit, workers=1):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be positive")
    validate_plan(plan)
    bound = binding(plan)
    output.mkdir(parents=True, exist_ok=True)
    with writer_lock(output):
        manifest = output / "manifest.json"
        if manifest.exists():
            if parse_source_json(read_source_bytes(manifest)) != bound:
                raise ValueError("output directory belongs to different inputs/implementation")
        else:
            if any(output.glob("[0-9]*.json")):
                raise ValueError("unbound previous results")
            write_json(manifest, bound)
        candidates = plan["matches"]
        if selected:
            if not set(selected) <= {m["match"] for m in candidates}:
                raise ValueError("requested match not in frozen development plan")
            candidates = [m for m in candidates if m["match"] in selected]
        if limit:
            candidates = candidates[:limit]
        if workers > 1:
            _parallel(candidates, data_root, output, bound, workers)
            return
        for match in candidates:
            status = execute_match(match, data_root, output, bound)
            print(json.dumps(dict(match=match["match"], status=status)), flush=True)


def report(plan, output):
    validate_plan(plan)
    bound = binding(plan)
    if parse_source_json(read_source_bytes(output / "manifest.json")) != bound:
        raise ValueError("output manifest mismatch")
    rows, completed = [], 0
    for match in plan["matches"]:
        p = output / f"{match['match']}.json"
        if not p.exists():
            continue
        record = parse_source_json(read_source_bytes(p))
        verify_result(record, match, bound)
        rows.extend(record["rows"])
        completed += 1
    return dict(
        matches_planned=len(plan["matches"]),
        matches_complete=completed,
        opportunities_planned=sum(len(m["cases"]) for m in plan["matches"]),
        opportunities_complete=len(rows),
        actions=dict(Counter(r["action"] for r in rows)),
        windows={
            str(n): dict(
                statuses=dict(Counter(r["windows"][str(n)]["status"] for r in rows)),
                differences={
                    kind: dict(
                        observed=sum(
                            r["windows"][str(n)][kind]["difference"] is not None for r in rows
                        ),
                        nonzero=sum(
                            r["windows"][str(n)][kind]["difference"] not in (None, 0) for r in rows
                        ),
                    )
                    for kind in ("creep", "neutral")
                },
            )
            for n in (30, 20)
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    make = sub.add_parser("plan")
    make.add_argument("--out", type=Path, required=True)
    make.add_argument("--rows", type=Path, default=ROOT / "reports/outcome-labels/rows.jsonl")
    make.add_argument(
        "--routes", type=Path, default=ROOT / "reports/b5-route-coverage-20261125/rows.json"
    )
    for name in ("run", "report"):
        q = sub.add_parser(name)
        q.add_argument("--plan", type=Path, required=True)
        q.add_argument("--out", type=Path, required=True)
        if name == "run":
            q.add_argument("--match", type=int, action="append")
            q.add_argument("--limit", type=int)
            q.add_argument("--workers", type=int, default=1)
            q.add_argument("--data", type=Path, default=ROOT / "data/demos-2026-11")
    make.add_argument("--data", type=Path, default=ROOT / "data/demos-2026-11")
    args = p.parse_args()
    if args.command == "plan":
        if args.out.exists():
            raise ValueError("plan already exists")
        plan = build_plan(args.rows, args.routes, args.data)
        validate_plan(plan)
        write_json(args.out, plan)
        print(
            json.dumps(
                dict(
                    matches=len(plan["matches"]),
                    opportunities=sum(len(m["cases"]) for m in plan["matches"]),
                )
            )
        )
    else:
        plan = parse_source_json(read_source_bytes(args.plan))
        if args.command == "run":
            if args.limit is not None and args.limit < 1:
                raise ValueError("limit must be positive")
            run(plan, args.data, args.out, args.match, args.limit, args.workers)
        else:
            print(json.dumps(report(plan, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
