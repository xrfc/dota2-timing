"""M2 item-timing prediction (product A). Protocol: docs/m2-design.md.

Pure functions: sample building from M1 tables, per-(hero, item, minute)
baseline and logistic models, frozen evaluation with match bootstrap.
"""

import math

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold

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
# Revision 2 (U12): enemy-only inputs, rare heroes merged, C chosen by grouped CV.
REVISION_2 = {
    "sides": ("enemies",),
    "min_count": 30,
    "c_grid": (0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0),
    "folds": 5,
}


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


def fit_vocab(train_samples, sides=("allies", "enemies"), min_count=0):
    """Training-only vocabulary; heroes seen fewer than ``min_count`` times become unknown."""
    counts = {}
    for s in train_samples:
        for side in sides:
            for h in s["inputs"][side]:
                counts[h] = counts.get(h, 0) + 1
    heroes = sorted(h for h, n in counts.items() if n >= min_count)
    return {"sides": list(sides), "heroes": heroes, "min_count": min_count}


def features(samples, vocab):
    """[one-hot per side | unknown count per side | radiant]."""
    sides = vocab.get("sides", ["allies", "enemies"])
    index = {h: i for i, h in enumerate(vocab["heroes"])}
    width = len(index)
    x = np.zeros((len(samples), len(sides) * (width + 1) + 1))
    for row, s in enumerate(samples):
        for k, side in enumerate(sides):
            for h in s["inputs"][side]:
                if h in index:
                    x[row, k * width + index[h]] = 1
                else:
                    x[row, len(sides) * width + k] += 1
        x[row, -1] = 1 if s["inputs"]["is_radiant"] else 0
    return x


def _logistic(c):
    return LogisticRegression(C=c, max_iter=1000, solver="lbfgs")


def choose_c(x, y, groups, c_grid, folds):
    """Grouped stratified CV on training rows only; lowest mean Brier wins (ties: smaller C)."""
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=SEED)
    splits = list(splitter.split(x, y, groups))
    scores = {}
    for c in c_grid:
        losses = []
        for train_idx, test_idx in splits:
            if len(set(y[train_idx])) < 2:
                losses.append(brier(y[test_idx], np.full(len(test_idx), y[train_idx].mean())))
                continue
            p = _logistic(c).fit(x[train_idx], y[train_idx]).predict_proba(x[test_idx])[:, 1]
            losses.append(brier(y[test_idx], p))
        scores[c] = float(np.mean(losses))
    best = min(c_grid, key=lambda c: (scores[c], c))
    return best, scores


def fit(train_samples, vocab, c_grid=None, folds=5):
    """Return {(spec, item, minute): model dict}; baseline-only below class floor.

    Without ``c_grid`` every model uses the fixed C (revision 1); with it, C is
    chosen per cell by ``choose_c`` on training rows only (revision 2).
    """
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
                    c = C
                    if c_grid:
                        groups = np.array([s["match_id"] for s in group])
                        c, scores = choose_c(x, y, groups, c_grid, folds)
                        entry["cv_brier"] = {str(k): v for k, v in scores.items()}
                    entry["C"] = c
                    clf = _logistic(c)
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


def timing_view(model_doc, result_rows, spec, enemies, is_radiant):
    """Per-item display rows for the pre-game page.

    A cell uses the lineup model only when the frozen display rule chose it and a
    full five-hero enemy lineup is given; otherwise the high-rank base rate.
    """
    if spec not in HERO_ITEMS:
        raise ValueError("Unsupported hero/position")
    if model_doc["vocab"].get("sides") != ["enemies"]:
        raise ValueError("Page expects the enemy-only model (revision 2)")
    shown = {(r["hero_id"], r["position"], r["item"], r["minute"]): r for r in result_rows}
    sample = {"inputs": {"allies": [], "enemies": list(enemies), "is_radiant": is_radiant}}
    x = features([sample], model_doc["vocab"])
    full_lineup = len(enemies) == 5
    items = []
    for item in HERO_ITEMS[spec]:
        cells = []
        for minute in MINUTES:
            entry = model_doc["entries"][f"{spec[0]}:{spec[1]}|{item}|{minute}"]
            row = shown.get((spec[0], spec[1], item, minute))
            use_model = (
                full_lineup
                and entry["model"] is not None
                and row is not None
                and row["display"] == "model"
            )
            cells.append(
                {
                    "minute": minute,
                    "probability": float(predict(entry, x)[0]) if use_model else entry["base_rate"],
                    "base_rate": entry["base_rate"],
                    "source": "model" if use_model else "baseline",
                    "improvement": row["brier_improvement"] if use_model else None,
                    "improvement_ci95": row["brier_improvement_ci95"] if use_model else None,
                }
            )
        shown_p = monotone([c["probability"] for c in cells])
        for cell, p in zip(cells, shown_p, strict=True):
            cell["display_probability"] = p
        typical = next((c["minute"] for c in cells if c["display_probability"] >= 0.5), None)
        first = model_doc["entries"][f"{spec[0]}:{spec[1]}|{item}|{MINUTES[0]}"]
        items.append(
            {
                "item": item,
                "cells": cells,
                "typical_minute": typical,
                "train_n": first["n"],
                "any_model": any(c["source"] == "model" for c in cells),
            }
        )
    return {"spec": list(spec), "full_lineup": full_lineup, "items": items}
