"""Census movement labels on the frozen U191 development wave opportunities (no fitting)."""

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from itertools import pairwise
from math import dist
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.source_io import parse_source_json, read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
ROWS_SHA256 = "f2f1254c33158b6923fa7185dd1454414fc8483baaa7c8f69d5cf88d6eb395ca"
LANE, JUNGLE, UNKNOWN = "stay_lane", "move_to_jungle", "unknown"
TIME = re.compile(rb'^\{"t": (-?\d+),')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def movement(path, front, camps):
    """Preserve the 2026-11-24 geometry thresholds; future positions are labels only."""
    if len(path) != 7:
        raise ValueError("movement requires exactly t..t+6")
    start = path[0]
    if not start or front is None:
        return UNKNOWN, "missing_start_or_front"
    lane_gap = dist(start, front)
    for second, (prev, pos) in enumerate(pairwise(path), 1):
        if not pos:
            return UNKNOWN, "interrupted_before_commitment"
        if dist(prev, pos) > 700:
            return UNKNOWN, "jump_before_commitment"
        if second < 3 or dist(pos, front) - lane_gap < 350:
            continue
        for camp in camps:
            centre = camp["x"], camp["y"]
            gaps = [dist(p, centre) for p in path[: second + 1]]
            if (
                gaps[-1] <= 1200
                and gaps[0] - gaps[-1] >= 450
                and sum(b < a for a, b in pairwise(gaps)) >= 3
                and dist(pos, front) >= 850
            ):
                return JUNGLE, "committed_departure"
    near = [dist(p, front) for p in path]
    if sum(gap <= 800 for gap in near) >= 4 and near[-1] <= 800 and near[-1] - lane_gap <= 150:
        return LANE, "stayed_near_front"
    return UNKNOWN, "ambiguous_geometry"


def load_opportunities(path, expected=ROWS_SHA256):
    raw = read_source_bytes(path)
    if digest(raw) != expected:
        raise ValueError("frozen wave rows hash mismatch")
    rows = [parse_source_json(line) for line in raw.splitlines()]
    seen = set()
    for row in rows:
        mid, hero, t = row["match"], row["hero"], row["t"]
        key = mid, hero, t
        fold = int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5
        if key in seen or is_holdout(mid) or row["fold"] != fold:
            raise ValueError("duplicate, holdout, or invalid development fold")
        seen.add(key)
    return rows


def read_frames(path, mid, needed):
    raw = read_source_bytes(path)
    frames = {}
    last = None
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        header = parse_source_json(next(stream))
        if header.get("match_id") != mid or header.get("schema") != "gem-state-capture/3":
            raise ValueError("state identity/schema mismatch")
        if header.get("coordinates") != "cell space (cell*128+vec), map centre 16384":
            raise ValueError("state coordinate mismatch")
        for line in stream:
            fast = TIME.match(line)
            frame = None if fast else parse_source_json(line)
            t = int(fast[1]) if fast else frame["t"]
            if last is not None and t <= last:
                raise ValueError("state seconds are not strictly increasing")
            last = t
            if t in needed:
                frames[t] = frame if frame is not None else parse_source_json(line)
    return frames, last, digest(raw)


def label_case(row, frames, last, camps):
    t, hero = row["t"], row["hero"]
    own = []
    for sec in range(t, t + 7):
        hits = [h for h in frames.get(sec, {}).get("heroes", []) if h["hero"] == hero]
        if len(hits) > 1:
            raise ValueError("duplicate hero in state frame")
        own.append(hits[0] if hits else {})
    path = [h.get("pos") if h.get("life_state") == 0 else None for h in own]
    start = own[0]
    prefix = {2: "radiant_", 3: "dire_"}.get(start.get("team"))
    fronts = frames.get(t, {}).get("world", {}).get("lane_fronts", {})
    points = [
        v["front"]
        for k, v in fronts.items()
        if prefix and k.startswith(prefix) and v and v.get("count") and v.get("front")
    ]
    front = min(points, key=lambda p: dist(path[0], p)) if points and path[0] else None
    action, reason = movement(path, front, camps)
    # Explicit allowlist: enemy state, future income and later movement never become features.
    available = {
        "own_position": path[0] is not None,
        "own_speed": start.get("move_speed") is not None and start["move_speed"] > 0,
        "own_lane_front": front is not None,
        "static_camp_geometry": bool(camps) and path[0] is not None,
    }
    hp, maximum = start.get("hp"), start.get("max_hp")
    hp_band = "missing" if hp is None or not maximum else ("low" if hp / maximum < 0.5 else "high")
    return dict(
        match=row["match"],
        hero=hero,
        t=t,
        fold=row["fold"],
        previous=row["action"],
        action=action,
        reason=reason,
        available=available,
        time_band=f"{t // 600 * 10}-{t // 600 * 10 + 10}min",
        hp_band=hp_band,
        state_reaches_20s=last is not None and last >= t + 20,
        state_reaches_30s=last is not None and last >= t + 30,
    )


