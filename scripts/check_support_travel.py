"""Audit walking scenarios on retrospectively observed endpoints in three 7.41f replays.

Run PYTHONPATH=src .venv/bin/python scripts/check_support_travel.py from the repository.
Outputs JSON to stdout. The endpoint is taken from the replay after eight seconds.
This measures traversal timing on moving segments, not support intent or fight arrival.
"""

import argparse
import gzip
import json
from collections import Counter
from itertools import pairwise
from math import dist
from pathlib import Path
from statistics import mean

from detect_ganks import match_inputs

from dota_items.data.awareness_split import is_holdout
from dota_items.data.support_arrival import support_comparison

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
            scenarios.append(walk["routes"]["walk"]["now"])
    return reasons, scenarios


def metrics(scenarios):
    return {
        "evaluated": len(scenarios),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/demos-2026-11"))
    args = parser.parse_args()
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
