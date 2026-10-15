"""Offline source-log modeling snapshot, distinct from actual-purchase admission."""

from pathlib import Path

from dota_items.data.feasibility import AuditConfig, audit_paths
from dota_items.data.lineup_preflight import encode_lineup, fit_vocabulary, lineup_features
from dota_items.data.patch_time import load_patch_window
from dota_items.data.player_overlap import audit_player_overlap
from dota_items.data.purchase_observation import observe_purchases
from dota_items.storage import digest, file_hash, json_bytes, read_json


def grouped_split(groups, seed=20261014):
    ids = [mid for group in groups for mid in group]
    if len(groups) < 3 or any(not g for g in groups) or len(ids) != len(set(ids)):
        raise ValueError("Need at least three nonempty disjoint player groups")
    targets = {"train": len(ids) * 0.6, "validation": len(ids) * 0.2, "test": len(ids) * 0.2}
    splits = {name: [] for name in targets}
    ordered = sorted((sorted(g) for g in groups), key=lambda g: (-len(g), digest([seed, g])))
    for group in ordered:
        name = max(targets, key=lambda name: targets[name] - len(splits[name]))
        splits[name].extend(group)
    if any(not ids for ids in splits.values()):
        raise ValueError("Group sizes prevent three nonempty splits")
    return {name: sorted(ids) for name, ids in splits.items()}


def class_support(samples, items):
    result = {}
    for split in ("train", "validation", "test"):
        rows = [s for s in samples if s["split"] == split]
        result[split] = {}
        for index, key in enumerate(items):
            values = [s["labels"][index] for s in rows if s["label_mask"][index]]
            pos, neg = values.count(1), values.count(0)
            result[split][key] = {
                "positive": pos,
                "negative": neg,
                "unknown": len(rows) - len(values),
                "both_classes_present": bool(pos and neg),
            }
    return result


def build_snapshot(summary_path):
    summary = read_json(summary_path)
    if summary["schema_version"] != "purchase-collection-summary/1":
        raise ValueError("Wrong summary schema")
    sources = summary["sources"]
    paths = {s["match_id"]: Path(s["path"]) for s in sources}
    if len(paths) != len(sources) or len(paths) != summary["retained_candidates"]:
        raise ValueError("Duplicate or inconsistent source count")
    for source in sources:
        if file_hash(paths[source["match_id"]]) != source["sha256"]:
            raise ValueError("Source hash mismatch")
    config = AuditConfig.model_validate(summary["audit"]["config"])
    receipt = Path("knowledge/evidence/feasibility-2026-10-13/receipt.json")
    audit = audit_paths(
        list(paths.values()),
        config,
        patch_window=load_patch_window(receipt, config.requested_patch),
        expected_ids={path: mid for mid, path in paths.items()},
    )
    if json_bytes(audit) != json_bytes(summary["audit"]):
        raise ValueError("Audit summary no longer reproduces from sources")
    rows = audit["results"]
    initial = {"train": list(paths), "validation": [], "test": []}
    identity = audit_player_overlap(rows, paths, initial)
    if not identity["identity_coverage_complete"]:
        raise ValueError("Complete supplied account identity required for player-disjoint snapshot")
    groups = identity["connected_match_groups"]
    splits = grouped_split(groups)
    overlap = audit_player_overlap(rows, paths, splits)
    if not overlap["player_disjoint_verified"]:
        raise ValueError("Cross-split player overlap")
    split_for = {mid: split for split, mids in splits.items() for mid in mids}
    group_for = {mid: f"group-{i:04d}" for i, group in enumerate(sorted(groups)) for mid in group}
    features = {row["match_id"]: lineup_features(row) for row in rows}
    vocabulary = fit_vocabulary([features[mid] for mid in splits["train"]])
    samples = []
    for row in rows:
        mid = row["match_id"]
        raw = read_json(paths[mid])
        if file_hash(paths[mid]) != row["sha256"]:
            raise ValueError("Source changed during processing")
        target = next(p for p in raw["players"] if p["player_slot"] == row["target_slot"])
        observation = observe_purchases(
            target, config.candidate_items, start=config.window_start, end=config.window_end
        )
        if observation["log_status"] != "present":
            raise ValueError("Expected valid source log in retained cohort")
        samples.append(
            {
                "match_id": mid,
                "source_sha256": row["sha256"],
                "split": split_for[mid],
                "group_id": group_for[mid],
                "features": features[mid],
                "encoded_features": encode_lineup(features[mid], vocabulary),
                "labels": [i["log_presence"] for i in observation["items"]],
                "label_mask": [i["log_presence_mask"] for i in observation["items"]],
                "role_hint": row["semantic_review"]["role_evidence"]["status"],
            }
        )
    support = class_support(samples, config.candidate_items)
    modeled = [
        key for key in config.candidate_items if support["train"][key]["both_classes_present"]
    ]
    return {
        "schema_version": "purchase-log-modeling-snapshot/1",
        "task": {
            "target": "source_purchase_log_key_presence",
            "window": [config.window_start, config.window_end],
            "candidate_items": config.candidate_items,
            "negative_means": "absent_from_valid_source_log_only",
            "scope": "retained Juggernaut matches, not independently verified position-1",
            "actual_purchase_ground_truth": False,
        },
        "modeling_ready": True,
        "training_executed": False,
        "legacy_training_allowed": False,
        "summary_sha256": file_hash(summary_path),
        "patch_receipt_sha256": file_hash(receipt),
        "implementation_sha256": {
            **audit["implementation_sha256"],
            **{
                name: file_hash(Path("src/dota_items/data") / name)
                for name in (
                    "purchase_snapshot.py",
                    "purchase_observation.py",
                    "player_overlap.py",
                    "lineup_preflight.py",
                )
            },
        },
        "split_policy": {
            "method": "all-player connected components, largest-first maximum size deficit",
            "seed": 20261014,
            "ratios": [0.6, 0.2, 0.2],
            "uses_labels": False,
            "fresh_unseen_test": False,
        },
        "splits": splits,
        "player_overlap": overlap,
        "preprocessing": {
            "fit_split": "train",
            "vocabulary": vocabulary,
            "columns": [
                c
                for side in ("ally", "enemy")
                for c in [*[f"{side}_hero_{h}" for h in vocabulary], f"{side}_unknown_count"]
            ],
        },
        "samples": samples,
        "support": support,
        "train_model_items": modeled,
        "constant_train_items": [key for key in config.candidate_items if key not in modeled],
        "evaluation_plan": {
            "primary": ["per-item average_precision when positives exist", "per-item Brier score"],
            "secondary": [
                "ROC-AUC only with both classes",
                "precision/recall/F1 with validation-only threshold",
            ],
            "baseline": "train-only per-item frequency",
            "macro_items": modeled,
            "undefined_metrics": None,
            "uncertainty": "bootstrap whole player groups, not individual matches",
            "slices": ["all retained matches", "estimated_carry (not verified role)"],
            "test_policy": "no threshold or hyperparameter tuning on test",
        },
        "limitations": [
            "Labels describe this source log, not complete actual purchases or optimal builds.",
            "Given account IDs are disjoint; this is not proof of independent people.",
            "Cohort already inspected; test is an exploratory grouped holdout.",
            "Large connected groups may dominate train; report group sizes and distribution shift.",
        ],
    }


def verify_snapshot(snapshot_path, summary_path):
    saved = read_json(snapshot_path)
    fresh = build_snapshot(summary_path)
    if json_bytes(saved) != json_bytes(fresh):
        raise ValueError("Snapshot differs from offline source reconstruction")
    return fresh
