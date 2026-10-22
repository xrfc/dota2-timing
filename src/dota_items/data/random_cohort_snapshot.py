"""Approved match-level development split; no fitting, network or output writes."""

import copy

from dota_items.contracts.tasks import task_contract
from dota_items.data.lineup_preflight import encode_lineup, fit_vocabulary
from dota_items.data.purchase_snapshot import class_support
from dota_items.storage import digest


def random_split(ids, seed=42):
    """Hash-shuffle positive unique IDs; first floor(N/5) are validation."""
    if type(seed) is not int or seed < 0:
        raise ValueError("Invalid seed")
    if len(ids) < 5 or any(type(mid) is not int or mid <= 0 for mid in ids):
        raise ValueError("Need at least five positive integer match IDs")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate match ID")
    ordered = sorted(ids, key=lambda mid: (digest([seed, mid]), mid))
    count = len(ids) // 5
    return {"train": sorted(ordered[count:]), "validation": sorted(ordered[:count]), "test": []}


def assemble_snapshot(rows, seed=42):
    """Only source-verified rows may be passed by the offline producer."""
    rows = copy.deepcopy(rows)
    splits = random_split([r["match_id"] for r in rows], seed)
    split_for = {mid: name for name, ids in splits.items() for mid in ids}
    contract = task_contract()
    items = contract["labels"]["candidate_items"]
    for row in rows:
        if row["features"]["target_hero_id"] != contract["target_hero_id"]:
            raise ValueError("Wrong target hero")
        labels, masks = row["labels"], row["label_mask"]
        if len(labels) != len(items) or len(masks) != len(items):
            raise ValueError("Wrong label dimension")
        for value, mask in zip(labels, masks, strict=True):
            if type(mask) is not bool:
                raise ValueError("Nonboolean mask")
            if mask and (type(value) is not int or value not in (0, 1)):
                raise ValueError("Invalid observed label")
            if not mask and value is not None:
                raise ValueError("Unknown must remain null")
        row["split"] = split_for[row["match_id"]]
    vocabulary = fit_vocabulary([r["features"] for r in rows if r["split"] == "train"])
    for row in rows:
        row["encoded_features"] = encode_lineup(row["features"], vocabulary)
    rows.sort(key=lambda row: row["match_id"])
    support = class_support(rows, items)
    modeled = [item for item in items if support["train"][item]["both_classes_present"]]
    return {
        "schema_version": "purchase-log-modeling-snapshot/2",
        "cohort_id": "purchase-cohort-random-v2/1",
        "task": {
            "target": "source_purchase_log_key_presence",
            "window": [0, 1800],
            "candidate_items": items,
            "negative_means": "absent_from_valid_source_log_only",
            "scope": "Juggernaut, requested position-1 not independently verified",
            "actual_purchase_ground_truth": False,
            "contract": contract,
        },
        "modeling_ready": True,
        "training_executed": False,
        "legacy_training_allowed": False,
        "split_policy": {
            "method": "SHA256(json_bytes([seed,match_id])) ascending, ID tie-break",
            "seed": seed,
            "validation_count": "floor(N/5); first hashes",
            "ratios": [0.8, 0.2, 0.0],
            "uses_labels": False,
            "player_overlap_allowed": True,
            "fresh_unseen_test": False,
            "authorization": "user 2026-10-21 10:21 Asia/Shanghai",
        },
        "splits": splits,
        "membership_sha256": digest(splits),
        "preprocessing": {
            "fit_split": "train",
            "vocabulary": vocabulary,
            "columns": [
                c
                for side in ("ally", "enemy")
                for c in [*[f"{side}_hero_{h}" for h in vocabulary], f"{side}_unknown_count"]
            ],
        },
        "samples": rows,
        "support": support,
        "train_model_items": modeled,
        "constant_train_items": [item for item in items if item not in modeled],
        "limitations": [
            "Development validation includes previously inspected historical holdouts.",
            "Players may overlap; no unseen-player or future-match generalization claim.",
            "Source-log presence is not complete purchase truth or optimal item choice.",
            "Both-class support is mechanical fit eligibility, not sufficient statistical power.",
            "No training or model evaluation was executed or authorized by this artifact.",
        ],
    }
