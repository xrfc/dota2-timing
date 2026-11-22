"""Evaluate observed wave actions by leaving one development match out at a time."""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import average_precision_score

from dota_items.data.awareness_split import is_holdout
from dota_items.data.lane_decisions import ACTION_SECONDS
from dota_items.storage import read_json


def samples(folder):
    report = read_json(folder / "cases.json")
    if report["schema"] != "wave-decision-review/1":
        raise ValueError("expected a before-last-hit wave report")
    rows, excluded, seen = [], Counter(), set()
    for case in report["cases"]:
        mid, key = int(case["match"]), case["id"]
        identity = mid, case["hero"], case["t"]
        if "recent_hero_damage" not in case:
            raise ValueError("regenerate the wave report to include action-window labels")
        if is_holdout(mid) or identity in seen or Path(key).name != key:
            raise ValueError("invalid, repeated or reserved match case")
        seen.add(identity)
        outcome = read_json(folder / "outcomes" / f"{key}.json")
        action = read_json(folder / "actions" / f"{key}.json")["action"]
        if not outcome["complete"] or action not in ("farm", "retreat"):
            excluded["incomplete" if not outcome["complete"] else "unknown_action"] += 1
            continue
        if any(s <= case["t"] + ACTION_SECONDS for s in outcome["death_seconds"]):
            excluded["death_in_action_window"] += 1
            continue
        frame = case["history"][-1]
        if frame["t"] != case["t"]:
            raise ValueError("expected a decision-time frame")
        hp, max_hp = case["hp"]
        features = [
            case["t"],
            case["front_distance"],
            case["nearby_creeps"],
            hp / max_hp if hp is not None and max_hp else None,
            case["mana"],
            sum(enemy["distance"] is not None for enemy in frame["enemies"]),
            frame["ally"][0] if frame["ally"] else None,
            len(case["ready_names"]),
            int(case["recent_hero_damage"]),
            int(action == "farm"),
        ]
        rows.append(
            (
                mid,
                action,
                features,
                outcome["lane_last_hits"] - outcome["action_window_hits"],
                int(any(s > case["t"] + ACTION_SECONDS for s in outcome["death_seconds"])),
            )
        )
    return rows, excluded


def evaluate(rows):
    matches = sorted({row[0] for row in rows})
    if len(matches) < 2:
        raise ValueError("need eligible actions in at least two development matches")
    predictions, unsupported = [], Counter()
    for mid in matches:
        train = [r for r in rows if r[0] != mid]
        test = [r for r in rows if r[0] == mid]
        x = np.asarray([r[2] for r in train], dtype=float)
        available = ~np.isnan(x).all(axis=0)
        x = x[:, available]
        hits, deaths = np.asarray([r[3:] for r in train]).T
        reg = HistGradientBoostingRegressor(random_state=0).fit(x, hits)
        clf = None
        if len(set(deaths)) == 2:
            clf = HistGradientBoostingClassifier(random_state=0).fit(x, deaths)
        for _, action, features, actual_hits, death in test:
            group = [r for r in train if r[1] == action]
            if not group:
                unsupported[action] += 1
                continue
            xx = np.asarray([features], dtype=float)[:, available]
            predictions.append(
                (
                    action,
                    features[-2],
                    actual_hits,
                    death,
                    np.mean([r[3] for r in group]),
                    reg.predict(xx)[0],
                    np.mean([r[4] for r in group]),
                    clf.predict_proba(xx)[0, 1] if clf else deaths.mean(),
                    mid,
                )
            )
    result = {}
    for name in ["all", "farm", "retreat", "no_recent_damage"]:
        part = [
            r
            for r in predictions
            if name in ("all", r[0]) or (name == "no_recent_damage" and not r[1])
        ]
        metrics = {"cases": len(part)}
        if part:
            _, _, hits, deaths, base_hits, tree_hits, base_death, tree_death, games = zip(
                *part, strict=True
            )
            for label, est_hits, risk in [
                ("action_mean", base_hits, base_death),
                ("boosting", tree_hits, tree_death),
            ]:
                metrics[label] = {
                    "hits_mae": float(np.mean(np.abs(np.subtract(hits, est_hits)))),
                    "false_alerts_per_represented_match_at_0_5": float(
                        np.sum((np.asarray(risk) >= 0.5) & (np.asarray(deaths) == 0))
                        / len(set(games))
                    ),
                    "calibration": calibration(deaths, risk),
                    "death_brier": float(np.mean(np.square(np.subtract(deaths, risk)))),
                    "death_ap": float(average_precision_score(deaths, risk))
                    if len(set(deaths)) == 2
                    else None,
                }
        result[name] = metrics
    return {"matches": len(matches), "unsupported": dict(unsupported), "metrics": result}


def calibration(deaths, risks):
    """Show calibration and case counts; include risk 1.0 in the last bin."""
    bins = [[] for _ in range(5)]
    for death, risk in zip(deaths, risks, strict=True):
        bins[min(4, int(risk * 5))].append((death, risk))
    return [
        {
            "lower": index / 5,
            "cases": len(group),
            "observed": float(np.mean([death for death, _ in group])),
            "predicted": float(np.mean([risk for _, risk in group])),
        }
        for index, group in enumerate(bins)
        if group
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    rows, excluded = samples(args.report)
    print(json.dumps({**evaluate(rows), "excluded": excluded}, indent=2))


if __name__ == "__main__":
    main()
