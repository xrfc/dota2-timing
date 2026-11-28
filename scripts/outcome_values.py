"""Evaluate action-specific consequences by propensity stratification and Hájek weighting."""

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from lane_study import SEED
from lane_study_baselines import _features
from lane_study_data import file_hash, fold_for
from outcome_labels import METRICS
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from dota_items.data.awareness_split import is_holdout
from dota_items.storage import read_json, write_json

DOMAINS = {
    "wave": (("farm", "retreat"), METRICS),
    "jungle": (("continue_jungle", "leave_camp"), METRICS),
    "support": (("approach", "stay"), (*METRICS, "arrival")),
}
TRIM = 0.05
BINS = 5
MIN_EFFECTIVE = 8
MIN_ROWS = 10
MIN_GAMES = 5


def usable(rows, weights):
    effective = float(weights.sum() ** 2 / (weights @ weights)) if len(weights) else 0.0
    return (
        len(rows) >= MIN_ROWS
        and len({r["match"] for r in rows}) >= MIN_GAMES
        and effective >= MIN_EFFECTIVE
    ), effective


def weighted_arm(rows, probabilities, targets):
    weights = 1 / np.asarray(probabilities)
    support, size = usable(rows, weights)
    result = {
        "supported": support,
        "rows": len(rows),
        "games": len({r["match"] for r in rows}),
        "arm_effective_n": size,
        "values": {},
        "effective_n": {},
    }
    for key in targets:
        mask = np.array([r[key] is not None for r in rows], dtype=bool)
        known = [r for r in rows if r[key] is not None]
        ok, size = usable(known, weights[mask])
        result["effective_n"][key] = size
        result["values"][key] = (
            float(np.average([r[key] for r in known], weights=weights[mask])) if ok else None
        )
    return result


def pareto(values, targets):
    first, second = values
    differences = []
    for key in targets:
        a, b = values[first][key], values[second][key]
        if a is None or b is None:
            return "incomplete"
        if not np.isclose(a, b, rtol=1e-12, atol=1e-10):
            differences.append((a < b) if key in ("death", "dead_seconds") else (a > b))
    if not differences:
        return "tie"
    if all(differences):
        return first
    return "tradeoff" if any(differences) else second


def balance(x, first, p):
    """Maximum absolute mean difference in units of the unweighted within-stratum SD."""
    a, b = x[first], x[~first]
    denom = x.std(axis=0)
    cols = denom > 0
    if not cols.any():
        return {"before": 0.0, "after": 0.0}

    def maximum(diff):
        return float(np.max(abs(diff[cols]) / denom[cols]))

    return {
        "before": maximum(a.mean(axis=0) - b.mean(axis=0)),
        "after": maximum(
            np.average(a, axis=0, weights=1 / p[first])
            - np.average(b, axis=0, weights=1 / (1 - p[~first]))
        ),
    }


def fit_value(rows, arms, targets):
    if not rows or any(r["action"] not in arms for r in rows):
        raise ValueError("expected recognized training actions")
    x = _features(rows)
    first = np.asarray([r["action"] == arms[0] for r in rows])
    model = {
        "arms": arms,
        "targets": targets,
        "propensity": None,
        "frequency": float(first.mean()),
        "strata": {},
        "mean": {},
    }
    for arm in arms:
        part = [r for r in rows if r["action"] == arm]
        model["mean"][arm] = {}
        for key in targets:
            known = [r[key] for r in part if r[key] is not None]
            model["mean"][arm][key] = float(np.mean(known)) if known else None
    if first.all() or not first.any():
        return model
    pipe = model["propensity"] = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
        StandardScaler(),
        LogisticRegression(C=1, max_iter=1000, random_state=SEED),
    ).fit(x, first)
    p = pipe.predict_proba(x)[:, 1]
    lower = max(float(p[first].min()), float(p[~first].min()), TRIM)
    upper = min(float(p[first].max()), float(p[~first].max()), 1 - TRIM)
    model["common_range"] = (lower, upper)
    in_range = (p >= lower) & (p <= upper)
    scaled = pipe[:-1].transform(x)
    for i in range(BINS):
        mask = in_range & ((p * BINS).astype(int) == i)
        stats = {}
        for arm, treatment, probability in zip(arms, (first, ~first), (p, 1 - p), strict=True):
            ix = np.flatnonzero(mask & treatment)
            stats[arm] = weighted_arm([rows[j] for j in ix], probability[ix], targets)
        model["strata"][i] = {
            "arms": stats,
            "balance": balance(scaled[mask], first[mask], p[mask])
            if all(s["supported"] for s in stats.values())
            else None,
        }
    return model


def estimate(model, rows):
    if not rows:
        return []
    propensity = (
        np.full(len(rows), model["frequency"])
        if model["propensity"] is None
        else model["propensity"].predict_proba(_features(rows))[:, 1]
    )
    results = []
    for probability in propensity:
        p = float(probability)
        i = min(BINS - 1, int(p * BINS))
        rec = {
            "propensity": p,
            "stratum": i,
            "overlap_reason": None,
            "ranking": None,
            "values": None,
        }
        if not TRIM <= p <= 1 - TRIM:
            rec["overlap_reason"] = "extreme_propensity"
        elif not model["common_range"][0] - 1e-12 <= p <= model["common_range"][1] + 1e-12:
            rec["overlap_reason"] = "outside_training_common_range"
        elif not all(a["supported"] for a in model["strata"][i]["arms"].values()):
            rec["overlap_reason"] = "sparse_training_arm"
        else:
            rec["values"] = {
                arm: model["strata"][i]["arms"][arm]["values"] for arm in model["arms"]
            }
            rec["ranking"] = pareto(rec["values"], model["targets"])
        results.append(rec)
    return results


