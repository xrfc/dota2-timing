"""Baselines for "will he die in the next seconds" (track B, B2 baseline, U160).

Reads the per-match tables of build_death_risk_table.py and compares, by match-grouped
cross-validation on the non-holdout matches only:

* rule      enemies in sight within 1500 plus missing health, no fitting;
* logistic  standardised logistic regression;
* boosting  sklearn HistGradientBoostingClassifier.

A death is a rare event (a few percent of the samples), so the report leads with average
precision, precision at fixed recall, recall at a fixed false-alarm rate and a calibration
table, not accuracy or AUC alone. Everything is given twice: on all samples and on the
samples where no enemy hero has hit him in the last seconds ("early"), because predicting
a death that is already under way is no warning.

    train_death_risk.py --root data/demos-2026-11 --out reports/death-risk-baseline-<date>
"""

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dota_items.data.death_risk import FEATURES

SCHEMA = "death-risk-baseline/1"
FOLDS = 5
SEED = 20261117
MAIN_HORIZON = 20  # U115's provisional window
ALERT_FALSE_ALARM = 0.05


def load(root):
    risk, deaths = [], []
    for path in sorted((root / "death-risk-v1").glob("*.pkl")):
        with path.open("rb") as stream:
            value = pickle.load(stream)  # written by build_death_risk_table.py, local only
        risk += value["risk"]
        deaths += value["deaths"]
    return pd.DataFrame(risk), pd.DataFrame(deaths)


def rule_score(frame):
    return frame["enemies_visible_near"].to_numpy() + (1 - frame["hp_frac"].to_numpy())


def models():
    return {
        "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        "boosting": lambda: HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.08, random_state=SEED
        ),
    }


def out_of_fold(frame, target, features, make):
    scores = np.zeros(len(frame))
    x, y, groups = frame[list(features)].to_numpy(), frame[target].to_numpy(), frame["match_id"]
    fitted = []
    for train, test in GroupKFold(FOLDS).split(x, y, groups):
        model = make().fit(x[train], y[train])
        scores[test] = model.predict_proba(x[test])[:, 1]
        fitted.append((model, test))
    return scores, fitted


def at_recall(y, scores, recall):
    precision, recalls, _ = precision_recall_curve(y, scores)
    ok = recalls >= recall
    return float(precision[ok].max()) if ok.any() else None


def at_false_alarm(y, scores, rate):
    fpr, tpr, thresholds = roc_curve(y, scores)
    index = np.searchsorted(fpr, rate, side="right") - 1
    return float(tpr[index]), float(thresholds[index])


def calibration(y, scores, bins=10):
    order = np.argsort(scores)
    rows = []
    for part in np.array_split(order, bins):
        rows.append(
            {
                "samples": len(part),
                "mean_predicted": round(float(scores[part].mean()), 4),
                "observed": round(float(y[part].mean()), 4),
            }
        )
    return rows


def measure(y, scores, probabilities=True):
    result = {
        "samples": len(y),
        "positives": int(y.sum()),
        "base_rate": round(float(y.mean()), 4),
        "average_precision": round(float(average_precision_score(y, scores)), 4),
        "roc_auc": round(float(roc_auc_score(y, scores)), 4),
        "precision_at_recall_50": at_recall(y, scores, 0.5),
        "precision_at_recall_72": at_recall(y, scores, 0.725),
        "recall_at_false_alarm_1": at_false_alarm(y, scores, 0.01)[0],
        "recall_at_false_alarm_5": at_false_alarm(y, scores, 0.05)[0],
    }
    if probabilities:
        result["brier"] = round(float(brier_score_loss(y, scores)), 5)
        result["brier_of_base_rate"] = round(float(np.mean((y - y.mean()) ** 2)), 5)
        result["calibration"] = calibration(y, scores)
    return result


def bootstrap_gap(frame, target, first, second, rounds, rng):
    """Match-resampled interval of average precision(first) - average precision(second)."""
    by_match = {mid: np.flatnonzero(part) for mid, part in _match_masks(frame)}
    ids = list(by_match)
    y = frame[target].to_numpy()
    gaps = []
    for _ in range(rounds):
        rows = np.concatenate([by_match[m] for m in rng.choice(ids, len(ids))])
        gaps.append(
            average_precision_score(y[rows], first[rows])
            - average_precision_score(y[rows], second[rows])
        )
    low, high = np.percentile(gaps, [2.5, 97.5])
    return {"mean": round(float(np.mean(gaps)), 4), "low": round(float(low), 4),
            "high": round(float(high), 4), "rounds": rounds}  # fmt: skip


