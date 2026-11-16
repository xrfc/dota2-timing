"""Coverage numbers for the multi-hero demo collection (data card, 2026-11-16).

Reads only local files of a collection root (receipts, OpenDota match JSON, the parsed
and state-v3 folders) and writes `stats.json` for `docs/demo-data-card.md`.

Positions 1 and 5 use the U8 rule. OpenDota parsed few of these matches (lane_role and
last hits are mostly missing), so positions come from the replays the way track B finds
them (`detect_ganks.read_match`: two heroes of a team mostly in their safelane at 1-10
min, more last hits at 15 min is position 1). That needs the state-v3 file of a match;
the result is kept in detect_ganks' input cache `<root>/gank-inputs-v2/`.

    demo_data_card.py --root data/demos-2026-11 --out reports/demo-data-card-2026-11-16
"""

import argparse
import json
import statistics
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from detect_ganks import match_inputs

from dota_items.data.awareness_split import describe as holdout_rule
from dota_items.data.awareness_split import is_holdout
from dota_items.data.mechanics_api import Knowledge

SCHEMA = "demo-data-card/1"
MIN_RANK = 70  # collect_demos.py: lobby average Divine or higher
RANK_NAMES = {5: "传奇", 6: "万古流芳", 7: "超凡入圣", 8: "冠绝一世"}
DURATION_BANDS = ((15, 25), (25, 35), (35, 45), (45, 60), (60, 999))


def replay_positions(job):
    """{player_slot: 1 or 5} of one match from its replay (U8 rule, track B reader)."""
    root, mid = job
    m = match_inputs(root, mid, root / "gank-inputs-v2")
    found = {}
    for hero, position in m["positions"].items():
        if position in (1, 5):
            pid = m["tracks"][hero]["player_id"]
            found[pid if pid < 5 else 128 + pid - 5] = position
    return mid, found


def share(part, whole):
    return round(part / whole, 4) if whole else None


def spread(values):
    values = sorted(values)
    if not values:
        return None
    return {
        "min": values[0],
        "p25": values[len(values) // 4],
        "median": statistics.median(values),
        "p75": values[3 * len(values) // 4],
        "max": values[-1],
    }


def band_counts(values, bands):
    return {f"{lo}-{hi}": sum(lo <= v < hi for v in values) for lo, hi in bands}


def collect(root):
    receipts = {}
    for path in sorted((root / "receipts").glob("*.json")):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipts[receipt["match_id"]] = receipt
    state = {
        int(p.stem)
        for p in (root / "state-v3" / "receipts").glob("*.json")
        if json.loads(p.read_text(encoding="utf-8")).get("status") == "extracted"
    }
    matches = []
    for mid, receipt in receipts.items():
        if receipt.get("status") != "parsed":
            continue
        match = json.loads((root / "meta" / f"{mid}.json").read_text(encoding="utf-8"))
        matches.append((receipt, match, mid in state))
    return receipts, matches


def summarize(receipts, matches, hero_name, found_positions):
    statuses = Counter(r.get("status") for r in receipts.values())
    skips = Counter(reason for r in receipts.values() for reason in r.get("reasons") or ())
    ranks = [r["avg_rank_tier"] for r, _, _ in matches]
    in_rank = [m for r, m, _ in matches if r["avg_rank_tier"] >= MIN_RANK]
    minutes = [m["duration"] / 60 for _, m, _ in matches]
    starts = [m["start_time"] for _, m, _ in matches]
    picks, pos1, pos5 = Counter(), Counter(), Counter()
    unknown_safelane = 0
    for _, match, done in matches:
        if not done:
            continue
        found = found_positions[match["match_id"]]
        unknown_safelane += 2 - sum(1 for v in found.values() if v == 1)
        for player in match["players"]:
            hero = player["hero_id"]
            picks[hero] += 1
            position = found.get(player["player_slot"])
            if position == 1:
                pos1[hero] += 1
            elif position == 5:
                pos5[hero] += 1
    total = len(matches)
    heroes = sorted(picks, key=lambda h: (-pos1[h], -picks[h]))
    holdout = sum(is_holdout(m["match_id"]) for _, m, _ in matches)
    return {
        "schema": SCHEMA,
        "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "receipts": {"statuses": dict(statuses), "skip_reasons": dict(skips)},
        "parse_modes": dict(Counter(r.get("parse_mode") for r, _, _ in matches)),
        "matches": total,
        "matches_in_rank": len(in_rank),
        "matches_below_rank": total - len(in_rank),
        "rank_bands": {
            RANK_NAMES.get(tier, str(tier)): sum(r // 10 == tier for r in ranks)
            for tier in sorted({r // 10 for r in ranks})
        },
        "avg_rank_tier": spread(ranks),
        "patches": dict(Counter(m["patch"] for _, m, _ in matches)),
        "game_modes": dict(Counter(m["game_mode"] for _, m, _ in matches)),
        "lobby_types": dict(Counter(m["lobby_type"] for _, m, _ in matches)),
        "start_utc": {
            "first": datetime.fromtimestamp(min(starts), UTC).isoformat(),
            "last": datetime.fromtimestamp(max(starts), UTC).isoformat(),
        },
        "duration_minutes": spread([round(v, 1) for v in minutes]),
        "duration_bands": band_counts(minutes, DURATION_BANDS),
        "radiant_win_share": share(sum(m["radiant_win"] for _, m, _ in matches), total),
        "leaver_matches": sum(
            any((p.get("leaver_status") or 0) > 1 for p in m["players"]) for _, m, _ in matches
        ),
        "state_v3_done": sum(done for _, _, done in matches),
        "holdout": {"rule": holdout_rule(), "matches": holdout, "rest": total - holdout},
        "positions": {
            "position_1": sum(pos1.values()),
            "position_5": sum(pos5.values()),
            "teams_without_position": unknown_safelane,
            "teams": 2 * sum(done for _, _, done in matches),
            "from": "replays with state-v3 (U8 rule, detect_ganks.read_match)",
        },
        "heroes_seen": len(picks),
        "hero_pick_bands": band_counts(
            picks.values(), ((0, 20), (20, 50), (50, 100), (100, 10**6))
        ),
        "position_1_heroes": {
            "heroes": sum(1 for h in pos1 if pos1[h]),
            "with_at_least": {n: sum(v >= n for v in pos1.values()) for n in (10, 30, 50, 100)},
        },
        "heroes": [
            {
                "hero_id": h,
                "name_zh": hero_name(h),
                "picks": picks[h],
                "position_1": pos1[h],
                "position_5": pos5[h],
            }
            for h in heroes
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    knowledge = Knowledge()

    def hero_name(hero_id):
        try:
            return knowledge.hero_name(hero_id)
        except KeyError:
            return str(hero_id)

    receipts, matches = collect(args.root)
    jobs = [(args.root, m["match_id"]) for _, m, done in matches if done]
    found = {}
    with ProcessPoolExecutor(args.workers) as pool:
        for number, (mid, value) in enumerate(pool.map(replay_positions, jobs), 1):
            found[mid] = value
            if number % 100 == 0:
                print(f"positions {number}/{len(jobs)}", flush=True)
    stats = summarize(receipts, matches, hero_name, found)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out / 'stats.json'}: {stats['matches']} matches")


if __name__ == "__main__":
    main()
