"""Current source links must not silently approve semantics or triggered behavior."""

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pytest

from dota_items.data.mechanics_engineering_evidence import (
    SOURCE_PATHS,
    build_mechanics_engineering_evidence,
)
from dota_items.data.source_io import read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
FACTS = (
    ("audit:enigma_malefice:summons:shard", "enigma_malefice", "summons", "shard_upgrade"),
    ("7.42:life_stealer_infest:slow:shard", "life_stealer_infest", "slow", "shard_upgrade"),
    (
        "7.42:life_stealer_infest:lifesteal:shard",
        "life_stealer_infest",
        "lifesteal",
        "shard_upgrade",
    ),
    ("7.42:life_stealer_infest:healing:shard", "life_stealer_infest", "healing", "shard_upgrade"),
    (
        "7.42:disruptor_kinetic_fence:aoe_damage:shard",
        "disruptor_kinetic_fence",
        "aoe_damage",
        "shard_upgrade",
    ),
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
    refs["admission"] = {"path": "/engineering/admission.json", "sha256": "a" * 64}
    return documents, refs


@pytest.fixture
def inputs():
    documents, refs = copy.deepcopy(sources())
    admission = {
        "schema": "mechanics-action-admission/1",
        "policy": "mechanics-action-assets/7.42-v1",
        "status": "candidate",
        "patch": "7.42",
        "formal_use_allowed": False,
        "training_allowed": False,
        "rows": [
            {
                "review_id": rid,
                "subject": subject,
                "mechanism": mechanism,
                "decision": "accept",
                "condition": {
                    "context": context,
                    "requires_shard": context == "shard_upgrade",
                    "requires_scepter": False,
                },
                "candidate_usable": rid.startswith("7.42:"),
                "user_approved_for_patch": False,
                "patch_evidence_status": "two_ai_overlay"
                if rid.startswith("7.42:")
                else "unproven",
            }
            for rid, subject, mechanism, context in FACTS
        ],
    }
    return admission, documents, refs


def build(inputs):
    admission, documents, refs = inputs
    return build_mechanics_engineering_evidence(
        admission, documents, exact_patch="7.42", source_refs=refs
    )


def row(result, review_id):
    return next(r for r in result["rows"] if r["review_id"] == review_id)


def ability(documents, hero, subject, language="english"):
    return next(
        a
        for a in documents[f"hero_{hero}_{language}"]["result"]["data"]["heroes"][0]["abilities"]
        if a["name"] == subject
    )


def test_current_official_sources_support_eleven_proposals_and_keep_three_behavior_gaps(inputs):
    result = build(inputs)
    assert result["summary"] == {
        "rows": 14,
        "proof_statuses": {
            "condition_narrowing_proposed": 1,
            "linked_effect_text_supported": 3,
            "linked_damage_text_found_trigger_scope_unproven": 1,
            "enemy_target_text_supported": 7,
            "channel_text_found_interruption_unproven": 2,
        },
        "candidate_rows_changed": 0,
        "user_rulings_added": 0,
    }
    assert result["formal_use_allowed"] is result["action_review_allowed"] is False
    assert result["training_allowed"] is False
    assert all(not r["candidate_mutated"] and not r["user_ruling_added"] for r in result["rows"])


def test_enigma_restriction_is_structured_and_does_not_reclassify_the_old_row(inputs):
    r = row(build(inputs), "audit:enigma_malefice:summons:shard")
    assert r["proposed_conditions"] == {
        "requires_shard": True,
        "target_scope": "enemy_hero",
        "trigger": "each_malefice_stun",
        "summon": "Eidolon",
        "can_multiply": False,
    }
    assert r["current_candidate_state"]["candidate_usable"] is False
    assert r["current_candidate_state"]["condition"]["requires_shard"] is True


@pytest.mark.parametrize("language", ["english", "schinese"])
def test_negated_or_edited_current_text_cannot_keep_the_registered_proof(inputs, language):
    a = ability(inputs[1], 33, "enigma_malefice", language)
    a["shard_loc"] = "This no longer applies: " + a["shard_loc"]
    r = row(build(inputs), "audit:enigma_malefice:summons:shard")
    assert r["proof_status"] == "source_requirement_unproven"
    assert r["proposed_conditions"] is None


def test_linked_healing_and_lifesteal_share_an_event_and_do_not_gain_strength(inputs):
    result = build(inputs)
    for mechanism in ("slow", "healing", "lifesteal"):
        r = row(result, f"7.42:life_stealer_infest:{mechanism}:shard")
        assert r["verified_link"]["duration_seconds"] == 3
        assert r["verified_link"]["healing_and_lifesteal_same_event"] is True
        assert (
            r["verified_link"]["healing_beneficiary"] == "allies_dealing_damage_to_affected_enemy"
        )
        assert "strength" not in r["verified_link"]
        assert r["current_candidate_state"]["candidate_usable"] is True
        assert r["current_candidate_state"]["user_approved_for_patch"] is False


def test_missing_linked_effect_text_is_not_inferred_from_ability_name(inputs):
    ability(inputs[1], 54, "life_stealer_open_wounds")["desc_loc"] = "An effect named Open Wounds."
    result = build(inputs)
    for mechanism in ("slow", "healing", "lifesteal"):
        r = row(result, f"7.42:life_stealer_infest:{mechanism}:shard")
        assert r["proof_status"] == "source_requirement_unproven"
        assert r["verified_link"] is None


def test_changed_shard_duration_cannot_keep_the_three_second_link(inputs):
    a = ability(inputs[1], 54, "life_stealer_infest")
    next(v for v in a["special_values"] if v["name"] == "dot_duration")["values_shard"] = [4]
    r = row(build(inputs), "7.42:life_stealer_infest:slow:shard")
    assert r["verified_link"] is None
    assert r["checks"]["three_second_shard_duration"] is False


def test_fence_text_link_does_not_prove_the_triggered_radius_or_victim_set(inputs):
    r = row(build(inputs), "7.42:disruptor_kinetic_fence:aoe_damage:shard")
    assert all(r["checks"].values())
    assert r["triggered_area_scope_verified"] is False
    assert r["chinese_trigger_name_matches_display_name"] is False
    assert r["current_candidate_state"]["candidate_usable"] is True


def test_custom_and_zero_target_teams_need_enemy_text_and_do_not_imply_item_interactions(inputs):
    result = build(inputs)
    targets = [r for r in result["rows"] if r["mechanism"] == "unit_target_spell"]
    assert len(targets) == 7
    assert all(r["proof_status"] == "enemy_target_text_supported" for r in targets)
    assert all(r["spell_block_or_reflect_inferred"] is False for r in targets)
    a = ability(inputs[1], 56, "clinkz_death_pact")
    assert a["target_team"] == 0
    a["desc_loc"] = "Consumes a friendly unit."
    r = row(build(inputs), "ebbbbe178b11c4ce1cbd")
    assert r["proof_status"] == "source_requirement_unproven"
    assert r["target_scope"] is None


def test_no_unit_target_behavior_cannot_be_repaired_by_text_alone(inputs):
    ability(inputs[1], 44, "phantom_assassin_phantom_strike")["behavior"] = "16"
    r = row(build(inputs), "c4c9a19f3fd010964b01")
    assert r["checks"]["unit_target_behavior"] is False
    assert r["proof_status"] == "source_requirement_unproven"


def test_channel_flag_and_text_do_not_certify_interruption_behavior(inputs):
    ability(inputs[1], 82, "meepo_poof")["behavior"] = "128"
    for r in build(inputs)["rows"]:
        if r["mechanism"] == "channeled":
            assert r["checks"]["explicit_channel_text"] is True
            assert r["checks"]["interruption_behavior_verified"] is False
            assert r["proof_status"] == "channel_text_found_interruption_unproven"


@pytest.mark.parametrize(
    "field,value",
    [("subject", "another_ability"), ("mechanism", "healing"), ("decision", "reject")],
)
def test_review_identity_and_existing_decision_cannot_be_silently_reinterpreted(
    inputs, field, value
):
    inputs[0]["rows"][0][field] = value
    with pytest.raises(ValueError, match="Fact identity"):
        build(inputs)


def test_shard_precondition_and_duplicate_review_ids_are_rejected(inputs):
    inputs[0]["rows"][0]["condition"]["requires_shard"] = False
    with pytest.raises(ValueError, match="Fact identity"):
        build(inputs)
    inputs[0]["rows"][0]["condition"]["requires_shard"] = True
    inputs[0]["rows"].append(copy.deepcopy(inputs[0]["rows"][0]))
    with pytest.raises(ValueError, match="Expected one review_id"):
        build(inputs)


def test_claim_id_cannot_be_attached_to_an_unrelated_mechanism(inputs):
    claim = next(r for r in inputs[1]["claim_key"] if r["claim_id"] == "c046")
    claim["mechanism"] = "healing"
    with pytest.raises(ValueError, match="Claim identity"):
        build(inputs)


@pytest.mark.parametrize("change", ["patch", "formal", "missing_source", "snapshot", "digest"])
def test_patch_purpose_and_incomplete_or_wrong_source_refs_are_rejected(inputs, change):
    if change == "patch":
        inputs[0]["patch"] = "7.42a"
    elif change == "formal":
        inputs[0]["formal_use_allowed"] = True
    elif change == "missing_source":
        del inputs[1]["hero_33_english"]
    elif change == "snapshot":
        ref = inputs[2]["hero_33_english"]
        ref["path"] = ref["path"].replace("2026-11-19", "2026-11-06")
    else:
        inputs[2]["hero_33_english"]["sha256"] = "unverified"
    with pytest.raises(ValueError):
        build(inputs)


def test_all_source_points_resolve_and_inputs_are_not_mutated(inputs):
    before = copy.deepcopy(inputs)
    result = build(inputs)
    assert inputs == before
    for r in result["rows"]:
        for p in [*r["evidence"], *([r["definition"]] if "definition" in r else [])]:
            value = inputs[1][p["source"]]
            for part in p["pointer"].strip("/").split("/"):
                value = value[int(part)] if isinstance(value, list) else value[part]
            assert value == p["value"]
            assert p["source_ref"] == inputs[2][p["source"]]
    result["source_refs"]["admission"]["path"] = "/different"
    assert inputs == before


def test_changed_vocabulary_semantics_require_a_new_registered_proof_policy(inputs):
    definition = next(
        r for r in inputs[1]["vocabulary"]["mechanisms"] if r["id"] == "unit_target_spell"
    )
    definition["definition"] = "Friendly targets only."
    with pytest.raises(ValueError, match="vocabulary definition"):
        build(inputs)


def test_conflicting_friendly_only_target_flag_does_not_keep_custom_target_proof(inputs):
    for lang in ("english", "schinese"):
        ability(inputs[1], 44, "phantom_assassin_phantom_strike", lang)["target_team"] = 1
    r = row(build(inputs), "c4c9a19f3fd010964b01")
    assert r["proof_status"] == "source_requirement_unproven"
