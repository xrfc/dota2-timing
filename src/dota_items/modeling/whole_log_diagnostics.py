"""Descriptive frozen predictions only; no training, selection or causal inference."""

import numpy as np

from dota_items.modeling.evaluation import metrics
from dota_items.modeling.purchase_diagnostics import calibration

FAMILIES = ("frequency", "logistic")
SPLITS = ("train", "validation")
METRICS = ("brier", "average_precision", "roc_auc")


def summarize(y, p):
    """Population (ddof=0) moments; bins are not an exact Brier decomposition."""
    result = metrics(y, p)  # Strict observed-vector validation before conversion.
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    n = len(y)
    bins = calibration(y, p)
    bias = float(p.mean() - y.mean()) if n else None
    variance = float(p.var()) if n else None
    covariance = float(np.mean((p - p.mean()) * (y - y.mean()))) if n else None
    label_variance = float(y.var()) if n else None
    result.update(
        {
            "mean_probability": float(p.mean()) if n else None,
            "bias_p_minus_y": bias,
            "probability_std_ddof0": float(p.std()) if n else None,
            "probability_quantiles": {
                str(q): float(np.quantile(p, q)) if n else None
                for q in (0, 0.05, 0.25, 0.5, 0.75, 0.95, 1)
            },
            "calibration_bins": bins,
            "ece10": sum(
                b["count"] * abs(b["mean_probability"] - b["positive_rate"])
                for b in bins
                if b["count"]
            )
            / n
            if n
            else None,
            "bin_approximate_calibration_squared_error": sum(
                b["count"] * (b["mean_probability"] - b["positive_rate"]) ** 2
                for b in bins
                if b["count"]
            )
            / n
            if n
            else None,
            "exact_brier_decomposition": {
                "variance_p": variance,
                "bias_squared": bias**2 if n else None,
                "covariance_p_y": covariance,
                "variance_y": label_variance,
                "reconstructed_brier": variance + bias**2 - 2 * covariance + label_variance
                if n
                else None,
                "ddof": 0,
            },
        }
    )
    return result


def difference(a, b):
    """b minus a, preserving undefined values."""
    return None if a is None or b is None else b - a


def contributions(ids, y, frequency, logistic):
    """Stable descending positive squared-error deltas; ties retain snapshot order."""
    a, b = summarize(y, frequency), summarize(y, logistic)
    if len(ids) != len(y):
        raise ValueError("Contribution IDs misaligned")
    y, f, p = map(lambda v: np.asarray(v, dtype=float), (y, frequency, logistic))
    if len(f) and not np.all(f == f[0]):
        raise ValueError("Frequency baseline must be constant")
    delta = (p - y) ** 2 - (f - y) ** 2
    total, positive, negative = (
        float(delta.sum()),
        float(delta[delta > 0].sum()),
        float(delta[delta < 0].sum()),
    )
    rows = [
        {
            "match_id": mid,
            "label": int(label),
            "frequency_probability": float(fp),
            "logistic_probability": float(lp),
            "squared_error_delta": float(d),
            "share_of_total_delta": float(d) / total if total else None,
            "share_of_positive_delta": float(d) / positive if positive else None,
        }
        for mid, label, fp, lp, d in zip(ids, y, f, p, delta, strict=True)
        if d > 0
    ]
    top = sorted(rows, key=lambda r: -r["squared_error_delta"])[:10]
    top_sum = sum(r["squared_error_delta"] for r in top)
    terms = b["exact_brier_decomposition"]
    incremental = (
        None
        if not len(y)
        else (
            terms["variance_p"]
            - 2 * terms["covariance_p_y"]
            + terms["bias_squared"]
            - a["exact_brier_decomposition"]["bias_squared"]
        )
    )
    return {
        "observed": len(y),
        "total_delta_sum": total,
        "mean_delta": float(delta.mean()) if len(y) else None,
        "exact_increment_vs_constant_frequency": incremental,
        "positive": {"count": len(rows), "sum": positive},
        "negative": {
            "count": int((delta < 0).sum()),
            "sum": negative,
            "mean": float(delta[delta < 0].mean()) if (delta < 0).any() else None,
            "minimum": float(delta.min()) if (delta < 0).any() else None,
        },
        "zero_count": int((delta == 0).sum()),
        "top10_positive": top,
        "top10_sum": top_sum,
        "top10_share_of_total_delta": top_sum / total if total else None,
        "top10_share_of_positive_delta": top_sum / positive if positive else None,
        "share_note": "Signed net-total shares may exceed 1 or be negative; no causal meaning.",
    }


