"""Train-only baselines; validation selection; paired player-group uncertainty."""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

C_GRID = (0.01, 0.1, 1.0, 10.0)


def metrics(y, p):
    y, p = np.asarray(y), np.asarray(p)
    pos = int(y.sum())
    n = len(y)
    return {
        "observed": n,
        "positive": pos,
        "negative": n - pos,
        "positive_rate": float(y.mean()) if n else None,
        "average_precision": float(average_precision_score(y, p)) if pos else None,
        "brier": float(brier_score_loss(y, p)) if n else None,
        "roc_auc": float(roc_auc_score(y, p)) if 0 < pos < n else None,
    }


def group_draws(groups, repeats, seed):
    """Resample entire groups, preserving repeated copies and all their rows."""
    groups = np.asarray(groups)
    unique = np.unique(groups)
    rng = np.random.default_rng(seed)
    members = [np.flatnonzero(groups == group) for group in unique]
    for _ in range(repeats):
        yield np.concatenate([members[i] for i in rng.integers(len(unique), size=len(unique))])


def paired_intervals(y, baseline, linear, groups, repeats=500, seed=20261015):
    values = {key: [] for key in ("average_precision", "brier", "roc_auc")}
    if not len(y):
        return {key: {"low": None, "high": None, "valid_replicates": 0} for key in values}
    for indices in group_draws(groups, repeats, seed):
        a, b = metrics(y[indices], baseline[indices]), metrics(y[indices], linear[indices])
        for key in values:
            if a[key] is not None and b[key] is not None:
                values[key].append(b[key] - a[key])
    return {
        key: {
            "low": float(np.quantile(v, 0.025)) if v else None,
            "high": float(np.quantile(v, 0.975)) if v else None,
            "valid_replicates": len(v),
        }
        for key, v in values.items()
    }


def run_experiment(snapshot, repeats=500):
    if repeats < 1:
        raise ValueError("At least one bootstrap replicate required")
    rows = snapshot["samples"]
    items = snapshot["task"]["candidate_items"]
    x = np.asarray([r["encoded_features"] for r in rows], dtype=float)
    y = np.asarray([r["labels"] for r in rows], dtype=float)
    mask = np.asarray([r["label_mask"] for r in rows], dtype=bool)
    split = np.asarray([r["split"] for r in rows])
    groups = np.asarray([r["group_id"] for r in rows])
    carry = np.asarray([r["role_hint"] == "estimated_carry" for r in rows])
    # Reconstruct eligibility only from train; do not use validation/test support.
    eligible = [
        item
        for j, item in enumerate(items)
        if len(np.unique(y[(split == "train") & mask[:, j], j])) == 2
    ]
    if eligible != snapshot["train_model_items"]:
        raise ValueError("Train eligibility mismatch")
    selected, predictions, evaluations = {}, {}, {}
    for item in eligible:
        j = items.index(item)
        train = (split == "train") & mask[:, j]
        val = (split == "validation") & mask[:, j]
        if not val.any():
            raise ValueError("Validation observations required")
        frequency = float(y[train, j].mean())
        trials = []
        models = []
        for c in C_GRID:
            model = LogisticRegression(C=c, solver="liblinear", max_iter=2000, random_state=0)
            model.fit(x[train], y[train, j])
            if model.n_iter_.max() >= model.max_iter:
                raise ValueError("Logistic regression did not converge")
            score = brier_score_loss(y[val, j], model.predict_proba(x[val])[:, 1])
            trials.append({"C": c, "validation_brier": float(score)})
            models.append(model)
        winner = min(range(len(trials)), key=lambda i: (trials[i]["validation_brier"], C_GRID[i]))
        model = models[winner]
        linear = model.predict_proba(x)[:, 1]
        baseline = np.full(len(rows), frequency)
        selected[item] = {
            "frequency": frequency,
            "C": C_GRID[winner],
            "trials": trials,
            "coef": model.coef_[0].tolist(),
            "intercept": float(model.intercept_[0]),
        }
        predictions[item] = [
            {"match_id": r["match_id"], "frequency": frequency, "linear": float(p)}
            for r, p in zip(rows, linear, strict=True)
        ]
        evaluations[item] = {}
        for name in ("validation", "test"):
            evaluations[item][name] = {}
            for slice_name, slice_mask in (
                ("all", np.ones(len(rows), dtype=bool)),
                ("estimated_carry", carry),
            ):
                cohort = (split == name) & slice_mask
                keep = cohort & mask[:, j]
                evaluations[item][name][slice_name] = {
                    "unknown": int((cohort & ~mask[:, j]).sum()),
                    "groups": len(np.unique(groups[keep])),
                    "frequency": metrics(y[keep, j], baseline[keep]),
                    "linear": metrics(y[keep, j], linear[keep]),
                    "paired_delta_linear_minus_frequency_ci95": paired_intervals(
                        y[keep, j], baseline[keep], linear[keep], groups[keep], repeats=repeats
                    ),
                }
    macro = {}
    for name in ("validation", "test"):
        macro[name] = {}
        for slice_name in ("all", "estimated_carry"):
            macro[name][slice_name] = {}
            for model in ("frequency", "linear"):
                macro[name][slice_name][model] = {}
                for metric in ("average_precision", "brier", "roc_auc"):
                    vals = [evaluations[i][name][slice_name][model][metric] for i in eligible]
                    macro[name][slice_name][model][metric] = {
                        "value": float(np.mean(vals)) if vals and None not in vals else None,
                        "defined_items": sum(v is not None for v in vals),
                        "required_items": len(eligible),
                    }
    return {
        "schema_version": "purchase-log-baseline/1",
        "training_executed": True,
        "task": snapshot["task"],
        "protocol": {
            "fit_split": "train",
            "selection_split": "validation",
            "selection_metric": "minimum per-item Brier; ties prefer smaller C",
            "C_grid": C_GRID,
            "class_weight": None,
            "threshold_tuning": False,
            "bootstrap": {
                "unit": "whole player group",
                "repeats": repeats,
                "seed": 20261015,
                "interval": "paired percentile 95%, conditional on fitted models",
            },
            "validation_intervals": "descriptive only; validation used for model selection",
            "test": "exploratory grouped holdout; no test tuning",
        },
        "modeled_items": eligible,
        "excluded_items": snapshot["constant_train_items"],
        "selected_models": selected,
        "evaluations": evaluations,
        "macro": macro,
        "predictions": predictions,
        "limitations": snapshot["limitations"]
        + [
            "Bootstrap does not include retraining or hyperparameter selection uncertainty.",
            "Per-item intervals lack multiplicity correction; sparse support is unstable.",
            "No optimal-build, actual-purchase completeness, or completed-item timing claim.",
        ],
    }
