"""Sample jungle and support alternatives in existing replays, using only decision-time anchors."""

import argparse
import tempfile
from bisect import bisect_right
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from itertools import pairwise
from math import dist
from pathlib import Path

from lane_decision_review import hero_hits_by_second, support_opportunity
from lane_study_data import (
    candidates,
    capture,
    file_hash,
    fold_for,
    frame_values,
    normalized_end,
    readonly_match,
    sources,
)
from outcome_labels import METRICS, describe, enrich_from_states, resource_state, write_dataset

from dota_items.data.awareness_split import is_holdout
from dota_items.data.death_risk import death_times
from dota_items.data.lane_decisions import (
    ACTION_SECONDS,
    OUTCOME_SECONDS,
    REPEAT_SECONDS,
    START_SECOND,
    _context,
    farm_seconds,
    jungle_seconds,
    make_jungle_cases,
)
from dota_items.storage import read_json, write_json

STATIC = (
    "time",
    "landmark_distance",
    "signal_age",
    "hp_fraction",
    "mana",
    "ready_saves",
    "recent_damage",
    "move_speed",
    "recent_lane_hits",
    "recent_jungle_hits",
)
DOMAINS = ("jungle", "support")


@lru_cache(maxsize=1)
def knowledge():
    folder = Path(__file__).resolve().parents[1] / "knowledge/awareness"
    return (
        read_json(folder / "map-zones-v1.json")["camps"],
        read_json(folder / "save-means-v2.json")["means"],
    )


def walking_path(track, t):
    path = [track.get(s) for s in range(t, t + ACTION_SECONDS + 1)]
    if any(p is None for p in path) or any(dist(a, b) > 700 for a, b in pairwise(path)):
        return None
    return path


def jungle_action(track, t, camp, hits):
    path = walking_path(track, t)
    if path is None:
        return "unknown"
    leaving = dist(path[-1], camp) - dist(path[0], camp) >= 350
    farming = bisect_right(hits, t + ACTION_SECONDS) > bisect_right(hits, t)
    if leaving != farming:
        return "leave_camp" if leaving else "continue_jungle"
    return "unknown"


def support_action(track, t, target):
    path = walking_path(track, t)
    if path is None:
        return "unknown"
    change = dist(path[0], target) - dist(path[-1], target)
    if change >= 350 or dist(path[-1], target) <= 400:
        return "approach"
    return "stay" if change < 100 else "unknown"


def arrived(own, ally, t, hit_seconds, own_states):
    """Joint event of an allied hit and own presence within 400 at that same second."""
    unknown = False
    for s in hit_seconds:
        if not t + ACTION_SECONDS < s <= t + OUTCOME_SECONDS:
            continue
        if own_states.get(s, {}).get("life_state") in (1, 2):
            continue
        a, b = own.get(s), ally.get(s)
        if a is None or b is None:
            unknown = True
        elif dist(a, b) <= 400:
            return 1
    return None if unknown else 0


def support_anchors(tracks, damage, hero):
    next_t = START_SECOND
    result = {}
    for t in sorted(tracks[hero]["pos"]):
        if t < next_t:
            continue
        signal = support_opportunity(tracks, damage, hero, t)
        if signal and 400 < signal["distance"] <= 6000:
            result[t] = signal
            next_t = t + REPEAT_SECONDS
    return result


def count(hits, start, stop):
    return bisect_right(hits, stop) - bisect_right(hits, start)


