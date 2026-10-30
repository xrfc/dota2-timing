"""M2 item-timing prediction (product A). Protocol: docs/m2-design.md.

Pure functions: sample building from M1 tables, per-(hero, item, minute)
baseline and logistic models, frozen evaluation with match bootstrap.
"""

import math

import numpy as np
from sklearn.linear_model import LogisticRegression

# U9/U10/U11. (hero_id, position) -> key items.
HERO_ITEMS = {
    (8, 1): (
        "magic_wand",
        "power_treads",
        "bfury",
        "yasha",
        "manta",
        "butterfly",
        "blink",
        "ultimate_scepter",
    ),
    (30, 5): (
        "magic_wand",
        "arcane_boots",
        "blink",
        "glimmer_cape",
        "aghanims_shard",
        "ultimate_scepter",
    ),
    (87, 5): ("magic_wand", "arcane_boots", "blink", "glimmer_cape", "ultimate_scepter"),
    (111, 5): (
        "magic_wand",
        "arcane_boots",
        "blink",
        "glimmer_cape",
        "ghost",
        "cyclone",
        "aether_lens",
    ),
}
MINUTES = (10, 15, 20, 25, 30)
MIN_CLASS_COUNT = 10
C = 1.0
BOOTSTRAP = 1000
SEED = 0


def build_samples(players, purchases):
    """One sample per target player: pre-game lineup inputs plus first-purchase times.

    ``players`` are M1 rows (with position/collapsed_carry); collapsed carries
    are excluded (U8). Only hero ids and side enter ``inputs``.
    """
    by_match = {}
    for row in players:
        by_match.setdefault(row["match_id"], []).append(row)
    first = {}
    for p in purchases:
        key = (p["match_id"], p["player_slot"])
        first.setdefault(key, {}).setdefault(p["item"], p["time_s"])
    samples = []
    for match_id, rows in by_match.items():
        for row in rows:
            spec = (row["hero_id"], row["position"])
            if spec not in HERO_ITEMS or row["collapsed_carry"]:
                continue
            allies = sorted(
                r["hero_id"] for r in rows if r["is_radiant"] == row["is_radiant"] and r is not row
            )
            enemies = sorted(r["hero_id"] for r in rows if r["is_radiant"] != row["is_radiant"])
            samples.append(
                {
                    "match_id": match_id,
                    "spec": spec,
                    "inputs": {
                        "allies": allies,
                        "enemies": enemies,
                        "is_radiant": row["is_radiant"],
                    },
                    "first_purchase_s": first.get((match_id, row["player_slot"]), {}),
                }
            )
    return samples


def label(sample, item, minute):
    t = sample["first_purchase_s"].get(item)
    return int(t is not None and t < minute * 60)


def fit_vocab(train_samples):
    heroes = sorted(
        {h for s in train_samples for side in ("allies", "enemies") for h in s["inputs"][side]}
    )
    return {"heroes": heroes}


def features(samples, vocab):
    """[ally one-hot | enemy one-hot | ally unknown | enemy unknown | radiant]."""
    index = {h: i for i, h in enumerate(vocab["heroes"])}
    width = len(index)
    x = np.zeros((len(samples), 2 * width + 3))
    for row, s in enumerate(samples):
        for side, offset, unknown in (("allies", 0, 2 * width), ("enemies", width, 2 * width + 1)):
            for h in s["inputs"][side]:
                if h in index:
                    x[row, offset + index[h]] = 1
                else:
                    x[row, unknown] += 1
        x[row, -1] = 1 if s["inputs"]["is_radiant"] else 0
    return x


def fit(train_samples, vocab):
    """Return {(spec, item, minute): model dict}; baseline-only below class floor."""
    models = {}
    for spec, items in HERO_ITEMS.items():
        group = [s for s in train_samples if s["spec"] == spec]
        if not group:
            continue
        x = features(group, vocab)
        for item in items:
            for minute in MINUTES:
                y = np.array([label(s, item, minute) for s in group])
                positives = int(y.sum())
                entry = {
                    "n": len(y),
                    "positives": positives,
                    "base_rate": positives / len(y),
                    "model": None,
                }
                if min(positives, len(y) - positives) >= MIN_CLASS_COUNT:
                    clf = LogisticRegression(C=C, max_iter=1000, solver="lbfgs")
                    clf.fit(x, y)
                    if clf.n_iter_[0] >= clf.max_iter:
                        raise ValueError(f"Not converged: {spec} {item} {minute}")
                    entry["model"] = {
                        "intercept": float(clf.intercept_[0]),
                        "coef": [float(v) for v in clf.coef_[0]],
                    }
                models[(spec, item, minute)] = entry
    return models


def predict(entry, x):
    if entry["model"] is None:
        return np.full(len(x), entry["base_rate"])
    z = x @ np.array(entry["model"]["coef"]) + entry["model"]["intercept"]
    return 1 / (1 + np.exp(-z))


def brier(y, p):
    return float(np.mean((p - y) ** 2))


def log_loss(y, p):
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (p >= lo) & ((p < hi) | (hi == 1))
        if mask.any():
            rows.append(
                {
                    "bin": [round(lo, 2), round(hi, 2)],
                    "n": int(mask.sum()),
                    "mean_p": float(p[mask].mean()),
                    "observed": float(y[mask].mean()),
                }
            )
    return rows


def evaluate(models, valid_samples, vocab):
    """Frozen protocol: Brier/log loss vs baseline with match-bootstrap 95% CI."""
    rng = np.random.default_rng(SEED)
    results = []
    for (spec, item, minute), entry in sorted(models.items()):
        group = [s for s in valid_samples if s["spec"] == spec]
        if not group:
            continue
        x = features(group, vocab)
        y = np.array([label(s, item, minute) for s in group], dtype=float)
        base = np.full(len(y), entry["base_rate"])
        model = predict(entry, x)
        matches = np.array([s["match_id"] for s in group])
        unique = np.unique(matches)
        rows_of = {m: np.flatnonzero(matches == m) for m in unique}
        deltas = []
        for _ in range(BOOTSTRAP):
            pick = np.concatenate([rows_of[m] for m in rng.choice(unique, len(unique))])
            deltas.append(brier(y[pick], base[pick]) - brier(y[pick], model[pick]))
        lo, hi = (float(v) for v in np.percentile(deltas, [2.5, 97.5]))
        modeled = entry["model"] is not None
        results.append(
            {
                "hero_id": spec[0],
                "position": spec[1],
                "item": item,
                "minute": minute,
                "train_n": entry["n"],
                "train_positives": entry["positives"],
                "valid_n": len(y),
                "valid_positive_rate": float(y.mean()),
                "modeled": modeled,
                "brier_baseline": brier(y, base),
                "brier_model": brier(y, model),
                "log_loss_baseline": log_loss(y, base),
                "log_loss_model": log_loss(y, model),
                "brier_improvement": brier(y, base) - brier(y, model),
                "brier_improvement_ci95": [lo, hi],
                "display": "model" if modeled and lo > 0 else "baseline",
                "calibration_model": calibration(y, model),
            }
        )
    return results


def monotone(probabilities):
    """Cumulative max so P(done by N) never decreases with N (display only)."""
    out, best = [], -math.inf
    for p in probabilities:
        best = max(best, p)
        out.append(best)
    return out
