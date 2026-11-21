"""Information ceiling of the death-risk model: what if he knew where every enemy was?

DIAGNOSTIC ONLY (U165). The user allowed this one test to break the rule that omniscient
data is never model input (U55), on condition that it changes neither the product nor
the plan. Nothing here is a product model, an input of another script or a page.

The question: deaths by ganks are the hardest to foresee from what the player knows
(28% alerted before the first hit). Is that because the features are weak, or because
the danger was invisible? This script adds the true positions of all living enemies,
seen or not, to the version 3 features of the same rows and compares the boosting model
with and without them, overall and by the main reason of each death.

    death_risk_ceiling.py --root data/demos-2026-11 --out reports/death-risk-ceiling-<date>
"""

import argparse
import json
import math
import pickle
from collections import defaultdict
from pathlib import Path

import pandas as pd
from death_risk_by_reason import by_reason, episode_index
from sklearn.metrics import average_precision_score

from dota_items.contracts.death_risk import FEATURES
from dota_items.experiments.awareness.death_risk_tables import load_tables
from dota_items.modeling.awareness.death_risk_eval import (
    at_false_alarm,
    death_alerts,
    models,
    out_of_fold,
)

SCHEMA = "death-risk-ceiling/2"  # 2: checked input, shared alert measure
TARGET = "dies_20"
HORIZON = 20
FAR = 20000.0
FALSE_ALARM = 0.05
OMNISCIENT = (
    "true_nearest_enemy",
    "true_enemies_1500",
    "true_enemies_3000",
    "true_nearest_unseen",
    "true_unseen_3000",
    "true_nearest_enemy_d1",
    "true_nearest_enemy_d2",
    "true_nearest_unseen_d1",
    "true_nearest_unseen_d2",
)


def truth_at(tracks, seen, hero, t):
    """(nearest enemy, nearest enemy his team cannot see, counts) at second t, or None."""
    here = tracks[hero]["pos"].get(t)
    if here is None:
        return None
    own = tracks[hero]["team"]
    every, unseen = [], []
    for other, track in tracks.items():
        there = track["pos"].get(t)
        if track["team"] == own or there is None:
            continue
        gap = math.hypot(here[0] - there[0], here[1] - there[1])
        every.append(gap)
        if t not in seen.get((other, own), ()):
            unseen.append(gap)
    return {
        "true_nearest_enemy": min(every, default=FAR),
        "true_enemies_1500": sum(d <= 1500 for d in every),
        "true_enemies_3000": sum(d <= 3000 for d in every),
        "true_nearest_unseen": min(unseen, default=FAR),
        "true_unseen_3000": sum(d <= 3000 for d in unseen),
    }


def add_truth(rows, root):
    """The rows of one table, each with the true enemy positions around him (U165 only)."""
    by_match = defaultdict(list)
    for row in rows:
        by_match[row["match_id"]].append(row)
    kept = []
    for mid, mine in by_match.items():
        with (root / "gank-inputs-v2" / f"{mid}.pkl").open("rb") as stream:
            match = pickle.load(stream)  # detect_ganks.py cache, local only
        tracks, seen = match["tracks"], match["seen"]
        for row in mine:
            truth = {
                lag: truth_at(tracks, seen, row["hero"], row["t"] - 5 * lag) for lag in (0, 1, 2)
            }
            if truth[0] is None:
                continue
            keep = {name: row[name] for name in ("match_id", "hero", "t", TARGET, "hit_recent")}
            keep |= {name: row[name] for name in FEATURES} | truth[0]
            for lag in (1, 2):
                for name in ("true_nearest_enemy", "true_nearest_unseen"):
                    earlier = truth[lag]
                    keep[f"{name}_d{lag}"] = truth[0][name] - earlier[name] if earlier else 0.0
            kept.append(keep)
    return kept


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--allow-legacy", action="store_true")
    parser.add_argument(
        "--episodes", type=Path, default=Path("reports/gank-episodes-2026-11-17-r7-draft2")
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    risk, _, deaths, info = load_tables(args.root / args.table, args.allow_legacy)
    args.out.mkdir(parents=True, exist_ok=False)
    frame = pd.DataFrame(add_truth(risk, args.root))
    deaths = pd.DataFrame(deaths)
    del risk
    y = frame[TARGET].to_numpy()
    early = frame["hit_recent"].to_numpy() == 0
    index = episode_index(args.episodes)
    report = {
        "schema": SCHEMA,
        "use": "DIAGNOSTIC ONLY (U165): omniscient inputs; not a product model, never reused",
        "input": info,
        "matches": int(frame["match_id"].nunique()),
        "samples": len(frame),
        "omniscient_features": list(OMNISCIENT),
        "alert_measure": "alert on a sample not hit in the last 3 s; not 'before the first hit'",
        "models": {},
    }
    for name, columns in (
        ("player_knows_v3", FEATURES),
        ("plus_true_positions", FEATURES + OMNISCIENT),
    ):
        scores, _ = out_of_fold(frame, TARGET, columns, models()["boosting"])
        _, threshold = at_false_alarm(y[early], scores[early], FALSE_ALARM)
        reasons = by_reason(death_alerts(frame, deaths, scores, threshold, HORIZON), index)
        report["models"][name] = {
            "average_precision_not_hit_last_3s": round(
                float(average_precision_score(y[early], scores[early])), 4
            ),
            "average_precision_all": round(float(average_precision_score(y, scores)), 4),
            "threshold_at_5_percent_false_alarm": round(threshold, 4),
            "by_reason": reasons,
        }
        shares = {r["reason"]: r["share_alerted_not_hit_last_3s"] for r in reasons}
        print(name, report["models"][name]["average_precision_not_hit_last_3s"], shares, flush=True)
    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out / 'report.json'}")


if __name__ == "__main__":
    main()
