"""Engineering candidates retain scope, unknown interactions and prior approvals."""

import hashlib
import json
from collections import Counter
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import pytest

from dota_items.data.mechanics_engineering_evidence import (
    SOURCE_PATHS,
    build_mechanics_engineering_evidence,
)
from dota_items.data.mechanics_evidence_admission import (
    ENIGMA,
    FENCE,
    REVIEW_IDS,
    TARGET_IDS,
    build_evidence_admission,
)
from dota_items.data.source_io import read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
FACTS = (
    (ENIGMA, "enigma_malefice", "summons", "shard_upgrade"),
    ("7.42:life_stealer_infest:slow:shard", "life_stealer_infest", "slow", "shard_upgrade"),
    ("7.42:life_stealer_infest:healing:shard", "life_stealer_infest", "healing", "shard_upgrade"),
    (
        "7.42:life_stealer_infest:lifesteal:shard",
        "life_stealer_infest",
        "lifesteal",
        "shard_upgrade",
    ),
    (FENCE, "disruptor_kinetic_fence", "aoe_damage", "shard_upgrade"),
    ("ebbbbe178b11c4ce1cbd", "clinkz_death_pact", "unit_target_spell", "base"),
    ("0e234c07bae2d264c62c", "doom_bringer_devour", "unit_target_spell", "base"),
    ("8804d4b34b90572aa12b", "life_stealer_infest", "unit_target_spell", "base"),
    ("0dba6399710fa947dc5d", "morphling_replicate", "unit_target_spell", "base"),
    ("c4c9a19f3fd010964b01", "phantom_assassin_phantom_strike", "unit_target_spell", "base"),
    ("9651e7885caaf7fd1553", "pugna_decrepify", "unit_target_spell", "base"),
    ("d5e57f0f93f66dedf40f", "undying_soul_rip", "unit_target_spell", "base"),
    ("7056861bb759c22212b6", "meepo_poof", "channeled", "base"),
    ("95b9db1c3a9654525662", "meteor_hammer", "channeled", "item"),
)


@lru_cache(maxsize=1)
def sources():
    documents, refs = {}, {}
    for key, name in SOURCE_PATHS.items():
        path = ROOT / name
        raw = read_source_bytes(path)
        documents[key] = json.loads(raw)
        refs[key] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}
    refs["baseline_admission"] = {"path": "/candidate/admission.json", "sha256": "a" * 64}
    refs["engineering_evidence"] = {"path": "/proof/mechanics.json", "sha256": "b" * 64}
    return documents, refs


def recount(document):
    document.update(
        counts=dict(Counter(row["patch_evidence_status"] for row in document["rows"])),
        candidate_usable_rows=sum(row["candidate_usable"] for row in document["rows"]),
        user_approved_for_patch_rows=sum(
            row["user_approved_for_patch"] for row in document["rows"]
        ),
    )


def recompute(inputs):
    baseline, _proof, documents, refs = inputs
    return build_mechanics_engineering_evidence(
        baseline,
        documents,
        exact_patch="7.42",
        source_refs={key: refs[key] for key in SOURCE_PATHS}
        | {"admission": refs["baseline_admission"]},
    )