def _match_masks(frame):
    codes, uniques = pd.factorize(frame["match_id"])
    for code, mid in enumerate(uniques):
        yield mid, codes == code


def lead_times(frame, deaths, scores, threshold, horizon):
    """How early the first alert before each death came, on not-yet-hit samples only."""
    early = frame["hit_recent"].to_numpy() == 0
    alerts = frame.loc[early & (scores >= threshold), ["match_id", "hero", "t"]]
    by_hero = {key: part["t"].to_numpy() for key, part in alerts.groupby(["match_id", "hero"])}
    tracked = set(map(tuple, frame[["match_id", "hero"]].drop_duplicates().to_numpy()))
    leads = []
    for row in deaths.itertuples():
        if (row.match_id, row.hero) not in tracked:
            continue
        times = by_hero.get((row.match_id, row.hero), np.array([]))
        before = times[(times < row.t) & (times >= row.t - horizon)]
        leads.append(int(row.t - before.min()) if len(before) else None)
    found = [lead for lead in leads if lead is not None]
    return {
        "deaths": len(leads),
        "alerted_before_being_hit": len(found),
        "share": round(len(found) / len(leads), 4) if leads else None,
        "median_lead_seconds": float(np.median(found)) if found else None,
        "share_with_lead_10_or_more": round(sum(v >= 10 for v in found) / len(leads), 4)
        if leads
        else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=100)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=False)
    frame, deaths = load(args.root)
    rng = np.random.default_rng(SEED)
    early = frame["hit_recent"].to_numpy() == 0
    features = [name for name in FEATURES]
    report = {
        "schema": SCHEMA,
        "use": "track B baseline on non-holdout matches; holdout untouched (U133)",
        "matches": int(frame["match_id"].nunique()),
        "hero_games": int(frame[["match_id", "hero"]].drop_duplicates().shape[0]),
        "samples": len(frame),
        "features": features,
        "folds": FOLDS,
        "main_horizon": MAIN_HORIZON,
        "horizons": {},
    }
    kept = {}
    for horizon in (10, 15, 20):
        target = f"dies_{horizon}"
        y = frame[target].to_numpy()
        entry = {"rule": {"all": measure(y, rule_score(frame), False),
                          "early": measure(y[early], rule_score(frame)[early], False)}}  # fmt: skip
        for name, make in models().items():
            if horizon != MAIN_HORIZON and name != "boosting":
                continue
            scores, fitted = out_of_fold(frame, target, features, make)
            entry[name] = {"all": measure(y, scores), "early": measure(y[early], scores[early])}
            if horizon == MAIN_HORIZON:
                kept[name] = (scores, fitted)
            print(horizon, name, entry[name]["early"]["average_precision"], flush=True)
        report["horizons"][str(horizon)] = entry
    target = f"dies_{MAIN_HORIZON}"
    y = frame[target].to_numpy()
    boosting, fitted = kept["boosting"]
    early_frame = frame[early].reset_index(drop=True)
    report["boosting_minus_logistic_early"] = bootstrap_gap(
        early_frame, target, boosting[early], kept["logistic"][0][early], args.bootstrap, rng
    )
    report["boosting_minus_rule_early"] = bootstrap_gap(
        early_frame, target, boosting[early], rule_score(frame)[early], args.bootstrap, rng
    )
    _, threshold = at_false_alarm(y[early], boosting[early], ALERT_FALSE_ALARM)
    report["alerts"] = {
        "threshold": round(threshold, 4),
        "false_alarm_rate_on_early_samples": ALERT_FALSE_ALARM,
        **lead_times(frame, deaths, boosting, threshold, MAIN_HORIZON),
    }
    model, test = fitted[0]
    pick = rng.choice(test, min(len(test), 100_000), replace=False)
    importance = permutation_importance(
        model, frame[features].to_numpy()[pick], y[pick], scoring="average_precision",
        n_repeats=3, random_state=SEED,
    )  # fmt: skip
    report["permutation_importance_fold_1"] = sorted(
        ({"feature": f, "drop_in_average_precision": round(float(v), 4)}
         for f, v in zip(features, importance.importances_mean, strict=True)),
        key=lambda row: -row["drop_in_average_precision"],
    )  # fmt: skip
    np.savez_compressed(
        args.out / "out-of-fold.npz",
        match_id=frame["match_id"].to_numpy(),
        t=frame["t"].to_numpy(),
        hero=frame["hero"].to_numpy().astype(str),
        y=y,
        hit_recent=frame["hit_recent"].to_numpy(),
        boosting=boosting,
        logistic=kept["logistic"][0],
    )
    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out / 'report.json'}")


if __name__ == "__main__":
    main()
