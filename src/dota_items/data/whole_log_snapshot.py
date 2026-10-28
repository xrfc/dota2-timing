"""Frozen random-v2 relabeling; no splitting, vocabulary fitting or training."""

import copy
import json
import math
from pathlib import Path

from dota_items.contracts.lineup import encode_lineup, fit_vocabulary
from dota_items.contracts.tasks import WHOLE_LOG_ITEMS, WHOLE_LOG_TASK_ID, task_contract
from dota_items.data.lineup_preflight import lineup_features
from dota_items.data.purchase_observation import observe_purchases
from dota_items.data.purchase_snapshot import class_support
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import digest, file_hash, json_bytes

BUNDLE_FILES = {
    "snapshot.json",
    "sources.json",
    "report.json",
    "source-audit.json",
    "split.json",
    "protection.json",
}
FROZEN_MEMBERSHIP = "5810a1a97ce12d3c07bad99ede29c8b4d107ea430e2e145291e480ac50c77dd8"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key in whole-log input")
        result[key] = value
    return result


def load(path):
    contents = read_source_bytes(path)
    # Preserve the public source parser and additionally reject ambiguous keys.
    value = parse_source_json(contents)
    json.loads(contents, object_pairs_hook=_unique_object)
    return value


def whole_log_task():
    contract = task_contract(WHOLE_LOG_TASK_ID)
    return {
        "target": contract["labels"]["target"],
        "window": None,
        "candidate_items": list(WHOLE_LOG_ITEMS),
        "negative_means": contract["labels"]["negative_means"],
        "scope": "whole_available_source_log",
        "actual_purchase_ground_truth": False,
        "contract": contract,
    }


def observe_whole_log(player):
    """All finite event times, including pregame; bad logs stay fully unknown."""
    log = player.get("purchase_log")
    valid = isinstance(log, list) and all(
        isinstance(e, dict)
        and isinstance(e.get("key"), str)
        and bool(e["key"])
        and type(e.get("time")) in (int, float)
        and math.isfinite(e["time"])
        for e in log
    )
    return {
        "scope": "whole_available_source_log",
        "log_status": "present" if valid else ("invalid" if isinstance(log, list) else "missing"),
        "labels": [
            int(any(e["key"] == key for e in log)) if valid else None for key in WHOLE_LOG_ITEMS
        ],
        "label_mask": [valid] * len(WHOLE_LOG_ITEMS),
        "event_refs": {
            key: [i for i, e in enumerate(log) if e["key"] == key] for key in WHOLE_LOG_ITEMS
        }
        if valid
        else {},
        "coverage_verified": False,
    }