@pytest.fixture
def inputs():
    documents, refs = deepcopy(sources())
    rows = []
    for key, subject, mechanism, context in FACTS:
        usable = key.startswith("7.42:")
        rows.append(
            {
                "review_id": key,
                "subject": subject,
                "mechanism": mechanism,
                "basis": "two_ai",
                "decision": "accept",
                "condition": {
                    "context": context,
                    "requires_scepter": False,
                    "requires_shard": context == "shard_upgrade",
                },
                "candidate_usable": usable,
                "user_approved_for_patch": False,
                "patch_evidence_status": "two_ai_overlay"
                if usable
                else "unreviewed_or_uncertain_for_patch"
                if key == ENIGMA
                else "fact_field_rebuild_unproven",
                "quotes": ["Preserved historical review quote"],
            }
        )
    rows.extend(
        [
            {
                **deepcopy(rows[0]),
                "review_id": "prior_user_approved",
                "subject": "old_subject",
                "basis": "user:U182",
                "candidate_usable": True,
                "user_approved_for_patch": True,
                "patch_evidence_status": "user_ruling_applied",
                "applied_user_decision": "user:U182",
            },
            {
                **deepcopy(rows[0]),
                "review_id": "unaffected_pending",
                "subject": "pending_subject",
                "patch_evidence_status": "pending_ruling",
                "pending_topic": "existing_user_ruling",
            },
            {
                **deepcopy(rows[0]),
                "review_id": "unaffected_reject",
                "subject": "rejected_subject",
                "decision": "reject",
                "patch_evidence_status": "excluded_fact",
            },
        ]
    )
    baseline = {
        "schema": "mechanics-action-admission/1",
        "policy": "mechanics-action-assets/7.42-v1",
        "patch": "7.42",
        "status": "candidate",
        "patch_verified": False,
        "formal_use_allowed": False,
        "training_allowed": False,
        "rows": rows,
        "source_refs": {"facts": {"path": "/candidate/facts.json", "sha256": "c" * 64}},
        "pending_review_ids": ["unaffected_pending"],
        "resolved_pending_review_ids": [],
    }
    recount(baseline)
    value = [baseline, None, documents, refs]
    value[1] = recompute(value)
    return value


def build(inputs, **kwargs):
    baseline, proof, documents, refs = inputs
    return build_evidence_admission(
        baseline, proof, documents, exact_patch=kwargs.get("exact_patch", "7.42"), source_refs=refs
    )


def row(document, key):
    return next(entry for entry in document["rows"] if entry["review_id"] == key)


def test_eight_promotions_and_fence_demotion_preserve_original_facts_and_approvals(inputs):
    output = build(inputs)
    assert output["schema"] == "mechanics-evidence-admission/1"
    assert output["summary"] == {
        "rows": 17,
        "engineering_rows": 14,
        "promoted_rows": 8,
        "demoted_rows": 1,
        "net_candidate_usable_change": 7,
        "link_enriched_rows": 3,
        "remaining_blocked_channel_rows": 2,
        "unchanged_non_target_rows": 3,
        "user_rulings_added": 0,
    }
    assert output["candidate_usable_rows"] == inputs[0]["candidate_usable_rows"] + 7
    assert output["user_approved_for_patch_rows"] == inputs[0]["user_approved_for_patch_rows"] == 1
    for before, after in zip(inputs[0]["rows"], output["rows"], strict=True):
        for key in (
            "review_id",
            "subject",
            "mechanism",
            "condition",
            "basis",
            "decision",
            "user_approved_for_patch",
            "quotes",
        ):
            assert before[key] == after[key]
        if before["review_id"] not in REVIEW_IDS:
            assert before == after
    assert output["pending_review_ids"] == inputs[0]["pending_review_ids"]
    assert output["formal_use_allowed"] is output["training_allowed"] is False
    assert output["action_review_allowed"] is output["patch_verified"] is False


def test_enigma_constraints_are_machine_fields_and_never_new_user_basis(inputs):
    fact = row(build(inputs), ENIGMA)
    detail = fact["engineering_admission"]
    assert fact["basis"] == "two_ai" and fact["user_approved_for_patch"] is False
    assert detail["conditions"] == {
        "requires_shard": True,
        "target_scope": "enemy_hero",
        "trigger": "each_malefice_stun",
        "summon": "Eidolon",
        "can_multiply": False,
    }
    assert detail["new_user_ruling"] is False
    assert detail["conditions_must_be_checked_at_use"] is True


