"""Supported task and feature definitions, not research authorization."""

from dota_items.contracts.lineup import columns
from dota_items.contracts.tasks import FEATURES, TASK, WHOLE_LOG_TASK_ID, validate_task_contract
from dota_items.contracts.tasks import FeatureSpec as FeatureSpec
from dota_items.contracts.tasks import TaskSpec as TaskSpec

from ._validation import _mapping

ITEMS = list(TASK.items)
C_GRID = (0.01, 0.1, 1.0, 10.0)


def check_preprocessing(preprocessing):
    _mapping(preprocessing, ("vocabulary", "fit_split", "columns"), "preprocessing")
    vocabulary = preprocessing["vocabulary"]
    if (
        not isinstance(vocabulary, list)
        or not vocabulary
        or TASK.target_hero_id not in vocabulary
        or any(type(h) is not int or h <= 0 for h in vocabulary)
        or vocabulary != sorted(set(vocabulary))
        or preprocessing.get("fit_split") != FEATURES.fit_split
        or preprocessing["columns"] != columns(vocabulary)
    ):
        raise ValueError("Invalid vocabulary or feature columns")
    return vocabulary


def check_lineup(features):
    _mapping(features, ("ally_hero_ids", "enemy_hero_ids", "target_hero_id"), "lineup")
    sides = [features[k] for k in ("ally_hero_ids", "enemy_hero_ids")]
    if any(not isinstance(side, list) or len(side) != 5 for side in sides):
        raise ValueError("Lineup requires five heroes on each side")
    heroes = sides[0] + sides[1]
    if any(type(h) is not int or h <= 0 for h in heroes) or len(set(heroes)) != 10:
        raise ValueError("Invalid or duplicate hero IDs")
    if (
        type(features.get("target_hero_id")) is not int
        or features["target_hero_id"] != TASK.target_hero_id
    ):
        raise ValueError("Only Juggernaut (8) is supported")
    if TASK.target_hero_id not in sides[0]:
        raise ValueError("Target must belong to allied lineup")


def check_task(task):
    _mapping(task, ("window",), "task")
    if "contract" in task:
        validate_task_contract(task["contract"])
        if task["contract"]["task_id"] == WHOLE_LOG_TASK_ID:
            contract = task["contract"]
            if (
                task.get("target") != contract["labels"]["target"]
                or task["window"] is not None
                or task.get("candidate_items") != contract["labels"]["candidate_items"]
                or task.get("negative_means") != contract["labels"]["negative_means"]
                or task.get("scope") != "whole_available_source_log"
                or task.get("actual_purchase_ground_truth") is not False
            ):
                raise ValueError("Unsupported whole-log task or label order")
            return
    window = task["window"]
    if (
        task.get("target") != TASK.target
        or not isinstance(window, list)
        or any(type(value) is not int for value in window)
        or window != list(TASK.window)
        or task.get("candidate_items") != ITEMS
        or task.get("negative_means") != TASK.negative_means
        or task.get("actual_purchase_ground_truth") is not False
    ):
        raise ValueError("Unsupported task or label order")


def task_items(task):
    """Return target order only after validating the closed registry."""
    check_task(task)
    return list(task["candidate_items"])
