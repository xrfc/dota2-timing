"""Pure whole-log prediction rows and fixed-candidate comparison; no I/O or fitting."""

import math

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS
from dota_items.modeling.inference import predict_lineup
from dota_items.modeling.whole_log_diagnostics import (
    METRICS,
    SPLITS,
    difference,
    metrics,
    summarize,
)


def rows_for(model, snapshot, split):
    rows = []
    for sample in snapshot["samples"]:
        if sample["split"] != split:
            continue
        row = {k: sample[k] for k in ("match_id", "split", "source_sha256")}
        row.update(
            {
                k: dict(zip(WHOLE_LOG_ITEMS, sample[k], strict=True))
                for k in ("labels", "label_mask")
            }
        )
        row["probabilities"] = predict_lineup(
            model, sample["features"], expected_task_contract=snapshot["task"]["contract"]
        )["probabilities"]
        rows.append(row)
    return rows


def evaluate(rows):
    per_item = {}
    for item in WHOLE_LOG_ITEMS:
        known = [r for r in rows if r["label_mask"][item]]
        scored = [r for r in known if r["probabilities"][item] is not None]
        result = metrics(
            [r["labels"][item] for r in scored], [r["probabilities"][item] for r in scored]
        )
        result.update(
            unknown=len(rows) - len(known),
            known=len(known),
            known_positive=sum(r["labels"][item] for r in known),
            known_negative=sum(1 - r["labels"][item] for r in known),
            unscored_known=len(known) - len(scored),
        )
        per_item[item] = result
    macro = {}
    for key in METRICS:
        included = [i for i, m in per_item.items() if m[key] is not None]
        macro[key] = {
            "value": sum(per_item[i][key] for i in included) / len(included) if included else None,
            "included_items": included,
        }
    return {"per_item": per_item, "macro": macro}


def compare(snapshot, models, *, candidates, rules):
    """All four models, both splits; do not choose a winner or discard null metrics."""
    if set(models) != {"frequency", "logistic", *candidates}:
        raise ValueError("Four fixed candidates required")
    scores, diagnostics, coefficients = {}, {}, {}
    for name, model in models.items():
        scores[name], diagnostics[name] = {}, {}
        coefficients[name] = {
            e["item"]: {
                "status": e["status"],
                "l2_norm": math.sqrt(sum(v * v for v in e["coefficients"]))
                if "coefficients" in e
                else None,
                "intercept": e.get("intercept"),
            }
            for e in model["models"]
        }
        for split in SPLITS:
            rows = rows_for(model, snapshot, split)
            scores[name][split] = evaluate(rows)
            diagnostics[name][split] = {}
            for item in WHOLE_LOG_ITEMS:
                scored = [
                    r
                    for r in rows
                    if r["label_mask"][item] and r["probabilities"][item] is not None
                ]
                diagnostics[name][split][item] = summarize(
                    [r["labels"][item] for r in scored],
                    [r["probabilities"][item] for r in scored],
                )
    deltas = {}
    for name in candidates:
        deltas[name] = {}
        for reference in ("frequency", "logistic"):
            deltas[name][reference] = {}
            for split in SPLITS:
                a, b = scores[reference][split], scores[name][split]
                if any(
                    a["macro"][k]["included_items"] != b["macro"][k]["included_items"]
                    for k in METRICS
                ):
                    raise ValueError("Unequal defined metric supports")
                deltas[name][reference][split] = {
                    "macro": {
                        k: difference(a["macro"][k]["value"], b["macro"][k]["value"])
                        for k in METRICS
                    },
                    "per_item": {
                        i: {
                            k: difference(a["per_item"][i][k], b["per_item"][i][k]) for k in METRICS
                        }
                        for i in WHOLE_LOG_ITEMS
                    },
                }
    return {
        "metrics": scores,
        "diagnostics": diagnostics,
        "coefficients": coefficients,
        "candidate_minus_reference": deltas,
        "rules": rules,
        "selected_model": None,
    }