def test_target_classification_does_not_unlock_block_reflect_or_immunity_interactions(inputs):
    output = build(inputs)
    for key in TARGET_IDS:
        fact = row(output, key)
        assert fact["candidate_usable"] is True
        detail = fact["engineering_admission"]
        assert detail["conditions"]["target_scope"]
        assert {
            "spell_block_interaction",
            "spell_reflect_interaction",
            "debuff_immunity_interaction",
        } <= set(detail["unproven_capabilities"])
    assert (
        row(output, "8804d4b34b90572aa12b")["engineering_admission"]["conditions"]["target_scope"]
        == "enemy_creep_base_enemy_hero_requires_scepter"
    )


def test_linked_healing_lifesteal_share_one_event_and_keep_unproved_strength(inputs):
    output = build(inputs)
    details = [
        row(output, f"7.42:life_stealer_infest:{mechanism}:shard")["engineering_admission"]
        for mechanism in ("slow", "healing", "lifesteal")
    ]
    assert details[1]["effect_identity"] == details[2]["effect_identity"]
    assert details[1]["deduplication_group"] == details[2]["deduplication_group"]
    assert details[0]["effect_identity"] != details[1]["effect_identity"]
    for detail in details:
        assert detail["conditions"]["duration_seconds"] == 3
        assert detail["conditions"]["requires_shard"] is True
        assert "linked_effect_strength" in detail["unproven_capabilities"]


def test_fence_and_channels_remain_unknown_not_rejected_game_claims(inputs):
    output = build(inputs)
    for key in (FENCE, "7056861bb759c22212b6", "95b9db1c3a9654525662"):
        fact = row(output, key)
        assert fact["decision"] == "accept" and fact["candidate_usable"] is False
        assert fact["engineering_admission"]["unproven_capabilities"]
    assert row(output, FENCE)["engineering_admission"]["prior_state"]["candidate_usable"] is True


@pytest.mark.parametrize(
    "change",
    [
        "status",
        "condition",
        "unknown",
        "definition",
        "source",
        "delete",
        "duplicate",
        "true_as_one",
    ],
)
def test_attachment_tampering_is_rejected_by_full_recomputation(inputs, change):
    proof = inputs[1]
    first = proof["rows"][0]
    if change == "status":
        first["proof_status"] = "enemy_target_text_supported"
    elif change == "condition":
        first["proposed_conditions"]["target_scope"] = "all_units"
    elif change == "unknown":
        first["unknown"] = []
    elif change == "definition":
        first["definition"]["value"]["definition"] = "Anything counts"
    elif change == "source":
        first["evidence"][0]["source_ref"]["sha256"] = "d" * 64
    elif change == "delete":
        proof["rows"].pop()
    elif change == "duplicate":
        proof["rows"].append(deepcopy(first))
    else:
        first["proposed_conditions"]["requires_shard"] = 1
    with pytest.raises(ValueError, match="differs from recomputed"):
        build(inputs)


@pytest.mark.parametrize(
    "change", ["baseline_ref", "source_ref", "missing_ref", "relative_ref", "extra_ref", "patch"]
)
def test_changed_source_binding_or_patch_is_not_silently_accepted(inputs, change):
    refs = inputs[3]
    if change == "baseline_ref":
        refs["baseline_admission"]["sha256"] = "d" * 64
    elif change == "source_ref":
        refs["hero_33_english"]["sha256"] = "d" * 64
    elif change == "missing_ref":
        del refs["items"]
    elif change == "relative_ref":
        refs["engineering_evidence"]["path"] = "relative.json"
    elif change == "extra_ref":
        refs["extra"] = refs["items"]
    with pytest.raises(ValueError):
        build(inputs, exact_patch="7.42a" if change == "patch" else "7.42")


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "policy",
        "formal_use_allowed",
        "training_allowed",
        "patch_verified",
        "action_review_allowed",
        "duplicate",
        "counts",
        "approved_target",
        "basis",
        "identity",
        "condition",
        "missing",
    ],
)
def test_baseline_identity_counts_closed_use_and_approval_drift_are_rejected(inputs, change):
    baseline = inputs[0]
    if change in ("schema", "policy"):
        baseline[change] = "new/unregistered"
    elif change in (
        "formal_use_allowed",
        "training_allowed",
        "patch_verified",
        "action_review_allowed",
    ):
        baseline[change] = True
    elif change == "duplicate":
        baseline["rows"].append(deepcopy(baseline["rows"][0]))
        recount(baseline)
    elif change == "counts":
        baseline["candidate_usable_rows"] += 1
    elif change == "approved_target":
        baseline["rows"][0]["user_approved_for_patch"] = True
        recount(baseline)
    elif change == "basis":
        baseline["rows"][0]["basis"] = "user:invented"
    elif change == "identity":
        baseline["rows"][0]["subject"] = "different_ability"
    elif change == "condition":
        baseline["rows"][0]["condition"]["requires_scepter"] = True
    else:
        baseline["rows"].pop(0)
        recount(baseline)
    with pytest.raises(ValueError):
        build(inputs)


