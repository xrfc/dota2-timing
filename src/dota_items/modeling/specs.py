"""Supported task and feature definitions, not research authorization."""

from dataclasses import dataclass

from dota_items.contracts.lineup import columns

from ._validation import _mapping


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
