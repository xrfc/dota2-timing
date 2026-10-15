"""Reproducible pre-training rehearsal, deliberately not an admitted training dataset."""

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field

from dota_items.data.contracts import StrictContract
from dota_items.data.feasibility import audit_paths
from dota_items.data.feasibility_sampling import verify_plan
from dota_items.data.patch_time import load_patch_window
from dota_items.data.player_overlap import audit_player_overlap
from dota_items.storage import digest, file_hash, json_bytes, read_json


def verify_preflight(report_path, plan_path, discovery, cache, patch_receipt):
    """Replay from explicit local sources; verification is never training admission.

    Compare canonical bytes, not Python equality (True == 1). Source and code
    changes invalidate an old report; neither report fields nor hashes authorize it.
    """
    saved = read_json(report_path)
    if not isinstance(saved, dict) or saved.get("schema_version") != "lineup-preflight/2":
        raise ValueError("Unsupported preflight schema")
    if not isinstance(saved.get("config"), dict):
        raise ValueError("Missing preflight config")
    config = PreflightConfig.model_validate(saved["config"])
    rebuilt = build_preflight(plan_path, discovery, cache, patch_receipt, config)
    if json_bytes(saved) != json_bytes(rebuilt):
        raise ValueError("Preflight differs from offline replay; sources or implementation changed")
    return {
        "schema_version": "lineup-preflight-verification/1",
        "status": "reproduced",
        "report_sha256": file_hash(report_path),
        "training_allowed": False,
        "summary": rebuilt["summary"],
        "limitations": [
            "Reproduction is not independent evidence or training admission.",
            "Config is replayed from the report, not certified as externally frozen.",
        ],
    }


class PreflightConfig(StrictContract):
    schema_version: Literal["lineup-preflight-config/1"] = "lineup-preflight-config/1"
    seed: int = Field(default=20261014, ge=0)
    validation_fraction: float = Field(default=0.2, gt=0, lt=0.5)
    test_fraction: float = Field(default=0.2, gt=0, lt=0.5)


def split_matches(ids, config):
    if len(ids) != len(set(ids)) or any(type(mid) is not int or mid <= 0 for mid in ids):
        raise ValueError("Expected distinct positive match IDs before splitting")
    if len(ids) < 3:
        return None
    ordered = sorted(ids, key=lambda mid: (digest([config.seed, mid]), mid))
    nv = max(1, int(len(ids) * config.validation_fraction))
    nt = max(1, int(len(ids) * config.test_fraction))
    return {"validation": ordered[:nv], "test": ordered[nv : nv + nt], "train": ordered[nv + nt :]}


def lineup_features(row):
    """Whitelist only hero identities; never copy scope_hints or role estimates."""
    slot = row["target_slot"]
    return {
        "target_hero_id": next(p["hero_id"] for p in row["lineup"] if p["player_slot"] == slot),
        "ally_hero_ids": sorted(
            p["hero_id"] for p in row["lineup"] if (p["player_slot"] < 128) == (slot < 128)
        ),
        "enemy_hero_ids": sorted(
            p["hero_id"] for p in row["lineup"] if (p["player_slot"] < 128) != (slot < 128)
        ),
    }


def fit_vocabulary(rows):
    return sorted(
        {hero for row in rows for key in ("ally_hero_ids", "enemy_hero_ids") for hero in row[key]}
    )


def encode_lineup(features, vocabulary):
    result = []
    for key in ("ally_hero_ids", "enemy_hero_ids"):
        heroes = set(features[key])
        result.extend(int(hero in heroes) for hero in vocabulary)
        result.append(len(heroes - set(vocabulary)))
    return result


def summarize_purchase_support(audit_rows, selected_rows, splits, candidate_items):
    """Count source observations, never infer negatives or independent class support.

    Match counts are binary per candidate. Repeated rows and same-second events
    remain diagnostic; deduplicating timestamps does not certify unique purchases.
    The all-inspectable denominator intentionally retains scope/censoring failures.
    """

    def summarize(rows):
        items = []
        for key in candidate_items:
            observations = [
                next(c for c in row["candidates"] if c["item_key"] == key) for row in rows
            ]
            observed = sum(bool(c["event_times"]) for c in observations)
            items.append(
                {
                    "item_key": key,
                    "observed_matches": observed,
                    "no_observation_matches": len(rows) - observed,
                    "source_event_rows": sum(len(c["event_times"]) for c in observations),
                    "distinct_match_time_pairs": sum(
                        len(set(c["event_times"])) for c in observations
                    ),
                    "admitted_positive_labels": 0,
                    "admitted_negative_labels": 0,
                }
            )
        return {"match_count": len(rows), "items": items}

    by_id = {r["match_id"]: r for r in selected_rows}
    return {
        "schema_version": "purchase-observation-support/1",
        "training_allowed": False,
        "all_inspectable": summarize([r for r in audit_rows if r["status"] == "inspectable"]),
        "preview": summarize(selected_rows),
        "by_split": {
            split: summarize([by_id[mid] for mid in ids]) for split, ids in (splits or {}).items()
        },
        "split_status": "rehearsal_only" if splits else "not_available",
        "limitations": [
            "No observation is unknown, not a negative label; even an empty log is unverified.",
            "All-inspectable includes excluded scope, short, missing-log and invalid-event rows.",
            "Counts describe source keys, not verified item mappings or completed equipment.",
            "Source rows may include duplicates or initial-inventory synthetic purchase events.",
            "Match counts are not independent player counts or proof of sample-size adequacy.",
        ],
    }


