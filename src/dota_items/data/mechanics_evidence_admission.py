"""Consume reproducible engineering proofs without changing frozen facts or rulings.

This is a new candidate schema. Its structured conditions and unknown interactions
must survive downstream projection; legacy upgrade-only consumers cannot use it.
The caller verifies source bytes before calling and again before publication.
"""

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import PurePosixPath

from dota_items.data.mechanics_engineering_evidence import (
    SOURCE_PATHS,
    build_mechanics_engineering_evidence,
)

POLICY = "mechanics-evidence-admission/7.42-v1"
BASELINE_POLICY = "mechanics-action-assets/7.42-v1"
ENIGMA = "audit:enigma_malefice:summons:shard"
FENCE = "7.42:disruptor_kinetic_fence:aoe_damage:shard"
TARGET_IDS = frozenset(
    {
        "ebbbbe178b11c4ce1cbd",
        "0e234c07bae2d264c62c",
        "8804d4b34b90572aa12b",
        "0dba6399710fa947dc5d",
        "c4c9a19f3fd010964b01",
        "9651e7885caaf7fd1553",
        "d5e57f0f93f66dedf40f",
    }
)
LINK_IDS = frozenset(
    f"7.42:life_stealer_infest:{mechanism}:shard" for mechanism in ("slow", "healing", "lifesteal")
)
CHANNEL_IDS = frozenset({"7056861bb759c22212b6", "95b9db1c3a9654525662"})
REVIEW_IDS = TARGET_IDS | LINK_IDS | CHANNEL_IDS | {ENIGMA, FENCE}
STATE_KEYS = (
    "condition",
    "candidate_usable",
    "patch_evidence_status",
    "user_approved_for_patch",
)


def _canonical(value):
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("Expected finite JSON evidence") from error


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _references(refs):
    if not isinstance(refs, dict) or set(refs) != set(SOURCE_PATHS) | {
        "baseline_admission",
        "engineering_evidence",
    }:
        raise ValueError("Complete baseline, engineering and registered source refs required")
    for ref in refs.values():
        if (
            not isinstance(ref, dict)
            or set(ref) != {"path", "sha256"}
            or not isinstance(ref.get("path"), str)
            or not PurePosixPath(ref["path"]).is_absolute()
            or ".." in PurePosixPath(ref["path"]).parts
            or not isinstance(ref.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) is None
        ):
            raise ValueError("Explicit absolute source paths and SHA256 refs required")


