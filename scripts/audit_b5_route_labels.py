"""Explain frozen B5 movement labels without relabelling, tuning or reading outcomes."""

import argparse
import gzip
import io
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from itertools import pairwise
from math import dist
from pathlib import Path

from inventory_b5_routes import ROOT, UNKNOWN, digest, label_case, load_opportunities

from dota_items.data.source_io import parse_source_json, read_source_bytes

TIME = re.compile(rb'^\{\s*"t"\s*:\s*(-?\d+)\s*,')
RECEIPT = ROOT / "docs/acceptance/b5-route-coverage.json"


def verified(path, expected):
    raw = read_source_bytes(path)
    if digest(raw) != expected:
        raise ValueError(f"frozen source hash mismatch: {path.name}")
    return raw


def frames_at(path, expected, mid, needed):
    """Read only requested seconds from byte-identical, previously validated state files."""
    raw = verified(path, expected)
    frames, last = {}, None
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        header = parse_source_json(next(stream))
        if header.get("match_id") != mid or header.get("schema") != "gem-state-capture/3":
            raise ValueError("state identity/schema mismatch")
        for line in stream:
            fast = TIME.match(line)
            frame = None if fast else parse_source_json(line)
            t = int(fast[1]) if fast else frame["t"]
            if last is not None and t <= last:
                raise ValueError("state seconds are not strictly increasing")
            last = t
            if t in needed:
                frames[t] = frame if frame is not None else parse_source_json(line)
    return frames, last


def own_at(frames, sec, hero):
    if sec not in frames:
        return {}, "missing_frame"
    found = [h for h in frames[sec].get("heroes", []) if h["hero"] == hero]
    if len(found) > 1:
        raise ValueError("duplicate hero")
    if not found:
        return {}, "missing_hero"
    own = found[0]
    if own.get("life_state") is None:
        return own, "missing_life_state"
    if own["life_state"] != 0:
        return own, "not_alive"
    if not own.get("pos"):
        return own, "missing_position"
    return own, None


def geometry(path, front, camps):
    lane = [dist(p, front) for p in path]
    failures = []
    if sum(x <= 800 for x in lane) < 4:
        failures.append("fewer_than_four_near_positions")
    if lane[-1] > 800:
        failures.append("endpoint_outside_800")
    if lane[-1] - lane[0] > 150:
        failures.append("lane_gap_gain_above_150")
    candidates = []
    for sec in range(3, 7):
        for camp in camps:
            gaps = [dist(p, (camp["x"], camp["y"])) for p in path[: sec + 1]]
            checks = {
                "lane_gap_gain_below_350": lane[sec] - lane[0] < 350,
                "lane_gap_below_850": lane[sec] < 850,
                "camp_gap_above_1200": gaps[-1] > 1200,
                "camp_gain_below_450": gaps[0] - gaps[-1] < 450,
                "fewer_than_three_approaches": sum(b < a for a, b in pairwise(gaps)) < 3,
            }
            failed = sorted(k for k, v in checks.items() if v)
            candidates.append((len(failed), sec, camp["id"], failed))
    closest = min(candidates) if candidates else None
    return dict(
        lane_failed=failures,
        lane_distances=[round(v, 3) for v in lane],
        # Diagnostic minimum failed predicate count, NOT an alternative action or confidence.
        jungle_min_failed=None if closest is None else closest[0],
        jungle_witness=None
        if closest is None
        else dict(second=closest[1], camp=closest[2], failed=closest[3]),
    )


def diagnose(row, frames, camps):
    t, hero = row["t"], row["hero"]
    observations = [own_at(frames, t + d, hero) for d in range(7)]
    own = [h for h, _ in observations]
    if observations[0][1]:
        return dict(kind=observations[0][1], second=0)
    prefix = {2: "radiant_", 3: "dire_"}.get(own[0].get("team"))
    fronts = frames[t].get("world", {}).get("lane_fronts", {})
    points = [
        v["front"]
        for k, v in fronts.items()
        if prefix and k.startswith(prefix) and v and v.get("count") and v.get("front")
    ]
    if not points:
        return dict(kind="missing_front")
    path = [h.get("pos") for h in own]
    front = min(points, key=lambda p: dist(path[0], p))
    for sec in range(1, 7):
        if observations[sec][1]:
            return dict(kind=observations[sec][1], second=sec)
        distance = dist(path[sec - 1], path[sec])
        if distance > 700:
            return dict(
                kind="jump",
                second=sec,
                distance=round(distance, 3),
                prior_speed=own[sec - 1].get("move_speed"),
                current_speed=own[sec].get("move_speed"),
            )
    return dict(kind="geometry", **geometry(path, front, camps))


