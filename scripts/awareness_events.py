"""Teleports and smoke breaks around ganks (gap list items 8 and 9, U154). Description only.

    PYTHONPATH=src .venv/bin/python scripts/awareness_events.py \
        --root data/demos-2026-11 --episodes reports/gank-episodes-2026-11-11-r6 \
        --out reports/awareness-events-2026-11-15

Reads the frozen round's `episodes.jsonl` and the per-match cache of detect_ganks.py
(`<root>/gank-inputs-v2/`); holdout matches are refused (U133). Writes `events.json`:

* teleports   how many casts landed, and for each gank class how many episodes had an
              attacker who teleported in (landed within `--tp-window` seconds before the
              start, up to 5 seconds after, within `--tp-radius` of the victim)
* scans       (with `--scans`, reads the parsed combat logs, slower) how often each class of
              gank had the victim's team scan in the `--scan-window` seconds before the start
              (the log has the time and the team of each Scan, not where it was aimed)
* smoke       how long smokes lasted and what was near when they ended; for ganks with a
              smoked attacker, when that smoke ended relative to the start and how far
              from the victim

Nothing here changes a rule or a label.
"""

import argparse
import gzip
import json
import math
import pickle
from collections import Counter
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.smoke_breaks import BREAK_RANGE, describe_breaks, smoke_spans
from dota_items.data.teleports import arrived_near, teleports

SCAN_MODIFIER = "modifier_radar_thinker"
ZONES = Path(__file__).resolve().parents[1] / "knowledge/awareness/map-zones-v1.json"


def gank_class(episode):
    if not episode["is_gank"]:
        return None
    return "gank" if episode["label"] in ("death", "save_escape") else episode["label"]


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tp-window", type=int, default=30)
    parser.add_argument("--tp-radius", type=int, default=3000)
    parser.add_argument("--scans", action="store_true", help="also count Scans (slow)")
    parser.add_argument("--scan-window", type=int, default=30)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    zones = json.loads(ZONES.read_text(encoding="utf-8"))
    by_match = {}
    with (args.episodes / "episodes.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            episode = json.loads(line)
            by_match.setdefault(episode["match_id"], []).append(episode)
    casts = landed = 0
    with_tp, totals, laning_other, laning_other_tp = Counter(), Counter(), 0, 0
    smoke_end = Counter()
    lasted = []
    gank_smoke = []
    scanned, scans_total = Counter(), 0
    for mid, episodes in sorted(by_match.items()):
        if is_holdout(mid):
            raise SystemExit(f"{mid} is in the track B holdout (U133)")
        with (args.root / "gank-inputs-v2" / f"{mid}.pkl").open("rb") as stream:
            match = pickle.load(stream)  # written by detect_ganks.py, local only
        tracks, combat = match["tracks"], match["combat"]
        tps = teleports(tracks, combat)
        casts += len(tps)
        landed += sum(r["landed"] is not None for r in tps)
        deaths = tower_deaths(combat)
        spans = describe_breaks(
            smoke_spans(combat),
            tracks,
            lambda second, deaths=deaths: (
                standing_towers(zones, deaths, second) + zones["fountains"]
            ),
        )
        for span in spans:
            lasted.append(span["lasted"])
            if span["lasted"] >= 44:
                smoke_end["ran_out"] += 1
                continue
            # Positions are once a second and both sides move, so the distance at the end
            # second overshoots the break distance; report it in bands instead of a rule.
            near = [
                n["distance"]
                for n in (span.get("nearest_enemy_hero"), span.get("nearest_enemy_building"))
                if n
            ]
            gap = min(near, default=None)
            if gap is None:
                band = "no_position"
            elif gap <= BREAK_RANGE + 150:
                band = f"enemy_within_{BREAK_RANGE + 150}"
            elif gap <= 2000:
                band = "enemy_within_2000"
            else:
                band = "enemy_further_than_2000"
            smoke_end[f"ended_early_{band}"] += 1
        scans = []
        if args.scans:
            parsed = args.root / "parsed" / f"{mid}.normalized.json.gz"
            with gzip.open(parsed, "rt", encoding="utf-8") as stream:
                log = json.load(stream)["context"]["channels"]["combat_log"]
            scans = [
                (e["time"], e["payload"].get("attacker_team"))
                for e in log
                if e["payload"].get("log_type") == "MODIFIER_ADD"
                and e["payload"].get("inflictor_name") == SCAN_MODIFIER
            ]
            scans_total += len(scans)
        for episode in episodes:
            kind = gank_class(episode)
            if kind is None:
                continue
            totals[kind] += 1
            if args.scans:
                own = tracks[episode["victim"]]["team"]
                scanned[kind] += any(
                    team == own and episode["t0"] - args.scan_window <= t <= episode["t0"]
                    for t, team in scans
                )
            victim, t0 = episode["victim"], episode["t0"]
            place = tracks[victim]["pos"].get(t0)
            if place is None:
                continue
            came = [
                a
                for a in episode["attackers"]
                if arrived_near(tps, a, place, t0 - args.tp_window, t0 + 5, args.tp_radius)
            ]
            with_tp[kind] += bool(came)
            other = (episode.get("depth") or {}).get("attackers_from_other_lanes") or []
            if t0 < 600 and other:
                laning_other += 1
                laning_other_tp += any(a in came for a in other)
            for attacker in episode.get("smoked_attackers") or []:
                mine = [
                    s
                    for s in spans
                    if s["hero"] == attacker and s["start"] <= t0 + 5 and s["end"] >= t0 - 30
                ]
                for span in mine:
                    there = tracks[attacker]["pos"].get(span["end"])
                    gank_smoke.append(
                        {
                            "class": kind,
                            "ended_before_start": t0 - span["end"],
                            "distance_to_victim": round(math.dist(there, place)) if there else None,
                        }
                    )
    result = {
        "use": "description_only",
        "frozen_round": str(args.episodes),
        "matches": len(by_match),
        "teleports": {
            "casts": casts,
            "landed": landed,
            "window_seconds": args.tp_window,
            "radius": args.tp_radius,
            "episodes_with_an_attacker_who_teleported_in": {
                k: {
                    "episodes": totals[k],
                    "with_teleport": with_tp[k],
                    "share": round(with_tp[k] / totals[k], 3),
                }
                for k in sorted(totals)
            },
            "laning_ganks_with_attackers_from_other_lanes": laning_other,
            "of_which_an_other_lane_attacker_teleported_in": laning_other_tp,
        },
        "scans": (
            {
                "scans": scans_total,
                "window_seconds": args.scan_window,
                "episodes_where_the_victims_team_scanned_before": {
                    k: {
                        "episodes": totals[k],
                        "scanned": scanned[k],
                        "share": round(scanned[k] / totals[k], 3),
                    }
                    for k in sorted(totals)
                },  # fmt: skip
            }
            if args.scans
            else None
        ),
        "smoke": {
            "smokes": len(lasted),
            "median_seconds": median(lasted),
            "how_it_ended": dict(smoke_end),
            "gank_smokes": len(gank_smoke),
            "gank_smoke_ended_seconds_before_start_median": median(
                [g["ended_before_start"] for g in gank_smoke]
            ),
            "gank_smoke_distance_to_victim_when_ended_median": median(
                [g["distance_to_victim"] for g in gank_smoke if g["distance_to_victim"] is not None]
            ),
            "gank_smoke_ended_within_10s_before_start": sum(
                0 <= g["ended_before_start"] <= 10 for g in gank_smoke
            ),
        },
    }
    text = json.dumps(result, ensure_ascii=False, indent=1)
    (args.out / "events.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
