"""Explicit identity joins and factual evaluation after action prediction."""

from collections import Counter, defaultdict
from collections.abc import Mapping
from numbers import Real

import numpy as np

from dota_items.contracts.action_outcomes import (
    DOMAINS,
    DecisionKey,
    validate_observed,
)
from dota_items.modeling.awareness.action_values import ActionEstimate

REFERENCE_SEED = 20261122


def _observations(observations, *, complete):
    indexed, folds = {}, {}
    for observation in observations:
        validate_observed(observation, complete=complete)
        key = observation.key
        if key in indexed:
            raise ValueError("duplicate observed identity")
        if folds.setdefault(key.match, observation.fold) != observation.fold:
            raise ValueError("inconsistent folds within a match")
        indexed[key] = observation
    return indexed


def _identity(key):
    return {"match": key.match, "hero": key.hero, "t": key.t, "domain": key.domain}


def join_observed(predictions, observations):
    """Join by (match, hero, t, domain), never by observation list position."""
    predictions = tuple(predictions)
    observed = _observations(observations, complete=True)
    keys = [p.key for p in predictions if type(p) is ActionEstimate]
    if len(keys) != len(predictions):
        raise ValueError("expected ActionEstimate predictions")
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate prediction identity")
    if set(keys) != set(observed):
        raise ValueError("prediction and observation identities differ")
    records = []
    for prediction in predictions:
        row = observed[prediction.key]
        records.append(
            {
                **_identity(row.key),
                "fold": row.fold,
                "action": row.action,
                "rank_band": row.rank_band,
                "observed": dict(row.values),
                "mean": dict(prediction.mean[row.action]),
                **prediction.to_record(),
            }
        )
    return records


def summarize_actions(records, arms, targets):
    """Frozen factual errors and paired-action summaries; no causal claim."""
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


def evaluate_factual(records, arms, targets):
    """Evaluate an identity-joined domain, retaining the original rank-band groups."""
    arms, targets = tuple(arms), tuple(targets)
    domains = [domain for domain, spec in DOMAINS.items() if spec == (arms, targets)]
    if len(domains) != 1:
        raise ValueError("unregistered evaluation actions or targets")
    if any(record.get("domain") != domains[0] for record in records):
        raise ValueError("evaluation records have a different domain")
    stats = summarize_actions(records, arms, targets)
    bands = sorted({r["rank_band"] for r in records if r["rank_band"] is not None})
    stats["by_rank"] = {
        band: summarize_actions([r for r in records if r["rank_band"] == band], arms, targets)
        for band in bands
    }
    return stats


def join_reference(predictions, observations, *, behavior=False):
    """Attach wave truth to already identity-bound reference predictions."""
    if not isinstance(predictions, Mapping) or type(behavior) is not bool:
        raise ValueError("reference predictions must be identity-keyed")
    observed = _observations(observations, complete=False)
    if set(predictions) != set(observed):
        raise ValueError("prediction and observation identities differ")
    fields = {"p_farm"} if behavior else {"hits_pred", "p_death"}
    records = []
    for key, prediction in predictions.items():
        if type(key) is not DecisionKey or key.domain != "wave":
            raise ValueError("reference predictions require wave identities")
        if not isinstance(prediction, Mapping) or set(prediction) != fields:
            raise ValueError("incorrect reference prediction fields")
        for name, value in prediction.items():
            if (
                not isinstance(value, Real)
                or isinstance(value, (bool, np.bool_))
                or not np.isfinite(value)
                or value < 0
                or (name != "hits_pred" and value > 1)
            ):
                raise ValueError("invalid reference prediction")
        row = observed[key]
        record = {
            **_identity(key),
            "fold": row.fold,
            "action": row.action,
            "recent_damage": row.recent_damage,
            **{name: float(value) for name, value in prediction.items()},
        }
        if not behavior:
            if any(row.values.get(name) is None for name in ("hits", "death")):
                raise ValueError("reference outcomes require known hits and death")
            record.update({name: row.values[name] for name in ("hits", "death")})
        records.append(record)
    return records


def summarize_reference(rows, *, behavior=False):
    """Frozen reference metrics; caller supplies observations only after the key join."""
    from sklearn.metrics import average_precision_score, log_loss

    result = {
        "cases": len(rows),
        "matches": len({r["match"] for r in rows}),
        "actions": Counter(r["action"] for r in rows),
    }
    if not rows:
        return result
    if behavior:
        y = np.array([r["action"] == "farm" for r in rows])
        p = np.array([r["p_farm"] for r in rows])
        result.update(
            log_loss=float(log_loss(y, p, labels=[False, True])),
            farm_recall=float(np.mean(p[y] >= 0.5)) if y.any() else None,
            retreat_recall=float(np.mean(p[~y] < 0.5)) if (~y).any() else None,
        )
    else:
        risk = np.array([r["p_death"] for r in rows])
        died = np.array([r["death"] for r in rows])
        bands = np.minimum((risk * 5).astype(int), 4)
        result.update(
            deaths=int(died.sum()),
            hits_mae=float(np.mean([abs(r["hits"] - r["hits_pred"]) for r in rows])),
            death_brier=float(np.mean((risk - died) ** 2)),
            death_ap=float(average_precision_score(died, risk)) if len(set(died)) == 2 else None,
            false_alerts_per_represented_match=float(
                np.sum((risk >= 0.5) & (died == 0)) / result["matches"]
            ),
            calibration=[
                {
                    "from": int(i) / 5,
                    "count": int((bands == i).sum()),
                    "predicted": float(risk[bands == i].mean()),
                    "observed": float(died[bands == i].mean()),
                }
                for i in sorted(set(bands))
            ],
        )
    return result


def compare_reference(first, second):
    """Frozen paired match errors and deterministic whole-match bootstrap."""

    def errors(rows):
        values = {
            (r["match"], r["hero"], r["t"], r["fold"], r["death"], r["hits"]): np.array(
                [abs(r["hits"] - r["hits_pred"]), (r["death"] - r["p_death"]) ** 2]
            )
            for r in rows
        }
        if len(values) != len(rows):
            raise ValueError("duplicate prediction key")
        return values

    a, b = errors(first), errors(second)
    if a.keys() != b.keys() or not a:
        raise ValueError("comparison requires identical nonempty cases")
    by_game = defaultdict(list)
    for key in sorted(a):
        by_game[key[0]].append(a[key] - b[key])
    diff = np.array([np.mean(values, axis=0) for values in by_game.values()])
    rng = np.random.default_rng(REFERENCE_SEED)
    boot = np.array(
        [diff[rng.integers(len(diff), size=len(diff))].mean(axis=0) for _ in range(2000)]
    )
    return {
        name: {
            "difference": float(diff[:, i].mean()),
            "ci95": np.quantile(boot[:, i], [0.025, 0.975]).tolist(),
        }
        for i, name in enumerate(("hits_mae", "death_brier"))
    }