def diagnose(predictions, items):
    """Caller verifies snapshot/model binding; enforce paired row alignment here too."""
    if set(predictions) != set(FAMILIES):
        raise ValueError("Unexpected families")
    results = {family: {} for family in FAMILIES}
    for family in FAMILIES:
        if set(predictions[family]) != set(SPLITS):
            raise ValueError("Only frozen train/validation allowed")
        seen = set()
        for split in SPLITS:
            rows = predictions[family][split]
            ids = [r["match_id"] for r in rows]
            if len(set(ids)) != len(ids) or seen.intersection(ids):
                raise ValueError("Duplicate prediction IDs")
            seen.update(ids)
            for row in rows:
                if row["split"] != split or any(
                    set(row[k]) != set(items) for k in ("labels", "label_mask", "probabilities")
                ):
                    raise ValueError("Prediction schema mismatch")
                for item in items:
                    mask, label = row["label_mask"][item], row["labels"][item]
                    if type(mask) is not bool or (not mask and label is not None):
                        raise ValueError("Invalid unknown mask")
            results[family][split] = {}
            for item in items:
                known = [r for r in rows if r["label_mask"][item]]
                if any(r["probabilities"][item] is None for r in known):
                    raise ValueError("Frozen diagnostic requires scored observed labels")
                summary = summarize(
                    [r["labels"][item] for r in known], [r["probabilities"][item] for r in known]
                )
                summary["unknown"] = len(rows) - len(known)
                results[family][split][item] = summary
    paired = {}
    for split in SPLITS:
        f, p = (predictions[family][split] for family in FAMILIES)
        if len(f) != len(p) or any(
            {k: a[k] for k in a if k != "probabilities"}
            != {k: b[k] for k in b if k != "probabilities"}
            for a, b in zip(f, p, strict=True)
        ):
            raise ValueError("Misaligned paired predictions")
        paired[split] = {}
        for item in items:
            pairs = [(a, b) for a, b in zip(f, p, strict=True) if a["label_mask"][item]]
            value = contributions(
                [a["match_id"] for a, _ in pairs],
                [a["labels"][item] for a, _ in pairs],
                [a["probabilities"][item] for a, _ in pairs],
                [b["probabilities"][item] for _, b in pairs],
            )
            if split == "train":
                value.pop("top10_positive")  # Per-match publication restricted to validation.
            paired[split][item] = value
    gaps = {
        family: {
            item: {
                key: difference(
                    results[family]["train"][item][key], results[family]["validation"][item][key]
                )
                for key in (*METRICS, "positive_rate", "mean_probability", "bias_p_minus_y")
            }
            for item in items
        }
        for family in FAMILIES
    }
    return {
        "schema_version": "whole-log-frozen-diagnostics/1",
        "metrics_and_calibration": results,
        "logistic_minus_frequency": paired,
        "validation_minus_train": gaps,
        "limitations": [
            "Frozen train/validation only; reused validation is not independent generalization.",
            "ECE10 and bin squared error are bin-sensitive, not an exact Brier decomposition.",
            "Exact moment decomposition uses population ddof=0; descriptive, not causal.",
            "No fit, calibration fitting, tuning, new splits, significance or group isolation.",
            "Unknown labels excluded; match IDs confined to ignored diagnostic artifacts.",
        ],
        "training_executed": False,
        "calibrator_fitted": False,
    }
