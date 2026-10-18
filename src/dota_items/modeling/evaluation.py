"""Reusable metrics and whole-group uncertainty; no fitting or split selection.

Parity with the byte-frozen historical experiment is regression-tested.
Callers supply observed labels/predictions and retain split authorization.
"""

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


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
