"""Descriptive train/validation diagnostics of a frozen baseline; never fit or tune."""

from collections import Counter

import numpy as np

from dota_items.modeling.purchase_baseline import metrics


def calibration(y, p):
    """Fixed deciles, including empty bins and probability 1 in the last bin."""
    y, p = np.asarray(y), np.asarray(p)
    bins = np.minimum((p * 10).astype(int), 9)
    return [
        {
            "lower": i / 10,
            "upper": (i + 1) / 10,
            "count": int((bins == i).sum()),
            "mean_probability": float(p[bins == i].mean()) if (bins == i).any() else None,
            "positive_rate": float(y[bins == i].mean()) if (bins == i).any() else None,
        }
        for i in range(10)
    ]


def diagnose(snapshot, experiment):
    # Filter first: test features, labels and predictions never enter diagnostics.
    rows = [r for r in snapshot["samples"] if r["split"] in ("train", "validation")]
    ids = [r["match_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate snapshot match IDs")
    split = np.asarray([r["split"] for r in rows])
    train, val = split == "train", split == "validation"
    if not train.any() or not val.any():
        raise ValueError("Both train and validation required")
    x = np.asarray([r["encoded_features"] for r in rows], dtype=float)
    columns = snapshot["preprocessing"]["columns"]
    if x.shape[1] != len(columns):
        raise ValueError("Feature column mismatch")
    groups = np.asarray([r["group_id"] for r in rows])
    largest = sorted(Counter(groups[train]).items(), key=lambda pair: (-pair[1], pair[0]))[0][0]
    cohorts = {
        "train": train,
        "train_largest_group": train & (groups == largest),
        "train_other_groups": train & (groups != largest),
        "validation": val,
    }
    drift = [
        {
            "feature": name,
            "train_rate": float(x[train, j].mean()),
            "validation_rate": float(x[val, j].mean()),
            "delta_validation_minus_train": float(x[val, j].mean() - x[train, j].mean()),
        }
        for j, name in enumerate(columns)
    ]
    items = {}
    for item in experiment["modeled_items"]:
        j = snapshot["task"]["candidate_items"].index(item)
        known = np.asarray([r["label_mask"][j] for r in rows], dtype=bool)
        y = np.asarray([r["labels"][j] if r["label_mask"][j] else np.nan for r in rows])
        if not np.isin(y[known], [0, 1]).all():
            raise ValueError("Observed labels must be binary")
        predictions = [p for p in experiment["predictions"][item] if p["match_id"] in set(ids)]
        by_id = {p["match_id"]: p for p in predictions}
        if len(by_id) != len(predictions) or set(by_id) != set(ids):
            raise ValueError("Prediction match IDs missing or duplicated")
        p = np.asarray([by_id[i]["linear"] for i in ids])
        freq = np.asarray([by_id[i]["frequency"] for i in ids])
        model = experiment["selected_models"][item]
        z = x @ np.asarray(model["coef"]) + model["intercept"]
        expected = np.exp(-np.logaddexp(0, -z))
        if not np.isfinite(p).all() or not np.allclose(p, expected, rtol=0, atol=1e-12):
            raise ValueError("Saved predictions disagree with frozen model")
        if not np.allclose(freq, y[train & known].mean(), rtol=0, atol=1e-12):
            raise ValueError("Frequency disagrees with training labels")
        support = {}
        for name, cohort in cohorts.items():
            keep = cohort & known
            support[name] = {
                "rows": int(cohort.sum()),
                "groups": len(set(groups[cohort])),
                "unknown": int((cohort & ~known).sum()),
                "positive": int(y[keep].sum()),
                "observed": int(keep.sum()),
                "positive_rate": float(y[keep].mean()) if keep.any() else None,
            }
        keep = val & known
        delta = (p[keep] - y[keep]) ** 2 - (freq[keep] - y[keep]) ** 2
        errors = [
            {
                "match_id": rows[index]["match_id"],
                "label": int(y[index]),
                "linear_probability": float(p[index]),
                "frequency_probability": float(freq[index]),
                "brier_delta": float(d),
            }
            for index, d in zip(np.flatnonzero(keep), delta, strict=True)
        ]
        items[item] = {
            "support": support,
            "validation": {
                "frequency": metrics(y[keep], freq[keep]),
                "linear": metrics(y[keep], p[keep]),
                "mean_probability_minus_rate": float((p[keep] - y[keep]).mean())
                if keep.any()
                else None,
                "brier_delta": float(delta.mean()) if keep.any() else None,
                "calibration": calibration(y[keep], p[keep]),
                "largest_harms": sorted(errors, key=lambda r: -r["brier_delta"])[:10],
                "largest_improvements": sorted(errors, key=lambda r: r["brier_delta"])[:10],
            },
        }
    return {
        "schema_version": "purchase-log-diagnostics/1",
        "protocol": {
            "splits": ["train", "validation"],
            "training_executed": False,
            "test_used": False,
            "calibration_bins": "fixed deciles; last bin includes 1",
            "interpretation": "Descriptive only; validation already used for C selection.",
        },
        "feature_shift": sorted(drift, key=lambda r: -abs(r["delta_validation_minus_train"])),
        "items": items,
        "limitations": [
            "Frequency shifts do not identify causes or prove population drift.",
            "Largest-group comparisons are descriptive, not independent experiments.",
            "No calibration fitting, threshold tuning, resplitting or test analysis.",
        ],
    }
