"""Versioned checks for a B5 action claim given decision-time historical estimates."""

import hashlib
import json
import math

VERSION = "b5-decision-score/1"
ARMS = {
    "wave": ("farm", "retreat"),
    "jungle": ("continue_jungle", "leave_camp"),
    "support": ("approach", "stay"),
}
FARM_CONDITION = "higher_farm_income_over_equal_time_including_travel_and_clear"


def metrics(domain):
    base = ("hits", "gold", "xp", "death", "dead_seconds")
    return (*base, "arrival") if domain == "support" else base


def fingerprint(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def historical_preference(domain, values):
    """U191 point-estimate Pareto rule; retain tradeoffs and unknowns."""
    a, b = ARMS[domain]
    if values is None:
        return "unsupported"
    if (
        not isinstance(values, dict)
        or set(values) != {a, b}
        or any(not isinstance(v, dict) or set(v) != set(metrics(domain)) for v in values.values())
    ):
        raise ValueError("invalid historical action or metric set")
    better = set()
    missing = False
    for metric in metrics(domain):
        x, y = values[a][metric], values[b][metric]
        for value in (x, y):
            if value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("invalid historical estimate")
            if metric in ("death", "arrival") and not 0 <= value <= 1:
                raise ValueError("invalid probability")
            if metric in ("hits", "xp", "dead_seconds") and value < 0:
                raise ValueError("negative count, experience or death duration")
            if metric == "dead_seconds" and value > 14:
                raise ValueError("death duration exceeds outcome window")
        if x is None or y is None:
            missing = True
        elif abs(x - y) > 1e-10 + 1e-12 * abs(y):
            larger_is_better = metric not in ("death", "dead_seconds")
            better.add(a if (x > y) == larger_is_better else b)
    if missing:
        return "incomplete"
    if len(better) == 1:
        return next(iter(better))
    return "tradeoff" if better else "tie"


def seal(identity, domain, values, balance_after):
    """Build a JSON snapshot from identity and predecision model evidence only."""
    match, hero, t = identity
    if type(match) is not int or match <= 0 or not isinstance(hero, str) or not hero:
        raise ValueError("invalid match or hero")
    if type(t) is not int or t < 0 or domain not in ARMS:
        raise ValueError("invalid decision second or domain")
    preference = historical_preference(domain, values)
    if balance_after is not None and (
        type(balance_after) not in (int, float)
        or not math.isfinite(balance_after)
        or balance_after < 0
    ):
        raise ValueError("invalid balance diagnostic")
    snapshot = dict(
        schema=VERSION,
        match=match,
        hero=hero,
        t=t,
        domain=domain,
        result_window=[7, 20],
        values=values,
        balance_after=balance_after,
    )
    return snapshot, preference


def judge(snapshot, proposal):
    """Classify a structured proposal against the evaluator's own sealed evidence."""
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be an object")
    kind = proposal.get("kind")
    if kind == "defer" and set(proposal) == {"kind"}:
        return "deferred"
    domain = snapshot["domain"]
    if (
        kind == "conditional"
        and proposal
        == {"kind": "conditional", "action": "rotate_to_jungle", "condition": FARM_CONDITION}
        and domain == "wave"
    ):
        return "conditional"
    if kind != "recommend" or set(proposal) != {"kind", "action"}:
        raise ValueError("invalid proposal form or unregistered condition")
    action = proposal["action"]
    if not isinstance(action, str) or not action:
        raise ValueError("proposal action must be a nonempty string")
    if action not in ARMS[domain]:
        return "action_not_estimated"
    if snapshot["values"] is None:
        return "no_joint_support"
    if snapshot["balance_after"] is None or snapshot["balance_after"] > 0.25:
        return "insufficient_balance"
    if historical_preference(domain, snapshot["values"]) != action:
        return "no_dominance"
    return "supported"
