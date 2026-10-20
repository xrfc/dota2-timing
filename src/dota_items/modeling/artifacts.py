"""Strict JSON artifact validation and I/O; never imports sklearn or fits models."""

import json
import math
from pathlib import Path

from dota_items.contracts.tasks import validate_task_contract, validate_task_envelope
from dota_items.storage import digest, json_bytes

from ._validation import _mapping, _number, _sha256, _text
from .provenance import (
    IMPLEMENTATION_FILES,
    LEGACY_IMPLEMENTATION_FILES,
    PRE_TASK_IMPLEMENTATION_FILES,
    SCHEMA,
    TASK_SCHEMA,
)
from .specs import C_GRID, ITEMS, check_preprocessing, check_task


def validate_model(artifact):
    """Reject malformed JSON models with ValueError; never repair or retrain."""
    try:
        _validate_model(artifact)
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError("Malformed model artifact") from error


def _validate_model(artifact):
    _mapping(
        artifact,
        (
            "schema_version",
            "family",
            "synthetic",
            "task",
            "preprocessing",
            "models",
            "provenance",
            "parameters",
            "meaning",
        ),
        "model artifact",
    )
    if artifact["schema_version"] not in (SCHEMA, TASK_SCHEMA) or artifact["family"] not in (
        "frequency",
        "logistic",
    ):
        raise ValueError("Unsupported model artifact")
    if type(artifact["synthetic"]) is not bool:
        raise ValueError("Missing data kind marker")
    if not _text(artifact["meaning"]):
        raise ValueError("Missing prediction meaning")
    validate_task_envelope(artifact["task"], artifact["schema_version"], SCHEMA, TASK_SCHEMA)
    check_task(artifact["task"])
    check_preprocessing(artifact["preprocessing"])
    if not isinstance(artifact["models"], list) or [m["item"] for m in artifact["models"]] != ITEMS:
        raise ValueError("Model label order mismatch")
    provenance = artifact["provenance"]
    _mapping(
        provenance,
        ("source_sha256", "implementation_sha256", "code_revision", "python", "dependencies"),
        "provenance",
    )
    if any(not _sha256(provenance[key]) for key in ("source_sha256", "implementation_sha256")):
        raise ValueError("Invalid provenance hash")
    if not _text(provenance["code_revision"]) or not _text(provenance["python"]):
        raise ValueError("Missing code/dependency versions")
    _mapping(provenance["dependencies"], ("numpy", "scikit-learn"), "dependency versions")
    if any(not _text(provenance["dependencies"][p]) for p in ("numpy", "scikit-learn")):
        raise ValueError("Missing dependency version")
    # Optional paired extension: schema /1 artifacts predating this bundle still load.
    fingerprint_keys = {"implementation_files_sha256", "implementation_bundle_sha256"}
    if artifact["schema_version"] == TASK_SCHEMA and (
        not fingerprint_keys <= provenance.keys()
        or not isinstance(provenance["implementation_files_sha256"], dict)
        or set(provenance["implementation_files_sha256"]) != set(IMPLEMENTATION_FILES)
    ):
        raise ValueError("Versioned task requires complete implementation fingerprint")
    if fingerprint_keys & provenance.keys():
        if not fingerprint_keys <= provenance.keys():
            raise ValueError("Incomplete implementation fingerprint")
        files = provenance["implementation_files_sha256"]
        if (
            not isinstance(files, dict)
            or set(files)
            not in (
                set(IMPLEMENTATION_FILES),
                set(PRE_TASK_IMPLEMENTATION_FILES),
                set(LEGACY_IMPLEMENTATION_FILES),
            )
            or any(not _sha256(value) for value in files.values())
            or provenance["implementation_sha256"] != files[IMPLEMENTATION_FILES[0]]
            or provenance["implementation_bundle_sha256"] != digest(files)
        ):
            raise ValueError("Invalid implementation fingerprint")
    params = artifact["parameters"]
    expected_params = {"C", "solver", "max_iter", "random_state", "class_weight"}
    _mapping(params, expected_params, "fitting parameters")
    if (
        set(params) != expected_params
        or type(params["max_iter"]) is not int
        or params["max_iter"] != 2000
        or type(params["random_state"]) is not int
        or params["random_state"] != 0
        or params["class_weight"] is not None
    ):
        raise ValueError("Unsupported fitting parameters")
    if artifact["family"] == "logistic":
        if (
            not _number(params["C"])
            or params["C"] not in C_GRID
            or params["solver"]
            not in (
                "liblinear",
                "lbfgs",
            )
        ):
            raise ValueError("Invalid model parameters")
    elif params["C"] is not None or params["solver"] is not None:
        raise ValueError("Invalid frequency parameters")
    totals = set()
    for model in artifact["models"]:
        support = model["support"]
        _mapping(support, ("observed", "positive", "unknown"), "target support")
        if any(
            type(support[k]) is not int or support[k] < 0
            for k in ("observed", "positive", "unknown")
        ):
            raise ValueError("Invalid support")
        if support["positive"] > support["observed"]:
            raise ValueError("Invalid positive support")
        totals.add(support["observed"] + support["unknown"])
        both = 0 < support["positive"] < support["observed"]
        fields = {"item", "status", "support"}
        if model["status"] == "untrained":
            fields.add("reason")
            reason = "single_class" if support["observed"] else "no_observations"
            if both or model.get("reason") != reason:
                raise ValueError("Invalid untrained target")
        elif model["status"] == "trained":
            fields.add("frequency")
            frequency = model["frequency"]
            if not both or not _number(frequency) or not 0 < frequency < 1:
                raise ValueError("Invalid frequency")
            if not math.isclose(
                frequency, support["positive"] / support["observed"], rel_tol=1e-12, abs_tol=1e-15
            ):
                raise ValueError("Frequency/support mismatch")
            if artifact["family"] == "logistic":
                fields.update(("coefficients", "intercept"))
                coef = model["coefficients"]
                if (
                    not isinstance(coef, list)
                    or len(coef) != len(artifact["preprocessing"]["columns"])
                    or any(not _number(value) for value in coef)
                    or not _number(model["intercept"])
                ):
                    raise ValueError("Invalid coefficients")
        else:
            raise ValueError("Invalid model status")
        if set(model) != fields:
            raise ValueError("Unexpected target model fields")
    if len(totals) != 1 or not next(iter(totals)):
        raise ValueError("Inconsistent or empty training support")
    json_bytes(artifact)  # Also reject NaN in otherwise unused metadata.


def save_model(path, artifact):
    validate_model(artifact)
    payload = json_bytes({"artifact": artifact, "sha256": digest(artifact)})
    with Path(path).open("xb") as stream:
        stream.write(payload)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def load_model(path, *, expected_preprocessing=None, expected_task_contract=None):
    envelope = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_json_object,
        parse_constant=_json_constant,
    )
    _mapping(envelope, ("artifact", "sha256"), "model envelope")
    if set(envelope) != {"artifact", "sha256"} or not _sha256(envelope["sha256"]):
        raise ValueError("Invalid model envelope")
    artifact = envelope["artifact"]
    if envelope["sha256"] != digest(artifact):
        raise ValueError("Model checksum mismatch")
    validate_model(artifact)
    if expected_task_contract is not None:
        validate_task_contract(expected_task_contract)
        if artifact["task"].get("contract") != expected_task_contract:
            raise ValueError("Task compatibility mismatch; legacy scope cannot be inferred")
    if expected_preprocessing is not None and artifact["preprocessing"] != expected_preprocessing:
        raise ValueError("Feature compatibility mismatch")
    return artifact