def relabel_snapshot(frozen, sources, payloads):
    """Pure replay API, also usable for synthetic fixtures; production adds frozen gates."""
    if frozen.get("cohort_id") != "purchase-cohort-random-v2/1":
        raise ValueError("Expected random-v2 cohort")
    if json_bytes(frozen["task"].get("contract")) != json_bytes(task_contract()):
        raise ValueError("Expected original five-item task")
    rows = frozen["samples"]
    ids = [r["match_id"] for r in rows]
    source_ids = [s["match_id"] for s in sources]
    members = [mid for ids_ in frozen["splits"].values() for mid in ids_]
    if (
        any(type(mid) is not int or mid <= 0 for mid in ids + source_ids + members)
        or len(set(ids)) != len(ids)
        or len(set(source_ids)) != len(source_ids)
        or len(set(members)) != len(members)
        or set(ids) != set(source_ids)
        or set(ids) != set(members)
        or set(payloads) != set(ids)
    ):
        raise ValueError("Duplicate, conflicting or mismatched membership")
    if digest(frozen["splits"]) != frozen["membership_sha256"]:
        raise ValueError("Membership hash mismatch")
    split_for = {mid: name for name, mids in frozen["splits"].items() for mid in mids}
    if any(row["split"] != split_for[row["match_id"]] for row in rows):
        raise ValueError("Sample split mismatch")
    vocabulary = frozen["preprocessing"]["vocabulary"]
    if fit_vocabulary([r["features"] for r in rows if r["split"] == "train"]) != vocabulary:
        raise ValueError("Vocabulary is not train-only")
    if any(
        json_bytes(encode_lineup(r["features"], vocabulary)) != json_bytes(r["encoded_features"])
        for r in rows
    ):
        raise ValueError("Encoded features mismatch")
    source_for = {s["match_id"]: s for s in sources}
    result = copy.deepcopy(frozen)
    for row in result["samples"]:
        mid = row["match_id"]
        raw = payloads[mid]
        if type(raw.get("match_id")) is not int or raw["match_id"] != mid:
            raise ValueError("Payload identity mismatch")
        if row["source_sha256"] != source_for[mid]["sha256"]:
            raise ValueError("Source identity mismatch")
        players = raw.get("players")
        if (
            not isinstance(players, list)
            or len(players) != 10
            or any(not isinstance(p, dict) for p in players)
        ):
            raise ValueError("Invalid source lineup")
        slots = [p.get("player_slot") for p in players]
        if (
            any(type(s) is not int for s in slots)
            or set(slots) != {0, 1, 2, 3, 4, 128, 129, 130, 131, 132}
            or any(type(p.get("hero_id")) is not int or p["hero_id"] <= 0 for p in players)
            or len({p["hero_id"] for p in players}) != 10
        ):
            raise ValueError("Invalid source players")
        targets = [p for p in players if p["hero_id"] == 8]
        if len(targets) != 1:
            raise ValueError("Expected unique Juggernaut")
        target = targets[0]
        features = lineup_features({"target_slot": target["player_slot"], "lineup": players})
        if json_bytes(features) != json_bytes(row["features"]):
            raise ValueError("Source lineup mismatch")
        old = observe_purchases(target, task_contract()["labels"]["candidate_items"])
        if (
            old["log_status"] != "present"
            or json_bytes([i["log_presence"] for i in old["items"]]) != json_bytes(row["labels"])
            or json_bytes([i["log_presence_mask"] for i in old["items"]])
            != json_bytes(row["label_mask"])
        ):
            raise ValueError("Old five-label replay mismatch or invalid log")
        observation = observe_whole_log(target)
        if observation["log_status"] != "present":
            raise ValueError("Missing or invalid source log")
        row["labels"] = observation["labels"]
        row["label_mask"] = observation["label_mask"]
        row["whole_log_observation"] = observation
    result["cohort_id"] = "purchase-cohort-whole-log-11/1"
    result["task"] = whole_log_task()
    result["support"] = class_support(result["samples"], WHOLE_LOG_ITEMS)
    result["train_model_items"] = [
        k for k in WHOLE_LOG_ITEMS if result["support"]["train"][k]["both_classes_present"]
    ]
    result["constant_train_items"] = [
        k for k in WHOLE_LOG_ITEMS if k not in result["train_model_items"]
    ]
    result["training_executed"] = False
    result["limitations"] = frozen.get("limitations", []) + [
        "Inherited minimum-duration cohort; whole-log scope does not remove selection bias.",
        "All available valid source events, not final inventory or complete actual purchases.",
    ]
    # Old producer fingerprints describe the parent only, never this new producer.
    result.pop("task_implementation_sha256", None)
    result["provenance"] = {
        "parent_snapshot_digest": digest(frozen),
        "old_five_label_replay": "all_samples_equal",
    }
    return result


def build_whole_log_bundle(parent):
    """Verify the immutable parent receipt, then replay every hashed local source."""
    parent = Path(parent)
    receipt = load(parent / "complete.json")
    if (
        receipt.get("schema_version") != "random-cohort-complete/1"
        or set(receipt.get("sha256", {})) != BUNDLE_FILES
    ):
        raise ValueError("Invalid parent completion receipt")
    hashes = {str(parent / name): sha for name, sha in receipt["sha256"].items()}
    hashes[str(parent / "complete.json")] = file_hash(parent / "complete.json")
    for path, sha in hashes.items():
        if file_hash(Path(path)) != sha:
            raise ValueError("Parent bundle hash mismatch")
    frozen, sources = load(parent / "snapshot.json"), load(parent / "sources.json")
    if (
        len(frozen["samples"]) != 1990
        or {k: len(v) for k, v in frozen["splits"].items()}
        != {"train": 1592, "validation": 398, "test": 0}
        or frozen["membership_sha256"] != FROZEN_MEMBERSHIP
    ):
        raise ValueError("Not the approved frozen 1990-candidate membership")
    split = load(parent / "split.json")
    if json_bytes(split) != json_bytes(
        {"policy": frozen["split_policy"], "members": frozen["splits"], "sha256": FROZEN_MEMBERSHIP}
    ):
        raise ValueError("Parent split manifest mismatch")
    payloads = {}
    for source in sources:
        mid, path = source["match_id"], Path(source["path"])
        if mid in payloads:
            raise ValueError("Duplicate source candidate")
        if file_hash(path) != source["sha256"]:
            raise ValueError("Original source hash mismatch")
        payloads[mid] = load(path)
        hashes[str(path)] = source["sha256"]
    result = relabel_snapshot(frozen, sources, payloads)
    result["provenance"]["parent_bundle_sha256"] = receipt["sha256"]
    implementation = [
        Path("src/dota_items/data/whole_log_snapshot.py"),
        Path("src/dota_items/contracts/tasks.py"),
        Path("scripts/prepare_whole_log_cohort.py"),
    ]
    result["provenance"]["implementation_sha256"] = {str(p): file_hash(p) for p in implementation}
    for path, sha in hashes.items():
        if file_hash(Path(path)) != sha:
            raise ValueError("Input changed during replay")
    return result, sources, hashes
