"""Audit walking scenarios on retrospectively observed endpoints in three 7.41f replays.

Run PYTHONPATH=src .venv/bin/python scripts/check_support_travel.py from the repository.
Outputs JSON to stdout. The endpoint is taken from the replay after eight seconds.
This measures traversal timing on moving segments, not support intent or fight arrival.
"""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from itertools import pairwise
from math import dist
from pathlib import Path
from statistics import mean, median

from detect_ganks import match_inputs

from dota_items.data.awareness_split import is_holdout
from dota_items.data.support_arrival import support_comparison, walk_hit_window

MATCHES = (9080976703, 9081112027, 9081112126)
START = 900
WINDOW = 8
MIN_STEP = 50
JUMP_FACTOR = 1.35


def audit_match(root, mid):
    if is_holdout(mid):
        raise ValueError(f"reserved holdout match {mid}")
    meta = json.loads((root / "meta" / f"{mid}.json").read_text())
    if meta["match_id"] != mid or meta["patch"] != 60:
        raise ValueError(f"{mid}: unexpected match metadata")
    match = match_inputs(root, mid, root / "gank-inputs-v2")
    tracks = {h: {} for h, role in match["positions"].items() if role == 1}
    with gzip.open(root / "state-v3" / f"{mid}.jsonl.gz", "rt") as stream:
        header = json.loads(next(stream))
        if header.get("schema") != "gem-state-capture/3" or header.get("match_id") != mid:
            raise ValueError(f"{mid}: unexpected state header")
        for row in map(json.loads, stream):
            for state in row["heroes"]:
                if state["hero"] in tracks and state.get("life_state") == 0:
                    if state.get("pos") and (state.get("move_speed") or 0) > 0:
                        tracks[state["hero"]][row["t"]] = (state["pos"], state["move_speed"])

    reasons = Counter()
    scenarios = []
    for track in tracks.values():
        for t in range(START, match["last"] - WINDOW + 1, WINDOW):
            segment = [track.get(s) for s in range(t, t + WINDOW + 1)]
            if None in segment:
                reasons["missing_or_dead"] += 1
                continue
            steps = [(dist(p, q), max(v, w)) for (p, v), (q, w) in pairwise(segment)]
            if any(step > JUMP_FACTOR * speed for step, speed in steps):
                reasons["possible_displacement"] += 1
                continue
            if any(step < MIN_STEP for step, _ in steps):
                reasons["paused_or_slow"] += 1
                continue
            pos, speed = segment[0]
            walk = support_comparison({"pos": pos, "move_speed": speed}, segment[-1][0], [], {})
            direct = dist(pos, segment[-1][0])
            sampled_path = sum(step for step, _ in steps)
            scenarios.append((walk["routes"]["walk"]["now"], direct, sampled_path, speed))
    return reasons, scenarios


def metrics(segments):
    scenarios = [scenario for scenario, *_ in segments]
    # Signed, unrounded components sum to observed time minus the direct estimate.
    turns = [(path - direct) / speed for _, direct, path, speed in segments]
    residuals = [WINDOW - path / speed for _, _, path, speed in segments]
    return {
        "evaluated": len(scenarios),
        "median_sampled_detour_seconds": round(median(turns), 2) if turns else None,
        "median_motion_residual_seconds": round(median(residuals), 2) if residuals else None,
        "within_scenarios": sum(low <= WINDOW <= high for low, high in scenarios),
        "faster_than_direct": sum(WINDOW < low for low, _ in scenarios),
        "slower_than_detour": sum(WINDOW > high for _, high in scenarios),
        "direct_mae_seconds": round(mean(abs(low - WINDOW) for low, _ in scenarios), 2)
        if scenarios
        else None,
        "detour_mae_seconds": round(mean(abs(high - WINDOW) for _, high in scenarios), 2)
        if scenarios
        else None,
    }


def review_rows(folder):
    """Read the decision evidence and the separately revealed outcome of each case."""
    packet = json.loads((folder / "cases.json").read_text(encoding="utf-8"))
    mode = packet.get("mode", "lane")
    if mode not in {"lane", "wave", "jungle"} or packet["schema"] != f"{mode}-decision-review/1":
        raise ValueError(f"{folder}: unknown decision report")
    for case in packet["cases"]:
        mid, hero, t = case["match"], case["hero"], case["t"]
        if is_holdout(mid):
            raise ValueError(f"reserved holdout match {mid}")
        key = ("" if mode == "lane" else mode + "-") + f"{mid}-{hero}-{t}"
        if key != case["id"] or Path(key).name != key:
            raise ValueError(f"unexpected case identity in {folder}")
        row = {"case": key, "mode": mode, "match": mid, "hero": hero, "second": t}
        target = case.get("support_opportunity")
        if not target:
            yield {
                **row,
                "reason": "no_target" if "support_opportunity" in case else "missing_evidence",
            }
            continue
        outcome = json.loads((folder / "outcomes" / f"{key}.json").read_text(encoding="utf-8"))
        walk = case.get("arrival", {}).get("routes", {}).get("walk", {})
        followup = outcome.get("support_followup")
        row.update(
            ally=target["hero"],
            now_seconds=walk.get("now"),
            after_six_seconds=walk.get("after_six"),
        )
        if followup is None:
            yield {**row, "reason": "missing_followup"}
            continue
        yield {**row, **walk_hit_window(walk, followup), "reason": "" if walk else "missing_route"}


def write_review_csv(folders, stream):
    fields = (
        "case",
        "mode",
        "match",
        "hero",
        "second",
        "ally",
        "now_seconds",
        "after_six_seconds",
        "hit_offsets",
        "last_hit",
        "complete",
        "now",
        "after_six",
        "reason",
    )
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for folder in folders:
        writer.writerows(review_rows(folder))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/demos-2026-11"))
    parser.add_argument(
        "--review-dir",
        type=Path,
        nargs="+",
        help="write retrospective per-case hit-window CSV from existing review reports",
    )
    args = parser.parse_args()
    if args.review_dir:
        write_review_csv(args.review_dir, sys.stdout)
        return
    all_routes, matches = [], {}
    excluded = Counter()
    for mid in MATCHES:
        reasons, routes = audit_match(args.root, mid)
        excluded.update(reasons)
        all_routes.extend(routes)
        matches[mid] = {"excluded": reasons, **metrics(routes)}
    print(
        json.dumps(
            {
                "matches": matches,
                "total": {"excluded": excluded, **metrics(all_routes)},
                "start_second": START,
                "grid_and_window_seconds": WINDOW,
                "minimum_step_units": MIN_STEP,
                "displacement_speed_factor": JUMP_FACTOR,
                "endpoint": "retrospective_position_at_window_end",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