def score(model, rows):
    result = []
    for row, pred in zip(rows, estimate(model, rows), strict=True):
        result.append(
            {
                **{k: row[k] for k in ("match", "hero", "t", "fold", "action")},
                "rank_band": row.get("rank_band"),
                "observed": {k: row[k] for k in model["targets"]},
                "mean": model["mean"][row["action"]],
                **pred,
            }
        )
    return result


def summary(records, arms, targets):
    supported = [r for r in records if r["values"] is not None]
    metrics, expected = {}, {}
    for key in targets:
        pairs = [
            r["values"] for r in supported if all(r["values"][a][key] is not None for a in arms)
        ]
        expected[key] = {
            "paired_cases": len(pairs),
            **{a: float(np.mean([v[a][key] for v in pairs])) if pairs else None for a in arms},
        }
        metrics[key] = {}
        for arm in ("all", *arms):
            obs = [
                r
                for r in supported
                if (arm == "all" or r["action"] == arm)
                and r["observed"][key] is not None
                and r["values"][r["action"]][key] is not None
            ]
            metric = "brier" if key in ("death", "arrival") else "mae"
            power = 2 if metric == "brier" else 1
            result = {"n": len(obs), "metric": metric, "value": None, "action_mean": None}
            if obs:
                y = np.asarray([r["observed"][key] for r in obs])
                for name, pred in (
                    ("value", [r["values"][r["action"]][key] for r in obs]),
                    ("action_mean", [r["mean"][key] for r in obs]),
                ):
                    result[name] = float(np.mean(np.abs(y - pred) ** power))
            metrics[key][arm] = result
    return {
        "eligible": len(records),
        "matches": len({r["match"] for r in records}),
        "overlap_supported": len(supported),
        "unsupported_fraction": 1 - len(supported) / len(records) if records else None,
        "overlap_exclusions": dict(
            Counter(r["overlap_reason"] for r in records if r["overlap_reason"])
        ),
        "rankings": dict(Counter(r["ranking"] for r in supported)),
        "expected": expected,
        "factual": metrics,
    }


def population_summary(records, arms, targets):
    stats = summary(records, arms, targets)
    bands = sorted({r["rank_band"] for r in records if r["rank_band"] is not None})
    stats["by_rank"] = {
        band: summary([r for r in records if r["rank_band"] == band], arms, targets)
        for band in bands
    }
    return stats


def read_dataset(folder, domain):
    meta = read_json(folder / "summary.json")
    path = folder / "rows.jsonl"
    if (
        meta.get("schema") != "outcome-labels/1"
        or meta["domain"] != domain
        or meta["split"] != "development"
        or file_hash(path) != meta["rows_sha256"]
    ):
        raise ValueError("wrong or changed development dataset")
    rows, seen = [], set()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        key = row["match"], row["hero"], row["t"]
        if is_holdout(key[0]) or row["fold"] != fold_for(key[0]) or key in seen:
            raise ValueError("reserved match, duplicate case, or wrong fold")
        seen.add(key)
        if row["outcome_eligible"]:
            rows.append(row)
    if len(seen) != meta["rows"] or len(rows) != meta["eligible"]:
        raise ValueError("incorrect dataset counts")
    return rows, meta["rows_sha256"]


def train(folder, dest, domain):
    rows, source = read_dataset(folder, domain)
    arms, targets = DOMAINS[domain]
    records, folds = [], {}
    for fold in range(5):
        fit = [r for r in rows if r["fold"] != fold]
        test = [r for r in rows if r["fold"] == fold]
        model = fit_value(fit, arms, targets)
        pred = score(model, test)
        records.extend(pred)
        folds[fold] = {
            "validation": summary(pred, arms, targets),
            "training_strata": model["strata"],
        }
    if len(records) != len(rows):
        raise ValueError("incomplete out-of-fold predictions")
    model = fit_value(rows, arms, targets)
    model_path = dest / "development.joblib"
    joblib.dump(model, model_path)
    assert estimate(joblib.load(model_path), rows[:12]) == estimate(model, rows[:12])
    with (dest / "predictions.jsonl").open("x") as stream:
        for row in records:
            print(json.dumps(row, allow_nan=False), file=stream)
    write_json(
        dest / "summary.json",
        {
            "schema": "outcome-value/1",
            "domain": domain,
            "rows_sha256": source,
            "model_sha256": file_hash(model_path),
            "predictions_sha256": file_hash(dest / "predictions.jsonl"),
            "source_sha256": file_hash(Path(__file__)),
            **population_summary(records, arms, targets),
            "folds": folds,
        },
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--domain", choices=sorted(DOMAINS), default="wave")
    args = ap.parse_args()
    if args.out.exists():
        ap.error("choose a new output directory")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp, threadpool_limits(limits=1):
        dest = Path(tmp) / "value"
        dest.mkdir()
        train(args.data, dest, args.domain)
        dest.rename(args.out)


if __name__ == "__main__":
    main()
