"""Training and evaluation of the death-risk models (track B, U160).

Moved out of scripts/train_death_risk.py, scripts/death_risk_by_reason.py and
scripts/death_risk_ceiling.py (2026-11-17, after a review) so the three share one
implementation of the alert measure and it can be tested.

The alert measure (`death_alerts`): a death counts as alerted when, within `horizon`
seconds before it, some sample with `hit_recent == 0` scored at or above the threshold.
`hit_recent == 0` means "not hit by an enemy hero in the last 3 seconds" (contracts.
death_risk), so an alert 5 seconds after a first hit and 13 seconds before the death
counts. It is NOT a "before the first hit of the fight" recall.

The fight-level measure (`fight_spans`, `fight_alerts`; user decision U171, 2026-11-18)
replaces it as the main one: a fight is a run of "contact" seconds, where contact is a
hit by an enemy hero (towers and creeps do not count, U173) or a second in which the
enemy team saw him while an enemy hero his team could see was within `contact_distance`
(he was seen and could know it, U172). Contact seconds at most `gap` apart belong to one
fight. An alert counts only on a sample outside every fight, before the start of the
fight he died in. The numbers in FIGHT are the assistant's proposal, not yet confirmed.
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
# Assistant's proposal (2026-11-18), pending the user (U172): seconds between contacts
# within one fight, distance of a visible enemy hero that counts as contact, hit sources.
# On 100 matches, gap 10 / distance 1200 made 59% of the laning deaths' fights longer
# than the 20 s horizon (docs/b2-retrain-checklist.md §2), hence the tighter proposal.
FIGHT = {"gap": 5, "contact_distance": 900, "hit_sources": ("hero",)}


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


def fight_spans(hits, contact, fight=FIGHT):
    """{(match_id, hero): sorted [(start, end)]} of fights, from the `hits` and `contact`
    parts of a table (see the module docstring)."""
    seconds = {}
    for row in hits:
        if row["source"] in fight["hit_sources"]:
            seconds.setdefault((row["match_id"], row["hero"]), set()).add(int(row["t"]))
    for track in contact:
        key = (track["match_id"], track["hero"])
        found = seconds.setdefault(key, set())
        for t, seen, distance in zip(
            track["t"], track["seen_by_enemy"], track["visible_enemy_distance"], strict=True
        ):
            if seen and distance <= fight["contact_distance"]:
                found.add(int(t))
    spans = {}
    for key, found in seconds.items():
        runs = []
        for t in sorted(found):
            if runs and t - runs[-1][1] <= fight["gap"]:
                runs[-1][1] = t
            else:
                runs.append([t, t])
        spans[key] = [tuple(run) for run in runs]
    return spans


def fight_start(spans, death, gap):
    """Start of the fight he died in: the span ending at most `gap` before the death and
    starting no later than it; the death second itself when there was none."""
    for start, end in reversed(spans):
        if start <= death and death - end <= gap:
            return start
        if end < death - gap:
            break
    return death


def in_fight(frame, spans):
    """Boolean array: is the sample (match_id, hero, t) inside one of his fights."""
    out = np.zeros(len(frame), dtype=bool)
    positions = {}
    for index, key in enumerate(zip(frame["match_id"], frame["hero"], strict=True)):
        positions.setdefault(key, []).append(index)
    times = frame["t"].to_numpy()
    for key, rows in positions.items():
        rows = np.array(rows)
        for start, end in spans.get(key, ()):
            inside = (times[rows] >= start) & (times[rows] <= end)
            out[rows[inside]] = True
    return out


def fight_alerts(frame, deaths, scores, threshold, horizon, spans, fight=FIGHT):
    """One dict per death with samples in the `horizon` before it (fight-level measure).

    `alerted`: a sample outside every fight, in [death - horizon, fight start), scored at
    or above `threshold`. `lead_to_fight` and `lead_to_death` count from the first such
    sample. `fight_seconds` is death minus fight start; `could_alert` says whether any
    sample lay outside fights before the fight start within the horizon (a fight longer
    than the horizon leaves none).
    """
    fighting = in_fight(frame, spans)
    series = {}
    for key, part in frame.assign(_score=scores, _fight=fighting).groupby(
        ["match_id", "hero"], sort=False
    ):
        part = part.sort_values("t")
        series[key] = (part["t"].to_numpy(), part["_score"].to_numpy(), part["_fight"].to_numpy())
    found = []
    for death in deaths.itertuples(index=False):
        key = (death.match_id, death.hero)
        if key not in series:
            continue
        times, values, fights = series[key]
        window = (times >= death.t - horizon) & (times < death.t)
        if not window.any():
            continue
        start = fight_start(spans.get(key, ()), int(death.t), fight["gap"])
        before = window & (times < start) & ~fights
        alert = before & (values >= threshold)
        first = times[alert].min() if alert.any() else None
        found.append(
            {
                "match_id": death.match_id,
                "hero": death.hero,
                "t": int(death.t),
                "fight_start": int(start),
                "fight_seconds": int(death.t - start),
                "could_alert": bool(before.any()),
                "alerted": bool(alert.any()),
                "lead_to_fight": int(start - first) if first is not None else None,
                "lead_to_death": int(death.t - first) if first is not None else None,
                "peak": float(values[window].max()),
            }
        )
    return found


def summarize_fight_alerts(found):
    """Shares of deaths alerted before the fight started, over all deaths and over those
    that left a sample before the fight; median leads and fight lengths."""
    count = len(found)
    could = [row for row in found if row["could_alert"]]
    alerted = [row for row in found if row["alerted"]]

    def share(part, whole):
        return round(len(part) / len(whole), 4) if whole else None

    def median(values):
        return float(np.median(values)) if values else None

    return {
        "deaths": count,
        "could_alert": len(could),
        "alerted_before_fight": len(alerted),
        "share_of_all_deaths": share(alerted, found),
        "share_of_deaths_that_could_alert": share(alerted, could),
        "median_lead_to_fight_seconds": median([r["lead_to_fight"] for r in alerted]),
        "median_lead_to_death_seconds": median([r["lead_to_death"] for r in alerted]),
        "median_fight_seconds": median([r["fight_seconds"] for r in found]),
    }


def false_alarm_rate(frame, scores, y, mask, threshold, step):
    """(false-alarm onsets per hour, share of time in false alarm) on the masked samples.

    A false alarm is a sample at or above `threshold` with no death in the horizon
    (y == 0); an onset is one whose previous sample of the same hero was not. Per hour,
    not per sample: a finer step checks more often, so a per-sample rate of 5% means more
    alarms per hour (found when comparing 3 s and 5 s sampling, 2026-11-18).
    """
    order = np.lexsort((frame["t"].to_numpy(), frame["hero"].to_numpy(),
                        frame["match_id"].to_numpy()))  # fmt: skip
    match, hero = frame["match_id"].to_numpy()[order], frame["hero"].to_numpy()[order]
    same = np.r_[False, (match[1:] == match[:-1]) & (hero[1:] == hero[:-1])]
    alarm = ((scores >= threshold) & mask & (y == 0))[order]
    previous = np.r_[False, alarm[:-1]]
    hours = mask.sum() * step / 3600
    if not hours:
        return 0.0, 0.0
    return float((alarm & ~(previous & same)).sum() / hours), float(alarm.sum() / mask.sum())


def threshold_for_rate(frame, scores, y, mask, step, onsets_per_hour, rounds=40):
    """The lowest threshold whose false-alarm onsets per hour do not exceed the target."""
    low, high = 0.0, 1.0
    for _ in range(rounds):
        middle = (low + high) / 2
        if false_alarm_rate(frame, scores, y, mask, middle, step)[0] > onsets_per_hour:
            low = middle
        else:
            high = middle
    return high
