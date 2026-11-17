"""How much did a death cost? A win-state model to rank deaths in a review (track B).

Step 1 fits "does Radiant win" on the public team state (net worth, levels, towers,
heroes alive, game clock) sampled every 30 seconds, with match-grouped cross-validation
on the non-holdout matches, and reports Brier score, AUC and calibration.

Step 2 gives every death a swing: the win probability of the victim's team `after`
seconds after the death minus the one `before` seconds before it, from the fold model
that did not see that match. The swing is what happened around the death (the whole
fight, not only this hero), so it ranks deaths; it is not the causal cost of one death.

    death_importance.py --root data/demos-2026-11 --out reports/death-importance-<date>
"""

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SCHEMA = "death-importance/1"
FEATURES = ("minute", "net_worth_diff", "net_worth_share", "level_diff", "alive_diff", "tower_diff")
FOLDS = 5
SEED = 20261117
TRAIN_STEP = 30
BEFORE, AFTER = 5, 30
BANDS = ((0, 10), (10, 20), (20, 30), (30, 45), (45, 999))


def load(root):
    win, deaths = [], []
    for path in sorted((root / "death-risk-v1").glob("*.pkl")):
        with path.open("rb") as stream:
            value = pickle.load(stream)  # written by build_death_risk_table.py, local only
        win += value["win"]
        deaths += value["deaths"]
    frame = pd.DataFrame(win)
    frame["net_worth_share"] = frame["net_worth_diff"] / frame["net_worth_total"].clip(lower=1)
    return frame, pd.DataFrame(deaths)


def calibration(y, scores, bins=10):
    rows = []
    for part in np.array_split(np.argsort(scores), bins):
        rows.append({"mean_predicted": round(float(scores[part].mean()), 3),
                     "observed": round(float(y[part].mean()), 3)})  # fmt: skip
    return rows


def spread(values):
    values = np.asarray(values)
    return {
        "count": len(values),
        "mean": round(float(values.mean()), 4),
        **{f"p{q}": round(float(np.percentile(values, q)), 4) for q in (10, 25, 50, 75, 90)},
        "share_worse_than_minus_5_points": round(float((values < -0.05).mean()), 4),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=False)
    frame, deaths = load(args.root)
    x, y = frame[list(FEATURES)].to_numpy(), frame["radiant_win"].to_numpy()
    train_rows = (frame["t"] % TRAIN_STEP == 0).to_numpy()
    makers = {
        "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        "boosting": lambda: HistGradientBoostingClassifier(max_iter=200, random_state=SEED),
    }
    scores = {name: np.zeros(len(frame)) for name in makers}
    for train, test in GroupKFold(FOLDS).split(x, y, frame["match_id"]):
        train = train[train_rows[train]]
        for name, make in makers.items():
            scores[name][test] = make().fit(x[train], y[train]).predict_proba(x[test])[:, 1]
    report = {
        "schema": SCHEMA,
        "use": "ranking deaths in a review; uses the full public state, not a model input",
        "matches": int(frame["match_id"].nunique()),
        "features": list(FEATURES),
        "win_model": {},
    }
    minute = frame["minute"].to_numpy()
    for name, values in scores.items():
        rows = train_rows
        report["win_model"][name] = {
            "samples": int(rows.sum()),
            "brier": round(float(brier_score_loss(y[rows], values[rows])), 4),
            "brier_of_always_half": 0.25,
            "roc_auc": round(float(roc_auc_score(y[rows], values[rows])), 4),
            "calibration": calibration(y[rows], values[rows]),
            "by_minute": {
                f"{lo}-{hi}": {
                    "brier": round(float(brier_score_loss(y[m], values[m])), 4),
                    "accuracy": round(float(((values[m] > 0.5) == y[m]).mean()), 4),
                }
                for lo, hi in BANDS
                if (m := rows & (minute >= lo) & (minute < hi)).sum() > 500
            },
        }
    chosen = "logistic"  # smooth in the inputs, so a swing is not a tree-split artefact
    frame["p_radiant"] = scores[chosen]
    lookup = {mid: part.set_index("t")["p_radiant"] for mid, part in frame.groupby("match_id")}
    swings = []
    for row in deaths.itertuples():
        series = lookup.get(row.match_id)
        if series is None:
            continue
        times = series.index.to_numpy()
        before = times[times <= row.t - BEFORE]
        after = times[times >= row.t + AFTER]
        if not len(before):
            continue
        p0 = series.loc[before[-1]]
        p1 = series.loc[after[0]] if len(after) else series.iloc[-1]
        sign = 1 if row.team == 2 else -1
        swings.append(
            {
                "match_id": int(row.match_id),
                "hero": row.hero,
                "t": int(row.t),
                "position": None if pd.isna(row.position) else int(row.position),
                "win_before": round(float(p0 if sign == 1 else 1 - p0), 4),
                "swing": round(float(sign * (p1 - p0)), 4),
            }
        )
    table = pd.DataFrame(swings)
    report["swing"] = {
        "model": chosen,
        "before_seconds": BEFORE,
        "after_seconds": AFTER,
        "all_deaths": spread(table["swing"]),
        "position_1": spread(table.loc[table["position"] == 1, "swing"]),
        "position_5": spread(table.loc[table["position"] == 5, "swing"]),
        "position_1_by_minute": {
            f"{lo}-{hi}": spread(part["swing"])
            for lo, hi in BANDS
            if len(
                part := table[
                    (table["position"] == 1) & (table["t"] >= lo * 60) & (table["t"] < hi * 60)
                ]
            )
        },
    }
    table.to_json(args.out / "death-swings.jsonl", orient="records", lines=True)
    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "swing"}, ensure_ascii=False)[:1500])
    print(json.dumps(report["swing"], ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