def process_match(job):
    mid, rows, state_root, camps = job
    path = state_root / f"{mid}.jsonl.gz"
    if path.exists():
        needed = {r["t"] + offset for r in rows for offset in range(7)}
        frames, last, sha = read_frames(path, mid, needed)
        source = dict(match=mid, sha256=sha, status="read")
    else:
        frames, last = {}, None
        source = dict(match=mid, sha256=None, status="missing")
    return [label_case(r, frames, last, camps) for r in rows], source


def counts(rows):
    return {
        action: dict(
            rows=sum(r["action"] == action for r in rows),
            matches=len({r["match"] for r in rows if r["action"] == action}),
        )
        for action in (LANE, JUNGLE, UNKNOWN)
    }


def summarize(rows):
    groups = {name: defaultdict(list) for name in ("hero", "fold", "time_band", "hp_band")}
    cells = defaultdict(list)
    for row in rows:
        for name, bins in groups.items():
            bins[str(row[name])].append(row)
        cells[(row["hero"], row["time_band"], row["hp_band"])].append(row)
    cell_rows = []
    for (hero, time, hp), members in sorted(cells.items()):
        arms = counts(members)
        cell_rows.append(
            dict(
                hero=hero,
                time_band=time,
                hp_band=hp,
                actions=arms,
                both_observed=all(arms[a]["rows"] > 0 for a in (LANE, JUNGLE)),
            )
        )
    return dict(
        opportunities=len(rows),
        matches=len({r["match"] for r in rows}),
        actions=counts(rows),
        reasons=dict(sorted(Counter(r["reason"] for r in rows).items())),
        transitions=dict(sorted(Counter(f"{r['previous']}->{r['action']}" for r in rows).items())),
        missing_decision_fields={
            k: sum(not r["available"][k] for r in rows) for k in rows[0]["available"]
        }
        if rows
        else {},
        state_window_short={
            str(n): sum(not r[f"state_reaches_{n}s"] for r in rows) for n in (20, 30)
        },
        by={name: {k: counts(v) for k, v in sorted(bins.items())} for name, bins in groups.items()},
        descriptive_cells=cell_rows,
        cells_with_both=sum(c["both_observed"] for c in cell_rows),
        note="Descriptive support only; bins are not balancing or causal identification.",
    )


def run(rows_path, state_root, map_path, output, workers):
    rows = load_opportunities(rows_path)  # Reject reserved data before any state access.
    map_raw = read_source_bytes(map_path)
    map_data = parse_source_json(map_raw)
    if map_data.get("patch") != "7.41":
        raise ValueError("census requires the existing 7.41 camp map")
    camps = map_data["camps"]
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["match"]].append(row)
    output.mkdir(parents=True, exist_ok=False)
    jobs = [(mid, group, state_root, camps) for mid, group in sorted(grouped.items())]
    labelled, sources = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, (cases, source) in enumerate(pool.map(process_match, jobs), 1):
            labelled.extend(cases)
            sources.append(source)
            if i % 100 == 0:
                print(f"{i}/{len(jobs)} matches", file=sys.stderr, flush=True)
    results = summarize(labelled)
    results.update(
        schema="b5-route-census/1",
        rows_sha256=ROWS_SHA256,
        map_sha256=digest(map_raw),
        implementation_sha256={
            p: digest(read_source_bytes(ROOT / p))
            for p in (
                "scripts/inventory_b5_routes.py",
                "src/dota_items/data/awareness_split.py",
                "src/dota_items/data/source_io.py",
            )
        },
        state_sources=sources,
    )
    for name, obj in (("summary.json", results), ("rows.json", labelled)):
        (output / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
    print(
        json.dumps(
            {
                k: results[k]
                for k in ("opportunities", "matches", "actions", "reasons", "cells_with_both")
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, default=ROOT / "reports/outcome-labels/rows.jsonl")
    parser.add_argument("--states", type=Path, default=ROOT / "data/demos-2026-11/state-v3")
    parser.add_argument("--map", type=Path, default=ROOT / "knowledge/awareness/map-zones-v1.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    run(args.rows, args.states, args.map, args.out, args.workers)


if __name__ == "__main__":
    main()
