"""Could a gank be seen coming? Visible-only snapshots before ganks and at quiet seconds.

Track B, exploratory (2026-11-12). A snapshot holds only what the evaluated player's team
could know at that second: which living enemies its vision shows, where his allies are and
where he stands. Comparing snapshots a few seconds before a gank with snapshots at quiet
seconds says whether the label is predictable at all from such information. This is
description, not a trained model, and it reads non-holdout matches only.
"""

import math

from dota_items.data.gank_depth import depth

FEATURES = (
    "enemies_missing",
    "enemies_missing_10s",
    "nearest_ally",
    "depth",
    "nearest_visible_enemy",
)
LOOKBACK = 10


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def snapshot(victim, second, tracks, seen, lookback=LOOKBACK):
    """Visible-only features of `victim` at `second`, or None when he is not alive then."""
    here = tracks[victim]["pos"].get(second)
    if here is None:
        return None
    own = tracks[victim]["team"]
    allies, missing, missing_long, visible = [], 0, 0, []
    for hero, track in tracks.items():
        there = track["pos"].get(second)
        if hero == victim or there is None:  # dead heroes are known to be dead
            continue
        if track["team"] == own:
            allies.append(_distance(here, there))
            continue
        shown = seen.get((hero, own), ())
        if second in shown:
            visible.append(_distance(here, there))
        else:
            missing += 1
            missing_long += not any(t in shown for t in range(second - lookback, second))
    return {
        "enemies_missing": missing,
        "enemies_missing_10s": missing_long,
        "nearest_ally": round(min(allies)) if allies else None,
        "depth": round(depth(here, own)),
        "nearest_visible_enemy": round(min(visible)) if visible else None,
    }


def quiet_seconds(victim, tracks, episodes, start, step, margin):
    """Every `step`-th second from `start` when he is alive and no episode is near."""
    busy = [(e["t0"] - margin, e["end"] + margin) for e in episodes]
    seconds = sorted(tracks[victim]["pos"])
    if not seconds:
        return []
    return [
        t
        for t in range(start, seconds[-1] + 1, step)
        if t in tracks[victim]["pos"] and not any(low <= t <= high for low, high in busy)
    ]


def auc(positives, negatives):
    """Chance that a random positive value exceeds a random negative one (ties count half)."""
    if not positives or not negatives:
        return None
    ordered = sorted(negatives)
    import bisect

    wins = 0.0
    for value in positives:
        low, high = bisect.bisect_left(ordered, value), bisect.bisect_right(ordered, value)
        wins += low + (high - low) / 2
    return round(wins / (len(positives) * len(negatives)), 3)


def compare(positive_rows, negative_rows):
    """Per feature: how many rows have it, medians, and the AUC of the raw value."""
    result = {}
    for name in FEATURES:
        pos = sorted(r[name] for r in positive_rows if r[name] is not None)
        neg = sorted(r[name] for r in negative_rows if r[name] is not None)
        result[name] = {
            "positives": len(pos),
            "negatives": len(neg),
            "median_before_gank": pos[len(pos) // 2] if pos else None,
            "median_quiet": neg[len(neg) // 2] if neg else None,
            "auc": auc(pos, neg),
        }
    return result