def record(e, kind, state, landmark, age, action, hits, deaths, end, damage, lane, jungle):
    t, hero = e["t"], e["hero"]
    if t + ACTION_SECONDS > end:
        action = "unknown"
    early = count(deaths, t, t + ACTION_SECONDS) > 0
    eligible = action != "unknown" and not early and t + OUTCOME_SECONDS <= end
    recent = any(hero in damage.get(s, ()) for s in range(t - 3, t + 1))
    history = {f["t"]: frame_values(f) for f in e["history"]}
    hp, maximum = e["hp"]
    return {
        "match": e["match"],
        "fold": fold_for(e["match"]),
        "domain": kind,
        "hero": hero,
        "t": t,
        "static": [
            t,
            landmark,
            age,
            hp / maximum if hp is not None and maximum else None,
            e["mana"],
            len(e["ready_names"]),
            int(recent),
            state.get("move_speed"),
            count(lane, t - 6, t),
            count(jungle, t - 6, t),
        ],
        "sequence": [history.get(s, [None] * len(history[t])) for s in (t - 10, t - 5, t)],
        "action": action,
        "recent_damage": recent,
        "action_complete": t + ACTION_SECONDS <= end,
        "window_complete": t + OUTCOME_SECONDS <= end,
        "early_death": early,
        "behavior_eligible": action != "unknown",
        "outcome_eligible": eligible,
        "death": int(count(deaths, t + ACTION_SECONDS, t + OUTCOME_SECONDS) > 0)
        if eligible
        else None,
        "hits": count(hits, t + ACTION_SECONDS, t + OUTCOME_SECONDS) if eligible else None,
    }


def domain_match(root, mid, *, holdout=False):
    if is_holdout(mid) != holdout:
        raise ValueError("wrong U133 partition")
    match = readonly_match(root, mid)
    end = min(match["last"], normalized_end(root / "parsed" / f"{mid}.normalized.json.gz", mid))
    heroes = sorted(h for h, role in match["positions"].items() if role == 1)
    visibility = {k: sorted(v) for k, v in match["seen"].items()}
    damage = hero_hits_by_second(match)
    lane = {h: farm_seconds(match["combat"], h, match["tracks"][h]["team"]) for h in heroes}
    jungle = {h: jungle_seconds(match["combat"], h) for h in heroes}
    signals = {h: support_anchors(match["tracks"], damage, h) for h in heroes}
    wanted = {h: set(jungle[h]) | set(signals[h]) for h in heroes}
    resources, states = defaultdict(dict), defaultdict(dict)
    match["dead_at"] = defaultdict(set)
    for frame in capture(root, "state-v3", mid, "gem-state-capture/3"):
        t = frame["t"]
        for hero in frame["heroes"]:
            name = hero["hero"]
            if hero.get("life_state") in (1, 2):
                match["dead_at"][t].add(name)
            if name in wanted:
                resources[name][t] = resource_state(hero)
                if t in wanted[name]:
                    states[name][t] = hero

    camps, means = knowledge()
    points = {c["id"]: (c["x"], c["y"]) for c in camps}
    rows = []
    rank = read_json(root / "receipts" / f"{mid}.json")["avg_rank_tier"]
    for h in heroes:
        own = match["tracks"][h]["pos"]
        deaths = death_times(match["combat"], h)
        for e, _, _ in make_jungle_cases(
            match, mid, h, jungle[h], visibility, states[h], means, deaths, camps
        ):
            t = e["t"]
            if t <= end:
                action = jungle_action(own, t, points[e["camp_id"]], jungle[h])
                rows.append(
                    record(
                        e,
                        "jungle",
                        states[h][t],
                        e["camp_distance"],
                        None,
                        action,
                        jungle[h],
                        deaths,
                        end,
                        damage,
                        lane[h],
                        jungle[h],
                    )
                )
        all_hits = sorted(lane[h] + jungle[h])
        for t, signal in signals[h].items():
            if t > end or t not in states[h]:
                continue
            ally = signal["hero"]
            ally_pos = match["tracks"][ally]["pos"]
            e = _context(match, mid, h, t, visibility, states[h][t], means)
            action = support_action(own, t, ally_pos[t])
            row = record(
                e,
                "support",
                states[h][t],
                signal["distance"],
                signal["seconds_ago"],
                action,
                all_hits,
                deaths,
                end,
                damage,
                lane[h],
                jungle[h],
            )
            seconds = [s for s in range(t + 7, t + 21) if ally in damage.get(s, ())]
            row["arrival"] = (
                arrived(own, ally_pos, t, seconds, resources[h])
                if row["outcome_eligible"]
                else None
            )
            row["target_hit_again"] = bool(seconds) if row["outcome_eligible"] else None
            rows.append(row)
    for r in rows:
        r["rank_band"] = "70+" if rank >= 70 else "60-69"
    return enrich_from_states(root, mid, rows, resources) if rows else []


