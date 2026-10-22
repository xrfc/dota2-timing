"""Closed, versioned research task registry. Registration is not training permission."""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskSpec:
    target: str = "source_purchase_log_key_presence"
    target_hero_id: int = 8
    items: tuple[str, ...] = ("bfury", "maelstrom", "manta", "black_king_bar", "skadi")
    window: tuple[int, int] = (0, 1800)
    negative_means: str = "absent_from_valid_source_log_only"


@dataclass(frozen=True)
class FeatureSpec:
    encoding: str = "lineup-multihot/1"
    fit_split: str = "train"
    unknown: str = "per-side-count"


TASK = TaskSpec()
FEATURES = FeatureSpec()
TASK_ID = "juggernaut-source-log-7.41f-30m/1"


WHOLE_LOG_TASK_ID = "juggernaut-source-log-7.41f-whole-11/1"
WHOLE_LOG_ITEMS = (
    "bfury",
    "maelstrom",
    "mjollnir",
    "manta",
    "sange_and_yasha",
    "butterfly",
    "blink",
    "ultimate_scepter",
    "monkey_king_bar",
    "diffusal_blade",
    "skadi",
)


def task_contract(task_id=TASK_ID):
    """Return an independent JSON value from the closed task registry."""
    if type(task_id) is str and task_id == WHOLE_LOG_TASK_ID:
        contract = task_contract()
        contract["task_id"] = WHOLE_LOG_TASK_ID
        contract["window"] = None
        contract["labels"]["candidate_items"] = list(WHOLE_LOG_ITEMS)
        contract["labels"]["scope"] = "whole_available_source_log"
        contract["labels"]["time_policy"] = "all_finite_times_including_negative"
        contract["labels"]["complete_actual_purchases_verified"] = False
        return contract
    if type(task_id) is not str or task_id != TASK_ID:
        raise ValueError("Unregistered task ID")
    return {
        "schema_version": "dota-task-contract/1",
        "task_id": TASK_ID,
        "target_hero_id": TASK.target_hero_id,
        "role": {"requested_position": 1, "evidence": "not_independently_verified"},
        "patch_scope": {
            "patches": ["7.41f"],
            "basis": "official_release_time_inference",
            "client_version_verified": False,
        },
        "window": {"start_seconds": 0, "end_seconds": 1800, "interval": "[start,end)"},
        "labels": {
            "target": TASK.target,
            "candidate_items": list(TASK.items),
            "negative_means": TASK.negative_means,
            "unknown": "null_with_false_mask",
            "actual_purchase_ground_truth": False,
        },
        "features": {
            "encoding": FEATURES.encoding,
            "fit_split": FEATURES.fit_split,
            "unknown": FEATURES.unknown,
            "input": "pregame_lineup_hero_ids_only",
        },
    }


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Task contract must be finite JSON") from error


def validate_task_contract(value):
    """Reject unknown versions, fields, type coercion and altered registered scope."""
    if not isinstance(value, dict):
        raise ValueError("Task contract must be an object")
    expected = task_contract(value.get("task_id"))
    if _canonical(value) != _canonical(expected):
        raise ValueError("Task contract differs from registered specification")


def validate_task_envelope(task, schema, legacy_schema, versioned_schema):
    if schema not in (legacy_schema, versioned_schema):
        raise ValueError("Unsupported task container schema")
    if not isinstance(task, dict):
        raise ValueError("Task must be an object")
    if schema == versioned_schema:
        validate_task_contract(task.get("contract"))
    elif "contract" in task:
        raise ValueError("Versioned task requires versioned container schema")
