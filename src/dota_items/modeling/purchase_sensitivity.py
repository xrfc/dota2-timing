"""Proposed train/validation-only intercept sensitivity experiment; no test evaluation."""

import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from dota_items.modeling.purchase_baseline import C_GRID, metrics


def compare(snapshot):
    # Filter before accessing any feature, label, or mask: test payloads are opaque.
    rows = [r for r in snapshot["samples"] if r["split"] in ("train", "validation")]
    if not rows:
        raise ValueError("Training and validation observations required")
    x = np.asarray([r["encoded_features"] for r in rows], dtype=float)
    y = np.asarray([r["labels"] for r in rows], dtype=float)
    mask = np.asarray([r["label_mask"] for r in rows], dtype=bool)
    split = np.asarray([r["split"] for r in rows])
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite features")
    items = snapshot["task"]["candidate_items"]
    output, skipped = {}, []
    for j, item in enumerate(items):
        train = (split == "train") & mask[:, j]
        val = (split == "validation") & mask[:, j]
        if not np.isin(y[mask[:, j], j], [0, 1]).all():
            raise ValueError("Observed labels must be binary")
        if len(np.unique(y[train, j])) != 2:
            skipped.append(item)
            continue
        if not val.any():
            raise ValueError("Validation observations required")
        frequency = float(y[train, j].mean())
        trials = []

        def record(name, c, model, frequency=frequency, trials=trials, j=j, train=train, val=val):
            probabilities = (
                np.full(len(rows), frequency) if model is None else model.predict_proba(x)[:, 1]
            )
            trials.append(
                {
                    "name": name,
                    "C": c,
                    "intercept": None if model is None else float(model.intercept_[0]),
                    "coefficients": None if model is None else model.coef_[0].tolist(),
                    "iterations": None if model is None else int(model.n_iter_.max()),
                    "metrics": {
                        name: {
                            **metrics(y[keep, j], probabilities[keep]),
                            "mean_prediction": float(probabilities[keep].mean()),
                            "mean_prediction_minus_observed": float(
                                (probabilities[keep] - y[keep, j]).mean()
                            ),
                        }
                        for name, keep in [("train", train), ("validation", val)]
                    },
                    "validation_predictions": [
                        {"match_id": rows[i]["match_id"], "probability": float(probabilities[i])}
                        for i in np.flatnonzero(val)
                    ],
                }
            )

        record("frequency", None, None)
        for solver in ("liblinear", "lbfgs"):
            for c in C_GRID:
                model = LogisticRegression(C=c, solver=solver, max_iter=2000, random_state=0)
                with warnings.catch_warnings():
                    warnings.simplefilter("error", ConvergenceWarning)
                    model.fit(x[train], y[train, j])
                if model.n_iter_.max() >= model.max_iter:
                    raise ValueError("Logistic regression did not converge")
                record(solver, c, model)
        # Stable candidate order: frequency first, then original solver, smaller C first.
        winner = min(range(len(trials)), key=lambda i: trials[i]["metrics"]["validation"]["brier"])
        output[item] = {"frequency": frequency, "selected_index": winner, "trials": trials}
    return {
        "schema_version": "purchase-log-sensitivity/1",
        "training_executed": True,
        "test_evaluated": False,
        "protocol": {
            "C_grid": list(C_GRID),
            "selection": "Per-item minimum validation Brier; exact ties follow candidate order",
            "candidate_order": ["frequency", "liblinear ascending C", "lbfgs ascending C"],
            "class_weight": None,
            "feature_scaling": False,
            "threshold_tuning": False,
            "intercept": "liblinear penalizes synthetic intercept; lbfgs does not",
        },
        "items": output,
        "excluded_train_single_class_items": skipped,
        "limitations": [
            "Validation reused for selection and diagnosis; not independent performance evidence.",
            "Solver changes as well as intercept penalty: not a pure causal ablation.",
            "No new data, test evaluation, calibration fitting, or optimal-build claim.",
        ],
    }