def checked_domain_job(job):
    root, mid = job
    if is_holdout(mid):
        raise ValueError("reserved development input")
    inputs = sources(root, None, mid)
    try:
        return domain_match(root, mid), None, inputs
    except (ValueError, EOFError) as exc:
        # Same explicit replay clock/count exclusions as the lane cohort. Propagate code errors.
        if not (
            str(exc).startswith(f"{mid}: non-increasing")
            or str(exc).startswith(f"{mid}: incomplete")
            or isinstance(exc, EOFError)
        ):
            raise
        return [], str(exc) or "unexpected end of replay input", inputs


def check_pilot(path, rows, ids, rejected):
    ref = read_json(path / "cases.json")
    if ref["schema"] != "jungle-decision-review/1":
        raise ValueError("wrong jungle reference report")
    reference = {(r["match"], r["hero"], r["t"]) for r in ref["cases"]}
    games = {m for m, _, _ in reference}
    if any(is_holdout(m) for m in games):
        raise ValueError("reserved pilot match")
    included = (games & set(ids)) - set(rejected)
    expected = {k for k in reference if k[0] in included}
    actual = {
        (r["match"], r["hero"], r["t"])
        for r in rows
        if r["domain"] == "jungle" and r["match"] in included
    }
    if expected != actual:
        raise ValueError("jungle anchor identities differ from the reference")
    return {
        "reference": len(reference),
        "verified": len(actual),
        "reference_games": len(games),
        "verified_games": len(included),
        "reference_sha256": file_hash(path / "cases.json"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ("root", "out", "pilot"):
        ap.add_argument("--" + arg, type=Path, required=True)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    if args.out.exists():
        ap.error("choose a new output directory")
    ready, more = candidates(args.root, min_rank=60)
    ids = sorted(ready + more)
    rows = []
    rejected, input_hashes = {}, {}
    with ProcessPoolExecutor(args.workers) as pool:
        for i, (mid, (part, reason, inputs)) in enumerate(
            zip(ids, pool.map(checked_domain_job, ((args.root, m) for m in ids)), strict=True), 1
        ):
            input_hashes[mid] = inputs
            if reason:
                rejected[mid] = reason
            rows.extend(part)
            if i % 50 == 0:
                print(i, "games processed", flush=True)
    verification = check_pilot(args.pilot, rows, ids, rejected)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        folder = Path(tmp) / "domains"
        folder.mkdir()
        write_json(
            folder / "manifest.json",
            {
                "matches": ids,
                "rejected_matches": rejected,
                "inputs_sha256": input_hashes,
                "pilot": verification,
                "source_sha256": file_hash(Path(__file__)),
                "static_features": STATIC,
            },
        )
        for domain in DOMAINS:
            part = [r for r in rows if r["domain"] == domain]
            targets = (*METRICS, "arrival") if domain == "support" else METRICS
            write_dataset(
                folder / domain,
                part,
                {
                    "schema": "outcome-labels/1",
                    "split": "development",
                    "domain": domain,
                    "cohort_sha256": file_hash(folder / "manifest.json"),
                    "rank_eligible": dict(
                        Counter(r["rank_band"] for r in part if r["outcome_eligible"])
                    ),
                    **describe(part, targets),
                },
            )
        folder.rename(args.out)


if __name__ == "__main__":
    main()