def build_preflight(
    plan_path: Path,
    discovery: Path,
    cache: Path,
    patch_receipt: Path,
    config: PreflightConfig | None = None,
):
    config = PreflightConfig.model_validate(config or PreflightConfig())
    plan, plan_hash = verify_plan(plan_path, discovery)
    window = load_patch_window(patch_receipt, plan.audit_config.requested_patch)
    paths = [cache / f"{mid}.json" for mid in plan.match_ids]
    report = audit_paths(
        paths,
        plan.audit_config,
        patch_window=window,
        expected_ids=dict(zip(paths, plan.match_ids, strict=True)),
    )
    selected, exclusions = [], []
    for row in report["results"]:
        reasons = []
        if row["status"] != "inspectable":
            reasons.append("audit_" + row["status"])
        else:
            if row.get("patch_time_check") != "time_consistent":
                reasons.append("patch_time_not_consistent")
            if not row["window_complete_in_duration"]:
                reasons.append("right_censored")
            if row["purchase_log_status"] != "present":
                reasons.append("purchase_log_not_present")
            if row["invalid_purchase_rows"]:
                reasons.append("invalid_purchase_events")
            if row["synthetic_marker_present"]:
                reasons.append("synthetic_marker")
        if reasons:
            exclusions.append({"requested_match_id": row["requested_match_id"], "reasons": reasons})
        else:
            selected.append(row)
    splits = split_matches([r["match_id"] for r in selected], config)
    overlap = audit_player_overlap(
        selected, {mid: cache / f"{mid}.json" for mid in plan.match_ids}, splits
    )
    split_for = {mid: split for split, mids in (splits or {}).items() for mid in mids}
    features = {r["match_id"]: lineup_features(r) for r in selected}
    vocabulary = fit_vocabulary([features[mid] for mid in (splits or {}).get("train", [])])
    samples = [
        {
            "sample_id": f"{row['match_id']}:{row['target_slot']}:pregame",
            "match_id": row["match_id"],
            "target_slot": row["target_slot"],
            "source_sha256": row["sha256"],
            "split": split_for.get(row["match_id"]),
            "features": features[row["match_id"]],
            "encoded_features": encode_lineup(features[row["match_id"]], vocabulary)
            if splits
            else None,
            "observations": row["candidates"],
            "labels": [None] * len(plan.audit_config.candidate_items),
            "label_mask": [False] * len(plan.audit_config.candidate_items),
            "training_allowed": False,
            "blockers": sorted(
                set(
                    row["reasons"]
                    + ["label_contract_not_admitted", "hero_catalog_version_unverified"]
                )
            ),
        }
        for row in selected
    ]
    blockers = [
        "label_contract_not_admitted",
        "independent_scope_evidence_missing",
        "event_completion_and_coverage_unverified",
        "cohort_is_exploratory_not_independent_evaluation",
    ]
    if not splits:
        blockers.append("insufficient_matches_for_three_splits")
        blockers.append("player_overlap_not_audited")
    else:
        if overlap["status"] == "overlap_detected":
            blockers.append("cross_split_player_overlap")
        if not overlap["identity_coverage_complete"]:
            blockers.append("player_identity_coverage_incomplete")
    return {
        "schema_version": "lineup-preflight/2",
        "training_allowed": False,
        "intended_task": "pregame_lineup_to_equipment (definition pending semantic admission)",
        "config": config.model_dump(mode="json"),
        "audit_config": plan.audit_config.model_dump(mode="json"),
        "input_identity": {
            "plan_sha256": plan_hash,
            "discovery_sha256": plan.discovery_sha256,
            "patch_receipt_sha256": file_hash(patch_receipt),
        },
        "implementation_sha256": {
            **report["implementation_sha256"],
            "data/lineup_preflight.py": file_hash(Path(__file__)),
            "data/player_overlap.py": file_hash(Path(__file__).with_name("player_overlap.py")),
        },
        "split_method": "sha256(seed,match_id), ordered then fixed counts; rehearsal only",
        "splits": splits,
        "player_overlap": overlap,
        "purchase_support": summarize_purchase_support(
            report["results"], selected, splits, plan.audit_config.candidate_items
        ),
        "preprocessing": {
            "fit_split": "train",
            "hero_vocabulary": vocabulary,
            "columns": [
                col
                for side in ("ally", "enemy")
                for col in [*(f"{side}_{hero}" for hero in vocabulary), f"{side}_unknown_count"]
            ],
            "role_estimates_in_features": False,
        },
        "summary": {
            "attempted_matches": len(report["results"]),
            "preview_samples": len(samples),
            "excluded_matches": len(exclusions),
            "training_admitted_matches": 0,
            "split_counts": {key: len(ids) for key, ids in (splits or {}).items()},
            "blocker_counts": dict(Counter(x for row in samples for x in row["blockers"])),
        },
        "blockers": blockers,
        "samples": samples,
        "exclusions": exclusions,
        "audit": report,
        "limitations": [
            "Preview split is not an independent evaluation or a sample-size guarantee.",
            "Observed purchases are not completed items or valid negative labels.",
            "Do not pass this schema to legacy training; all supervision is masked.",
        ],
    }
