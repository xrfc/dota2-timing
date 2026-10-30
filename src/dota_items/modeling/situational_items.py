"""M2b first situational item (针对装) for Juggernaut. Protocol: docs/m2b-design.md.

6-way choice among Juggernauts who bought any situational item, from enemy role
and capability-signal counts (hero registry). Pure functions; JSON-safe models.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold

HERO = (8, 1)
CLASSES = ("monkey_king_bar", "skadi", "basher", "sange_and_yasha", "nullifier", "diffusal")
ITEM_CLASS = {
    "monkey_king_bar": "monkey_king_bar",
    "skadi": "skadi",
    "basher": "basher",
    "sange_and_yasha": "sange_and_yasha",
    "nullifier": "nullifier",
    "diffusal_blade": "diffusal",
    "disperser": "diffusal",
}
C_GRID = (0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0)
FOLDS = 5
SEED = 0
BOOTSTRAP = 1000
MIN_IMPROVEMENT = 0.01  # log loss; pre-registered minimum effect size


def build_samples(players, purchases):
    """Juggernaut pos1 (not collapsed) with any situational item; label = first one.

    Ties at the same second keep purchase_log order. Only enemy hero ids and side
    are kept as inputs.
    """
    targets = {
        (r["match_id"], r["player_slot"]): r
        for r in players
        if (r["hero_id"], r["position"]) == HERO and not r["collapsed_carry"]
    }
    first = {}
    for order, p in enumerate(purchases):
        key = (p["match_id"], p["player_slot"])
        if key in targets and p["item"] in ITEM_CLASS:
            best = first.get(key)
            if best is None or (p["time_s"], order) < best[:2]:
                first[key] = (p["time_s"], order, ITEM_CLASS[p["item"]])
    by_match = {}
    for r in players:
        by_match.setdefault(r["match_id"], []).append(r)
    samples = []
    for key, row in targets.items():
        if key not in first:
            continue
        enemies = sorted(
            r["hero_id"] for r in by_match[row["match_id"]] if r["is_radiant"] != row["is_radiant"]
        )
        samples.append(
            {
                "match_id": row["match_id"],
                "enemies": enemies,
                "label": first[key][2],
                "first_time_s": first[key][0],
            }
        )
    return sorted(samples, key=lambda s: s["match_id"])


def feature_spec(registry_heroes):
    """Feature names come from the registry, never from training labels."""
    roles = sorted({r for h in registry_heroes for r in h.get("published_role_labels") or []})
    dims = sorted(
        {s["dimension"] for h in registry_heroes for s in h.get("capability_review_signals") or []}
    )
    hero_tags = {
        h["hero_id"]: {
            "roles": sorted(set(h.get("published_role_labels") or [])),
            "dims": sorted({s["dimension"] for s in h.get("capability_review_signals") or []}),
        }
        for h in registry_heroes
    }
    names = [f"role:{r}" for r in roles] + [f"mech:{d}" for d in dims] + ["unknown_heroes"]
    return {"roles": roles, "dims": dims, "names": names, "hero_tags": hero_tags}


def features(samples, spec):
    role_i = {r: i for i, r in enumerate(spec["roles"])}
    dim_i = {d: len(role_i) + i for i, d in enumerate(spec["dims"])}
    x = np.zeros((len(samples), len(spec["names"])))
    for row, s in enumerate(samples):
        for hero in s["enemies"]:
            tags = spec["hero_tags"].get(hero)
            if tags is None:
                x[row, -1] += 1
                continue
            for r in tags["roles"]:
                x[row, role_i[r]] += 1
            for d in tags["dims"]:
                x[row, dim_i[d]] += 1
    return x


def labels(samples):
    index = {c: i for i, c in enumerate(CLASSES)}
    return np.array([index[s["label"]] for s in samples])


def log_loss(y, p):
    p = np.clip(p, 1e-15, 1)
    return float(-np.mean(np.log(p[np.arange(len(y)), y])))


def brier(y, p):
    onehot = np.eye(len(CLASSES))[y]
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def _standardize(x, mean, std):
    return (x - mean) / std


def _fit_one(x, y, c):
    return LogisticRegression(C=c, max_iter=5000, solver="lbfgs").fit(x, y)


def _proba(clf, x):
    """Probabilities over all CLASSES even if a fold lacks some class."""
    out = np.full((len(x), len(CLASSES)), 1e-9)
    out[:, clf.classes_] = clf.predict_proba(x)
    return out / out.sum(axis=1, keepdims=True)


def fit(train, spec):
    x_raw, y = features(train, spec), labels(train)
    mean = x_raw.mean(axis=0)
    std = x_raw.std(axis=0)
    std[std == 0] = 1.0
    x = _standardize(x_raw, mean, std)
    groups = np.array([s["match_id"] for s in train])
    splits = list(
        StratifiedGroupKFold(n_splits=FOLDS, shuffle=True, random_state=SEED).split(x, y, groups)
    )
    cv = {}
    for c in C_GRID:
        losses = []
        for tr, te in splits:
            # Fold-local standardization keeps the held-out fold unseen.
            m, s = x_raw[tr].mean(axis=0), x_raw[tr].std(axis=0)
            s[s == 0] = 1.0
            clf = _fit_one(_standardize(x_raw[tr], m, s), y[tr], c)
            losses.append(log_loss(y[te], _proba(clf, _standardize(x_raw[te], m, s))))
        cv[c] = float(np.mean(losses))
    best = min(C_GRID, key=lambda c: (cv[c], c))
    clf = _fit_one(x, y, best)
    if clf.n_iter_.max() >= clf.max_iter:
        raise ValueError("Not converged")
    coef = np.zeros((len(CLASSES), x.shape[1]))
    intercept = np.full(len(CLASSES), -30.0)
    coef[clf.classes_] = clf.coef_
    intercept[clf.classes_] = clf.intercept_
    return {
        "classes": list(CLASSES),
        "feature_names": spec["names"],
        "mean": mean.tolist(),
        "std": std.tolist(),
        "coef": coef.tolist(),
        "intercept": intercept.tolist(),
        "C": best,
        "cv_log_loss": {str(k): v for k, v in cv.items()},
        "priors": [float(np.mean(y == i)) for i in range(len(CLASSES))],
        "train_n": len(y),
        "train_class_counts": [int(np.sum(y == i)) for i in range(len(CLASSES))],
    }


def predict(model, x_raw):
    x = _standardize(x_raw, np.array(model["mean"]), np.array(model["std"]))
    z = x @ np.array(model["coef"]).T + np.array(model["intercept"])
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def evaluate(model, valid, spec):
    """Frozen protocol: log loss vs priors, match bootstrap, CI and minimum effect."""
    x, y = features(valid, spec), labels(valid)
    p_model = predict(model, x)
    p_base = np.tile(np.array(model["priors"]), (len(y), 1))
    rng = np.random.default_rng(SEED)
    deltas = []
    for _ in range(BOOTSTRAP):
        pick = rng.integers(0, len(y), len(y))
        deltas.append(log_loss(y[pick], p_base[pick]) - log_loss(y[pick], p_model[pick]))
    lo, hi = (float(v) for v in np.percentile(deltas, [2.5, 97.5]))
    improvement = log_loss(y, p_base) - log_loss(y, p_model)
    passed = lo > 0 and improvement >= MIN_IMPROVEMENT
    confusion = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    for t, pr in zip(y, p_model.argmax(axis=1), strict=True):
        confusion[t, pr] += 1
    return {
        "valid_n": len(y),
        "valid_class_counts": [int(np.sum(y == i)) for i in range(len(CLASSES))],
        "log_loss_baseline": log_loss(y, p_base),
        "log_loss_model": log_loss(y, p_model),
        "log_loss_improvement": improvement,
        "log_loss_improvement_ci95": [lo, hi],
        "brier_baseline": brier(y, p_base),
        "brier_model": brier(y, p_model),
        "top1_baseline": float(np.mean(y == int(np.argmax(model["priors"])))),
        "top1_model": float(np.mean(p_model.argmax(axis=1) == y)),
        "calibration_mean_p_vs_rate": [
            {"class": c, "mean_p": float(p_model[:, i].mean()), "rate": float(np.mean(y == i))}
            for i, c in enumerate(CLASSES)
        ],
        "confusion_true_by_pred": confusion.tolist(),
        "min_improvement": MIN_IMPROVEMENT,
        "passed": passed,
        "display": "model" if passed else "baseline",
    }


def top_coefficients(model, k=5):
    """Largest standardized coefficients per class (interpretation only)."""
    names = model["feature_names"]
    out = {}
    for c, row in zip(model["classes"], model["coef"], strict=True):
        order = np.argsort(row)
        out[c] = {
            "more_likely": [(names[i], round(row[i], 3)) for i in order[::-1][:k]],
            "less_likely": [(names[i], round(row[i], 3)) for i in order[:k]],
        }
    return out
