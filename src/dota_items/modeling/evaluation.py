"""Reusable metrics and whole-group uncertainty; no fitting or split selection.

Parity with the byte-frozen historical experiment is regression-tested.
Callers supply observed labels/predictions and retain split authorization.
"""

from numbers import Integral, Real

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def _vector(value, name, *, binary=False):
    """Reject coercion of missing, textual or boolean observations into numbers."""
    if np.ma.isMaskedArray(value):
        raise ValueError("Filter unknown observations explicitly; masked arrays are not accepted")
    try:
        raw = np.asarray(value, dtype=object)
        if raw.ndim != 1 or any(
            isinstance(v, (bool, np.bool_)) or not isinstance(v, Real) for v in raw
        ):
            raise ValueError(f"{name} must be a one-dimensional numeric vector")
        result = np.asarray(value, dtype=float)
    except (TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if not np.isfinite(result).all() or not ((result >= 0) & (result <= 1)).all():
        raise ValueError(f"{name} must contain finite values in [0, 1]")
    if binary and not np.isin(result, [0, 1]).all():
        raise ValueError("Labels must be observed binary values; filter unknowns first")
    return result


def _options(repeats, seed):
    for value, name, minimum in ((repeats, "repeats", 1), (seed, "seed", 0)):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
            raise ValueError(f"{name} must be an integer")
        if value < minimum:
            raise ValueError(f"{name} must be >= {minimum}")


def _groups(groups):
    if np.ma.isMaskedArray(groups):
        raise ValueError("Masked group identities are not accepted")
    raw = np.asarray(groups, dtype=object)
    if raw.ndim != 1:
        raise ValueError("Groups must be a one-dimensional vector")
    if not len(raw):
        return np.asarray([], dtype=int)
    integers = all(isinstance(v, Integral) and not isinstance(v, (bool, np.bool_)) for v in raw)
    strings = all(isinstance(v, str) and bool(v.strip()) for v in raw)
    if not (integers or strings):
        raise ValueError("Group IDs must be all integers or all nonempty strings")
    # Object integers avoid overflowing or rounding large group identifiers.
    return raw if integers else np.asarray(groups, dtype=str)


def metrics(y, p):
    y, p = _vector(y, "labels", binary=True), _vector(p, "probabilities")
    if len(y) != len(p):
        raise ValueError("Labels and probabilities must have equal lengths")
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
    _options(repeats, seed)
    groups = _groups(groups)
    if not len(groups):
        return
    unique = np.unique(groups)
    rng = np.random.default_rng(seed)
    members = [np.flatnonzero(groups == group) for group in unique]
    for _ in range(repeats):
        yield np.concatenate([members[i] for i in rng.integers(len(unique), size=len(unique))])


def paired_intervals(y, baseline, linear, groups, repeats=500, seed=20261015):
    _options(repeats, seed)
    y = _vector(y, "labels", binary=True)
    baseline, linear = _vector(baseline, "baseline"), _vector(linear, "linear")
    groups = _groups(groups)
    if not (len(y) == len(baseline) == len(linear) == len(groups)):
        raise ValueError("Labels, predictions and groups must have equal lengths")
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