def audit_match(job):
    mid, cases, expected_rows, source, state_root, camps = job
    if source["status"] != "read":
        raise ValueError("baseline has no validated state for this match")
    frames, last = frames_at(
        state_root / f"{mid}.jsonl.gz",
        source["sha256"],
        mid,
        {r["t"] + d for r in cases for d in range(7)},
    )
    details = []
    for case in cases:
        key = case["match"], case["hero"], case["t"]
        observed = label_case(case, frames, last, camps)
        if observed != expected_rows[key]:
            raise ValueError("replayed label differs from frozen census")
        if observed["action"] == UNKNOWN:
            details.append(
                dict(
                    match=mid,
                    hero=case["hero"],
                    t=case["t"],
                    previous_reason=observed["reason"],
                    diagnostic=diagnose(case, frames, camps),
                )
            )
    return len(cases), details


def summarize(details):
    result = dict(
        unknown=len(details),
        matches=len({r["match"] for r in details}),
        kinds={},
        lane_failures={},
        jungle_min_failed={},
        jump_by_hero={},
    )
    result["kinds"] = dict(sorted(Counter(r["diagnostic"]["kind"] for r in details).items()))
    geometric = [r["diagnostic"] for r in details if r["diagnostic"]["kind"] == "geometry"]
    result["lane_failures"] = dict(
        sorted(Counter(" + ".join(d["lane_failed"]) for d in geometric).items())
    )
    result["jungle_min_failed"] = dict(
        sorted(Counter(str(d["jungle_min_failed"]) for d in geometric).items())
    )
    result["jungle_failed_predicates"] = dict(
        sorted(
            Counter(
                f for d in geometric if d["jungle_witness"] for f in d["jungle_witness"]["failed"]
            ).items()
        )
    )
    jumps = [r for r in details if r["diagnostic"]["kind"] == "jump"]
    result["jump_by_hero"] = dict(sorted(Counter(r["hero"] for r in jumps).items()))
    result["jump_distance_counts"] = {
        "700_to_1200": sum(r["diagnostic"]["distance"] <= 1200 for r in jumps),
        "1200_to_3000": sum(1200 < r["diagnostic"]["distance"] <= 3000 for r in jumps),
        "above_3000": sum(r["diagnostic"]["distance"] > 3000 for r in jumps),
    }
    result["examples"] = {
        kind: next(r for r in details if r["diagnostic"]["kind"] == kind)
        for kind in result["kinds"]
    }
    return result


def run(args):
    receipt = parse_source_json(read_source_bytes(RECEIPT))
    census = parse_source_json(
        verified(args.census / "summary.json", receipt["outputs_sha256"]["summary.json"])
    )
    old = parse_source_json(
        verified(args.census / "rows.json", receipt["outputs_sha256"]["rows.json"])
    )
    for path, sha in census["implementation_sha256"].items():
        verified(ROOT / path, sha)
    camps = parse_source_json(
        verified(ROOT / "knowledge/awareness/map-zones-v1.json", census["map_sha256"])
    )["camps"]
    rows = load_opportunities(args.rows)
    expected = {(r["match"], r["hero"], r["t"]): r for r in old}
    if len(expected) != len(old) or set(expected) != {
        (r["match"], r["hero"], r["t"]) for r in rows
    }:
        raise ValueError("opportunity population mismatch")
    sources = {r["match"]: r for r in census["state_sources"]}
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["match"]].append(row)
    args.out.mkdir(parents=True, exist_ok=False)
    jobs = [
        (
            mid,
            cases,
            {
                (r["match"], r["hero"], r["t"]): expected[r["match"], r["hero"], r["t"]]
                for r in cases
            },
            sources[mid],
            args.states,
            camps,
        )
        for mid, cases in sorted(grouped.items())
    ]
    verified_count, details = 0, []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, (n, diagnostics) in enumerate(pool.map(audit_match, jobs), 1):
            verified_count += n
            details.extend(diagnostics)
            if i % 200 == 0:
                print(f"{i}/{len(jobs)} matches", file=sys.stderr, flush=True)
    result = summarize(details)
    if result["unknown"] != receipt["actions"][UNKNOWN]["rows"]:
        raise ValueError("unknown population mismatch")
    result.update(
        schema="b5-route-diagnostics/1",
        labels_reproduced=verified_count,
        census_outputs_sha256=receipt["outputs_sha256"],
        implementation_sha256=digest(read_source_bytes(Path(__file__))),
    )
    for name, value in (("summary.json", result), ("details.json", details)):
        (args.out / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "labels_reproduced",
                    "unknown",
                    "kinds",
                    "lane_failures",
                    "jungle_min_failed",
                    "jump_distance_counts",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--census", type=Path, default=ROOT / "reports/b5-route-coverage-20261125")
    p.add_argument("--rows", type=Path, default=ROOT / "reports/outcome-labels/rows.jsonl")
    p.add_argument("--states", type=Path, default=ROOT / "data/demos-2026-11/state-v3")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    run(p.parse_args())
