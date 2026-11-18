"""Training and evaluation of the death-risk models (track B, U160).

Moved out of scripts/train_death_risk.py, scripts/death_risk_by_reason.py and
scripts/death_risk_ceiling.py (2026-11-17, after a review) so the three share one
implementation of the alert measure and it can be tested.

The alert measure (`death_alerts`): a death counts as alerted when, within `horizon`
seconds before it, some sample with `hit_recent == 0` scored at or above the threshold.
`hit_recent == 0` means "not hit by an enemy hero in the last 3 seconds" (contracts.
death_risk), so an alert 5 seconds after a first hit and 13 seconds before the death
counts. It is NOT a "before the first hit of the fight" recall.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
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

FOLDS = 5
SEED = 20261117
ALERT_FALSE_ALARM = 0.05


def rule_score(frame):
    """Enemies in sight within 1500 plus missing health: no fitting."""
    return frame["enemies_visible_near"].to_numpy() + (1 - frame["hp_frac"].to_numpy())


def models(seed=SEED):
    return {
        "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        "boosting": lambda: HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.08, random_state=seed
        ),
    }


def out_of_fold(frame, target, features, make, folds=FOLDS):
    """Scores from match-grouped cross-validation, and the fitted (model, test rows)."""
    scores = np.zeros(len(frame))
    x, y, groups = frame[list(features)].to_numpy(), frame[target].to_numpy(), frame["match_id"]
    fitted = []
    for train, test in GroupKFold(folds).split(x, y, groups):
        model = make().fit(x[train], y[train])
        scores[test] = model.predict_proba(x[test])[:, 1]
        fitted.append((model, test))
    return scores, fitted


def at_recall(y, scores, recall):
    precision, recalls, _ = precision_recall_curve(y, scores)
    ok = recalls >= recall
    return float(precision[ok].max()) if ok.any() else None


def at_false_alarm(y, scores, rate):
    """(recall, threshold) at the largest false-alarm rate not above `rate`."""
    fpr, tpr, thresholds = roc_curve(y, scores)
    index = np.searchsorted(fpr, rate, side="right") - 1
    return float(tpr[index]), float(thresholds[index])


def calibration(y, scores, bins=10):
    rows = []
    for part in np.array_split(np.argsort(scores), bins):
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
    codes, uniques = pd.factorize(frame["match_id"])
    by_match = [np.flatnonzero(codes == code) for code in range(len(uniques))]
    y = frame[target].to_numpy()
    gaps = []
    for _ in range(rounds):
        rows = np.concatenate([by_match[i] for i in rng.integers(0, len(by_match), len(by_match))])
        gaps.append(
            average_precision_score(y[rows], first[rows])
            - average_precision_score(y[rows], second[rows])
        )
    low, high = np.percentile(gaps, [2.5, 97.5])
    return {
        "mean": round(float(np.mean(gaps)), 4),
        "low": round(float(low), 4),
        "high": round(float(high), 4),
        "rounds": rounds,
    }


def death_alerts(frame, deaths, scores, threshold, horizon):
    """One dict per death of a tracked hero that has samples in the `horizon` before it.

    `frame` needs match_id, hero, t and hit_recent; `deaths` match_id, hero and t.
    `alerted` is true when a sample with hit_recent == 0 in [t - horizon, t) scored at or
    above `threshold`; `lead` is the death second minus the first such sample; `peak` is
    the highest score in the window, whatever hit_recent.
    """
    series = {}
    for key, part in frame.assign(_score=scores).groupby(["match_id", "hero"], sort=False):
        part = part.sort_values("t")
        series[key] = (
            part["t"].to_numpy(),
            part["_score"].to_numpy(),
            part["hit_recent"].to_numpy(),
        )
    found = []
    for death in deaths.itertuples(index=False):
        key = (death.match_id, death.hero)
        if key not in series:
            continue
        times, values, hits = series[key]
        window = (times >= death.t - horizon) & (times < death.t)
        if not window.any():
            continue
        alert = window & (hits == 0) & (values >= threshold)
        found.append(
            {
                "match_id": death.match_id,
                "hero": death.hero,
                "t": int(death.t),
                "alerted": bool(alert.any()),
                "lead": int(death.t - times[alert].min()) if alert.any() else None,
                "peak": float(values[window].max()),
            }
        )
    return found


def summarize_alerts(found):
    """Share alerted (not hit in the last 3 seconds), median lead and median peak."""
    leads = [row["lead"] for row in found if row["alerted"]]
    count = len(found)
    return {
        "deaths": count,
        "alerted_not_hit_last_3s": len(leads),
        "share_alerted_not_hit_last_3s": round(len(leads) / count, 4) if count else None,
        "median_lead_seconds": float(np.median(leads)) if leads else None,
        "share_with_lead_10_or_more": round(sum(v >= 10 for v in leads) / count, 4)
        if count
        else None,
        "median_peak_risk": round(float(np.median([r["peak"] for r in found])), 4)
        if found
        else None,
    }
