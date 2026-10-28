"""Formula inference from validated artifacts; independent of training libraries."""

import math

import numpy as np

from dota_items.contracts.lineup import encode_lineup
from dota_items.contracts.tasks import validate_task_contract

from .artifacts import validate_model
from .specs import check_lineup


def predict_lineup(artifact, features, *, expected_task_contract=None):
    validate_model(artifact)
    if expected_task_contract is not None:
        validate_task_contract(expected_task_contract)
        if artifact["task"].get("contract") != expected_task_contract:
            raise ValueError("Task compatibility mismatch; legacy scope cannot be inferred")
    check_lineup(features)
    x = np.asarray(encode_lineup(features, artifact["preprocessing"]["vocabulary"]), dtype=float)
    probabilities = {}
    for model in artifact["models"]:
        p = None
        if model["status"] == "trained":
            p = model["frequency"]
            if artifact["family"] == "logistic":
                try:
                    with np.errstate(over="raise", invalid="raise"):
                        z = float(x @ np.asarray(model["coefficients"]) + model["intercept"])
                    if not math.isfinite(z):
                        raise ValueError("Prediction score must be finite")
                except (FloatingPointError, OverflowError) as error:
                    raise ValueError("Prediction score must be finite") from error
                p = float(np.exp(-np.logaddexp(0, -z)))
        probabilities[model["item"]] = p
    return {
        **(
            {"task_contract": artifact["task"]["contract"]}
            if "contract" in artifact["task"]
            else {}
        ),
        "probabilities": probabilities,
        "synthetic": artifact["synthetic"],
        "meaning": artifact["meaning"],
        "untrained_items": [m["item"] for m in artifact["models"] if m["status"] == "untrained"],
        "unknown_counts": {
            side: int(x[index])
            for side, index in (("ally", len(x) // 2 - 1), ("enemy", len(x) - 1))
        },
    }