def _baseline(document, exact_patch):
    if (
        exact_patch != "7.42"
        or not isinstance(document, dict)
        or document.get("schema") != "mechanics-action-admission/1"
        or document.get("policy") != BASELINE_POLICY
        or document.get("patch") != exact_patch
        or document.get("status") != "candidate"
        or any(
            document.get(key) is not False
            for key in ("patch_verified", "formal_use_allowed", "training_allowed")
        )
        or ("action_review_allowed" in document and document["action_review_allowed"] is not False)
        or not isinstance(document.get("rows"), list)
    ):
        raise ValueError("Exact closed version-one candidate admission required")
    rows = {}
    for row in document["rows"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid baseline row")
        key = row.get("review_id")
        condition = row.get("condition")
        if (
            not isinstance(key, str)
            or not key
            or key in rows
            or any(
                not isinstance(row.get(k), str) or not row[k]
                for k in ("subject", "mechanism", "basis", "patch_evidence_status")
            )
            or row.get("decision") not in ("accept", "reject")
            or any(
                type(row.get(k)) is not bool
                for k in ("candidate_usable", "user_approved_for_patch")
            )
            or not isinstance(condition, dict)
            or condition.get("context") not in ("base", "item", "scepter_upgrade", "shard_upgrade")
            or any(
                type(condition.get(k)) is not bool for k in ("requires_scepter", "requires_shard")
            )
            or "engineering_admission" in row
        ):
            raise ValueError("Missing, duplicate or incompatible baseline row identity")
        rows[key] = row
    expected = {
        "counts": dict(Counter(row["patch_evidence_status"] for row in rows.values())),
        "candidate_usable_rows": sum(row["candidate_usable"] for row in rows.values()),
        "user_approved_for_patch_rows": sum(
            row["user_approved_for_patch"] for row in rows.values()
        ),
    }
    if any(_canonical(document.get(key)) != _canonical(value) for key, value in expected.items()):
        raise ValueError("Baseline counts do not match its row inventory")
    if not REVIEW_IDS <= rows.keys():
        raise ValueError("Registered engineering facts are missing from baseline")
    for key in REVIEW_IDS:
        row = rows[key]
        usable = key in LINK_IDS or key == FENCE
        status = (
            "two_ai_overlay"
            if usable
            else "unreviewed_or_uncertain_for_patch"
            if key == ENIGMA
            else "fact_field_rebuild_unproven"
        )
        shard = key in LINK_IDS or key in (ENIGMA, FENCE)
        if (
            row["basis"] != "two_ai"
            or row["decision"] != "accept"
            or row["candidate_usable"] is not usable
            or row["patch_evidence_status"] != status
            or row["user_approved_for_patch"] is not False
            or row["condition"]["requires_shard"] is not shard
            or row["condition"]["requires_scepter"] is not False
        ):
            raise ValueError("Registered fact decision, approval or prior admission drifted")
    return rows


def _plan(proof):
    key = proof["review_id"]
    context = proof["current_candidate_state"]["condition"]["context"]
    effect = f"7.42:{proof['subject']}:{proof['mechanism']}:{context}"
    dedup = None
    if key == ENIGMA:
        expected, operation, status = (
            "condition_narrowing_proposed",
            "promote_condition",
            "engineering_condition_verified",
        )
        conditions = proof["proposed_conditions"]
        unproven = ["actual_game_execution"]
    elif key in TARGET_IDS:
        expected, operation, status = (
            "enemy_target_text_supported",
            "promote_target",
            "engineering_target_text_verified",
        )
        conditions = {"target_scope": proof["target_scope"]}
        unproven = [
            "spell_block_interaction",
            "spell_reflect_interaction",
            "debuff_immunity_interaction",
            "all_unit_targetability",
        ]
    elif key in LINK_IDS:
        expected, operation, status = (
            "linked_effect_text_supported",
            "enrich_link",
            "two_ai_overlay",
        )
        conditions = proof["verified_link"]
        unproven = ["linked_effect_level", "linked_effect_strength", "damage_source_details"]
        if proof["mechanism"] in ("healing", "lifesteal"):
            effect = "7.42:life_stealer_infest:shard:open_wounds:damage_recovery"
            dedup = effect
    elif key == FENCE:
        expected, operation, status = (
            "linked_damage_text_found_trigger_scope_unproven",
            "block_trigger_scope",
            "engineering_trigger_scope_unproven",
        )
        conditions = None
        unproven = [
            "triggered_area_scope",
            "triggered_damage_center",
            "triggered_damage_radius",
            "triggered_victim_set",
        ]
    else:
        expected, operation, status = (
            "channel_text_found_interruption_unproven",
            "retain_blocked_channel",
            "fact_field_rebuild_unproven",
        )
        conditions = None
        unproven = ["channel_interruption_behavior"]
    if proof["proof_status"] == "source_requirement_unproven":
        operation, status, conditions = (
            "block_source_requirement",
            "engineering_source_unproven",
            None,
        )
        unproven = ["source_requirement", *unproven]
    elif proof["proof_status"] != expected:
        raise ValueError("Unregistered engineering proof status")
    usable = operation in ("promote_condition", "promote_target", "enrich_link")
    return {
        "operation": operation,
        "patch_evidence_status": status,
        "candidate_usable": usable,
        "conditions": deepcopy(conditions),
        "effect_identity": effect,
        "deduplication_group": dedup,
        "unproven_capabilities": unproven,
    }


def build_evidence_admission(
    baseline_admission, engineering_evidence, documents, *, exact_patch, source_refs
):
    """Recompute all proofs, then return a distinct, constrained candidate admission.

    ``documents`` has exactly the frozen proof producer's ``SOURCE_PATHS`` keys.
    ``source_refs`` has those keys plus ``baseline_admission`` and
    ``engineering_evidence``. References bind provenance; byte verification remains
    the caller's job. No source is opened and no input is changed here.
    """
    originals = _baseline(baseline_admission, exact_patch)
    _references(source_refs)
    proof_refs = {key: source_refs[key] for key in SOURCE_PATHS} | {
        "admission": source_refs["baseline_admission"]
    }
    rebuilt = build_mechanics_engineering_evidence(
        baseline_admission, documents, exact_patch=exact_patch, source_refs=proof_refs
    )
    if _canonical(rebuilt) != _canonical(engineering_evidence):
        raise ValueError("Engineering attachment differs from recomputed proof or source binding")
    if {row["review_id"] for row in rebuilt["rows"]} != REVIEW_IDS:
        raise ValueError("Engineering proof inventory changed")
    output = deepcopy(baseline_admission)
    rows = {row["review_id"]: row for row in output["rows"]}
    changes = []
    for index, proof in enumerate(rebuilt["rows"]):
        key = proof["review_id"]
        row, original = rows[key], originals[key]
        if any(proof[name] != original[name] for name in ("subject", "mechanism")):
            raise ValueError("Engineering subject or mechanism differs from baseline")
        plan = _plan(proof)
        prior = {name: deepcopy(original[name]) for name in STATE_KEYS}
        row.update(
            candidate_usable=plan["candidate_usable"],
            patch_evidence_status=plan["patch_evidence_status"],
        )
        row["engineering_admission"] = {
            "policy": POLICY,
            "operation": plan["operation"],
            "proof_status": proof["proof_status"],
            "proof_ref": {
                "source_ref": deepcopy(source_refs["engineering_evidence"]),
                "pointer": f"/rows/{index}",
                "review_id": key,
                "row_sha256": _sha(proof),
            },
            "prior_state": prior,
            **{
                name: deepcopy(plan[name])
                for name in (
                    "conditions",
                    "effect_identity",
                    "deduplication_group",
                    "unproven_capabilities",
                )
            },
            "unknown": deepcopy(proof["unknown"]),
            "new_user_ruling": False,
            "conditions_must_be_checked_at_use": True,
        }
        changes.append(
            {
                "review_id": key,
                "operation": plan["operation"],
                "before": deepcopy(prior),
                "after": {name: deepcopy(row[name]) for name in STATE_KEYS},
            }
        )
    promoted = sum(
        not c["before"]["candidate_usable"] and c["after"]["candidate_usable"] for c in changes
    )
    demoted = sum(
        c["before"]["candidate_usable"] and not c["after"]["candidate_usable"] for c in changes
    )
    output.update(
        schema="mechanics-evidence-admission/1",
        policy=POLICY,
        baseline_policy=BASELINE_POLICY,
        baseline_source_refs=deepcopy(baseline_admission.get("source_refs", {})),
        source_refs=deepcopy(source_refs),
        source_integrity_checked_here=False,
        baseline_document_sha256=_sha(baseline_admission),
        engineering_document_sha256=_sha(engineering_evidence),
        counts=dict(Counter(row["patch_evidence_status"] for row in rows.values())),
        candidate_usable_rows=sum(row["candidate_usable"] for row in rows.values()),
        user_approved_for_patch_rows=sum(row["user_approved_for_patch"] for row in rows.values()),
        action_review_allowed=False,
        changes=changes,
        summary={
            "rows": len(rows),
            "engineering_rows": len(changes),
            "promoted_rows": promoted,
            "demoted_rows": demoted,
            "net_candidate_usable_change": promoted - demoted,
            "link_enriched_rows": sum(c["operation"] == "enrich_link" for c in changes),
            "remaining_blocked_channel_rows": sum(
                not rows[key]["candidate_usable"] for key in CHANNEL_IDS
            ),
            "unchanged_non_target_rows": len(rows) - len(REVIEW_IDS),
            "user_rulings_added": 0,
        },
        limits=[
            "Engineering admission preserves the baseline fact decision and basis.",
            "New candidate conditions do not authorize formal use, action review or training.",
            "Target classification cannot establish spell-block or spell-reflect interactions.",
            "Downstream consumers must carry conditions and unproven capabilities explicitly.",
            "Healing and lifesteal labels may describe one event; deduplication is required.",
            "Historical quotes and review notes remain baseline evidence, not new conclusions.",
        ],
    )
    return output