def test_changed_raw_source_cannot_reuse_old_attachment(inputs):
    ability = inputs[2]["hero_33_english"]["result"]["data"]["heroes"][0]["abilities"][0]
    ability["shard_loc"] = "No longer applies: " + ability["shard_loc"]
    with pytest.raises(ValueError, match="differs from recomputed"):
        build(inputs)


def test_recomputed_unknown_source_safely_blocks_promotion_and_existing_link(inputs):
    for hero, subject, field in (
        (33, "enigma_malefice", "shard_loc"),
        (54, "life_stealer_open_wounds", "desc_loc"),
    ):
        abilities = inputs[2][f"hero_{hero}_english"]["result"]["data"]["heroes"][0]["abilities"]
        ability = next(value for value in abilities if value["name"] == subject)
        ability[field] = "No longer applies: " + ability[field]
    inputs[1] = recompute(inputs)
    output = build(inputs)
    for key in (
        ENIGMA,
        "7.42:life_stealer_infest:slow:shard",
        "7.42:life_stealer_infest:healing:shard",
        "7.42:life_stealer_infest:lifesteal:shard",
    ):
        fact = row(output, key)
        assert fact["candidate_usable"] is False
        assert fact["engineering_admission"]["conditions"] is None
        assert fact["engineering_admission"]["operation"] == "block_source_requirement"
    assert output["summary"]["promoted_rows"] == 7
    assert output["summary"]["demoted_rows"] == 4


def test_no_input_mutation_or_aliases_between_inputs_return_and_change_log(inputs):
    before = deepcopy(inputs)
    output = build(inputs)
    assert inputs == before
    original_output = deepcopy(output)
    fact = row(output, ENIGMA)
    fact["engineering_admission"]["conditions"]["target_scope"] = "changed"
    fact["engineering_admission"]["prior_state"]["condition"]["requires_shard"] = False
    output["source_refs"]["baseline_admission"]["path"] = "/changed"
    assert output["changes"][0]["before"]["condition"]["requires_shard"] is True
    assert inputs == before
    assert build(inputs) == original_output
    inputs[0]["rows"][-1]["quotes"].append("later caller edit")
    assert row(output, "unaffected_reject")["quotes"] == ["Preserved historical review quote"]


def test_proof_pointers_digests_and_prior_states_bind_each_changed_row(inputs):
    output = build(inputs)
    for changed in output["changes"]:
        fact = row(output, changed["review_id"])
        detail = fact["engineering_admission"]
        ref = detail["proof_ref"]
        proof = inputs[1]["rows"][int(ref["pointer"].rsplit("/", 1)[1])]
        assert proof["review_id"] == ref["review_id"] == fact["review_id"]
        encoded = json.dumps(
            proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        assert hashlib.sha256(encoded).hexdigest() == ref["row_sha256"]
        assert detail["prior_state"] == changed["before"]
        assert ref["source_ref"] == inputs[3]["engineering_evidence"]
