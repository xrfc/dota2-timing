"""Patch-specific evidence admission must survive all derived projections."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from dota_items.data.mechanics_action_assets import (
    SOURCE_KEYS,
    build_action_assets,
    required_pending_review_ids,
)


def _condition(context="base"):
    return {
        "context": context,
        "requires_scepter": context == "scepter_upgrade",
        "requires_shard": context == "shard_upgrade",
    }


def _row(key, subject, mechanism, *, basis="two_ai", context="base", decision="accept"):
    return {
        "review_id": key,
        "subject": subject,
        "mechanism": mechanism,
        "basis": basis,
        "condition": _condition(context),
        "decision": decision,
        "quotes": ["reviewed source text"],
        "condition_notes": [],
    }


def _ability(name, *, behavior="16", target_team=0):
    return {
        "name": name,
        "name_zh": name,
        "raw_mechanics": {"behavior": behavior, "target_team": target_team, "dispellable": 2},
        "cooldowns": [12.0, 10.0],
        "cast_ranges": [600.0],
        "special_values": [
            {"name": "blink_range", "values_float": [600.0, 800.0]},
            {"name": "blink_speed", "values_float": [1000.0]},
        ],
    }


@pytest.fixture
def inputs():
    rows = [
        _row("move", "blink_spell", "self_mobility"),
        _row("legacy", "legacy_save", "death_prevention", basis="user:U70"),
        _row("pending", "juggernaut_blade_fury", "applies_strong_dispel", basis="user:U75"),
        _row("burrow", "nyx_assassin_burrow", "mana_gain", basis="user:U52"),
        _row("field", "field_save", "spell_block", basis="field:behavior"),
        _row("unknown", "unknown_save", "invisibility"),
        _row("item", "test_item", "applies_basic_dispel", context="item"),
        _row("smoke", "smoke_of_deceit", "invisibility", context="item"),
        _row("rejected", "blink_spell", "invisibility", decision="reject"),
    ]
    lanes = {
        "legacy": "keep_user",
        "pending": "user_cat4",
        "burrow": "keep_user",
        "field": "field_rebuild",
    }
    reviews = [
        {
            "review_id": row["review_id"],
            "subject": row["subject"],
            "mechanism": row["mechanism"],
            "lane": lanes.get(row["review_id"], "keep_two_ai"),
            "codex": "holds",
        }
        for row in rows
        if row["review_id"] != "unknown"
    ]
    rules = [
        {
            "id": key,
            "zh": key,
            "relation": "counters",
            "decision": "U30",
            "source_mechanisms": ["applies_basic_dispel"],
            "target_mechanisms": ["self_mobility"],
        }
        for key in ("R01", "R06")
    ]
    return {
        "facts_doc": {
            "schema": "mechanics-facts/27",
            "patch_verified": False,
            "rows": rows,
            "field_observations": [],
            "skill_notes": [],
            "condition_exceptions": [],
        },
        "rules_doc": {"schema": "mechanics-rules/1", "rules": rules},
        "vocabulary_doc": {
            "mechanisms": [
                {"id": mechanism} for mechanism in sorted({r["mechanism"] for r in rows})
            ]
        },
        "review_doc": {"schema": "mechanics-recheck-742/1", "rows": reviews},
        "patch_registry": {
            "target_patch": "7.42",
            "heroes": [
                {
                    "hero_id": 1,
                    "npc_name": "npc_dota_hero_test",
                    "name_zh": "test",
                    "abilities": [
                        _ability(row["subject"])
                        for row in rows
                        if row["condition"]["context"] == "base" and row["review_id"] != "rejected"
                    ],
                },
                {
                    "hero_id": 2,
                    "npc_name": "npc_dota_hero_empty",
                    "name_zh": "empty",
                    "abilities": [],
                },
            ],
        },
        "exact_patch": "7.42",
        "source_refs": {
            key: {"path": f"inputs/{key}.json", "sha256": "0" * 64} for key in SOURCE_KEYS
        },
        "pending_review_ids": ["pending", "burrow"],
        "overlay_doc": {"schema": "mechanics-overlay-inputs/1", "version": 27, "operations": []},
        "evaluation_doc": {
            "schema": "mechanics-rules-evaluation/3",
            "rules": [
                {
                    "id": rule["id"],
                    "sources": ["test_item"],
                    "targets": ["blink_spell"],
                    "source_conditions": {"test_item": [{"when": "item", "unless": []}]},
                    "target_conditions": {"blink_spell": [{"when": "base", "unless": []}]},
                }
                for rule in rules
            ],
        },
        "trait_mapping_doc": {
            "status": "candidate",
            "counting": "per ability",
            "traits": {
                "mobile": {"zh": "mobility", "mechanisms": ["self_mobility"]},
                "strong_dispel": {"zh": "dispel", "mechanisms": ["applies_strong_dispel"]},
                "old_named": {"zh": "named", "from_heroes": [1]},
            },
        },
        "item_names_doc": {
            "result": {"data": {"itemabilities": [{"name": "item_test_item", "name_loc": "test"}]}}
        },
        "retired_items_doc": {"status": {"test_item": "purchasable"}},
        "extra_abilities_doc": {"heroes": []},
    }


def _admission(result):
    return {row["review_id"]: row for row in result["admission"]["rows"]}


def _add(inputs, row, *, lane="keep_two_ai", codex="holds", ability=True):
    inputs["facts_doc"]["rows"].append(row)
    if row["mechanism"] not in {m["id"] for m in inputs["vocabulary_doc"]["mechanisms"]}:
        inputs["vocabulary_doc"]["mechanisms"].append({"id": row["mechanism"]})
    inputs["review_doc"]["rows"].append(
        {**{k: row[k] for k in ("review_id", "subject", "mechanism")}, "lane": lane, "codex": codex}
    )
    abilities = inputs["patch_registry"]["heroes"][0]["abilities"]
    if ability and row["subject"] not in {a["name"] for a in abilities}:
        abilities.append(_ability(row["subject"]))


def _sha(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _proof(inputs, ids, *, equivalent=True):
    facts = inputs["facts_doc"]
    inputs["source_refs"]["equivalence"] = {"path": "proof.json", "sha256": "a" * 64}
    proof = {
        "schema": "mechanics-source-equivalence/1",
        "patch": "7.42",
        "baseline_patch": "7.41f",
        "base": {
            "schema": "mechanics-facts/26",
            "path": "knowledge/mechanics/extractions/v26/facts-v26.json",
            "sha256": "391aa4268b6be3714984b48d401c3c966728a750aba0172ab209ca761ce18f95",
            "document_sha256": "c" * 64,
        },
        "candidate": {"schema": facts["schema"], "document_sha256": _sha(facts)},
        "rows": [],
    }
    for row in facts["rows"]:
        if row["review_id"] in ids:
            proof["rows"].append(
                {
                    **{
                        k: deepcopy(row[k])
                        for k in (
                            "review_id",
                            "subject",
                            "mechanism",
                            "decision",
                            "condition",
                            "basis",
                        )
                    },
                    "fact_sha256": _sha(row),
                    "base_fact_sha256": _sha(row),
                    "source_equivalent": equivalent,
                    "status": "source_identical" if equivalent else "unknown",
                    "raw_source_refs": [
                        {
                            "patch": patch,
                            "language": language,
                            "path": patch + "/" + language + "/raw.json",
                            "sha256": "d" * 64,
                            "subject_sha256": ("e" if language == "english" else "a") * 64,
                        }
                        for patch in ("7.41f", "7.42")
                        for language in ("english", "schinese")
                    ],
                    "script_source_refs": [
                        {
                            "patch": patch,
                            "path": patch + "/script.txt",
                            "sha256": "f" * 64,
                            "block_sha256": "0" * 64,
                        }
                        for patch in ("7.41f", "7.42")
                    ],
                }
            )
    inputs["source_equivalence_doc"] = proof
    return proof


def test_full_source_equivalence_admits_unchanged_fact_without_new_user_approval(inputs):
    _proof(inputs, ["unknown", "pending"])
    result = build_action_assets(**inputs)
    rows = _admission(result)
    assert rows["unknown"]["patch_evidence_status"] == "source_equivalent"
    assert rows["unknown"]["candidate_usable"] is True
    assert rows["unknown"]["user_approved_for_patch"] is False
    assert rows["unknown"]["source_equivalence_evidence"]["new_user_approval"] is False
    assert rows["pending"]["patch_evidence_status"] == "pending_ruling"
    assert rows["pending"]["candidate_usable"] is False


@pytest.mark.parametrize(
    "damage",
    [
        "patch",
        "base",
        "base-sha",
        "doc",
        "row",
        "claim",
        "raw-missing",
        "script-mismatch",
        "old-fact",
    ],
)
def test_source_equivalence_rejects_wrong_identity_or_incomplete_proof(inputs, damage):
    proof = _proof(inputs, ["unknown"])
    row = proof["rows"][0]
    if damage == "patch":
        proof["patch"] = "7.41f"
    elif damage == "base":
        proof["base"]["schema"] = "mechanics-facts/25"
    elif damage == "base-sha":
        proof["base"]["sha256"] = "0" * 64
    elif damage == "doc":
        proof["candidate"]["document_sha256"] = "0" * 64
    elif damage == "row":
        row["fact_sha256"] = "0" * 64
    elif damage == "claim":
        row["mechanism"] = "self_mobility"
    elif damage == "raw-missing":
        row["raw_source_refs"].pop()
    elif damage == "script-mismatch":
        row["script_source_refs"][0]["block_sha256"] = "1" * 64
    else:
        row["base_fact_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        build_action_assets(**inputs)


@pytest.mark.parametrize(
    ("mechanism", "behavior", "team", "expected"),
    [
        ("unit_target_spell", "8", 2, True),
        ("unit_target_spell", "8", 3, True),
        ("unit_target_spell", "8", 4, False),
        ("unit_target_spell", "8", 0, False),
        ("unit_target_spell", "2", 2, False),
        ("channeled", "128", 0, True),
        ("channeled", "8", 1, False),
    ],
)
def test_current_registry_can_prove_existing_field_claim_without_semantic_expansion(
    inputs, mechanism, behavior, team, expected
):
    row = _row("field-check", "field_ability", mechanism)
    _add(inputs, row, lane="field_rebuild")
    ability = inputs["patch_registry"]["heroes"][0]["abilities"][-1]
    ability["raw_mechanics"].update(behavior=behavior, target_team=team)
    admitted = _admission(build_action_assets(**inputs))["field-check"]
    assert admitted["candidate_usable"] is expected
    assert admitted["user_approved_for_patch"] is False
    if expected:
        assert admitted["patch_evidence_status"] == "current_fields_verified"
        assert admitted["current_field_evidence"]["pointer"].endswith("/raw_mechanics")
        assert admitted["current_field_evidence"]["raw_fields"] == ability["raw_mechanics"]


@pytest.mark.parametrize(
    ("subject", "decision", "pending"),
    [
        ("partial_break", "accept", False),
        ("dazzle_innate_weave", "reject", True),
        ("windrunner_tailwind", "accept", True),
        ("centaur_horsepower", "reject", True),
    ],
)
def test_current_break_flag_preserves_scope_and_never_overrides_unresolved_ruling(
    inputs, subject, decision, pending
):
    row = _row("break-check", subject, "break_sensitive", decision=decision, basis="user:U47")
    row["break_conditions_en"] = ["Break only prevents automatic activation."]
    _add(inputs, row, lane="field_rebuild")
    if pending:
        inputs["pending_review_ids"].append("break-check")
    proof = _proof(inputs, ["break-check"], equivalent=False)
    proof["rows"][0]["current_script_fields"] = {
        "IsBreakable": {
            "value": "1",
            "unambiguous": True,
            "occurrences": 1,
            "source_refs": [proof["rows"][0]["script_source_refs"][1]],
        }
    }
    admitted = _admission(build_action_assets(**inputs))["break-check"]
    assert admitted["candidate_usable"] is (not pending)
    assert admitted["user_approved_for_patch"] is False
    assert admitted["break_conditions_en"] == row["break_conditions_en"]
    proof["rows"][0]["current_script_fields"]["IsBreakable"]["unambiguous"] = False
    assert _admission(build_action_assets(**inputs))["break-check"]["candidate_usable"] is False


def test_six_payloads_retain_distinct_evidence_and_closed_admission(inputs):
    result = build_action_assets(**inputs)
    assert set(result) == {
        "profiles",
        "save_means",
        "mobility",
        "admission",
        "counter_graph",
        "hero_traits",
    }
    for payload in result.values():
        assert payload["patch"] == "7.42"
        assert payload["status"] == "candidate"
        assert payload["patch_verified"] is False
        assert payload["formal_use_allowed"] is payload["training_allowed"] is False
        assert payload["source_integrity_checked_here"] is False
    rows = _admission(result)
    assert rows["move"]["candidate_usable"] is True
    assert rows["move"]["user_approved_for_patch"] is False
    assert rows["legacy"]["patch_evidence_status"] == "prior_user_ruling_retained"
    assert rows["legacy"]["original_user_basis"] is True
    assert rows["legacy"]["user_approved_for_patch"] is False
    for key in ("pending", "burrow", "field", "unknown", "rejected"):
        assert rows[key]["candidate_usable"] is False
    assert result["admission"]["user_approved_for_patch_rows"] == 0
    assert set(result["save_means"]["means"]) == {"blink_spell", "legacy_save", "item_test_item"}
    assert "U136_smoke_is_not_a_save" in {row["reason"] for row in result["save_means"]["blocked"]}


@pytest.mark.parametrize("patch", ["7.41f", "7.42a", "latest", "7.42 ", None])
def test_exact_patch_only(inputs, patch):
    inputs["exact_patch"] = patch
    with pytest.raises(ValueError, match="exact patch"):
        build_action_assets(**inputs)


def test_registry_patch_mismatch(inputs):
    inputs["patch_registry"]["target_patch"] = "7.41f"
    with pytest.raises(ValueError, match="exact patch"):
        build_action_assets(**inputs)


def test_required_pending_includes_explicit_selector_without_changed_review(inputs):
    assert required_pending_review_ids(inputs["facts_doc"], inputs["review_doc"]) == [
        "burrow",
        "pending",
    ]
    inputs["pending_review_ids"] = ["pending"]
    with pytest.raises(ValueError, match="cannot be omitted"):
        build_action_assets(**inputs)


def test_pending_identity_must_exist(inputs):
    inputs["pending_review_ids"].append("not-a-fact")
    with pytest.raises(ValueError, match="absent"):
        build_action_assets(**inputs)


def test_u188_requires_exact_overlay_and_preserves_shard_condition(inputs):
    row = _row(
        "7.42:c108", "undying_bite", "self_mobility", basis="user:U188", context="shard_upgrade"
    )
    _add(inputs, row, lane="user_cat8")
    inputs["pending_review_ids"].append(row["review_id"])
    before = _admission(build_action_assets(**inputs))[row["review_id"]]
    assert before["patch_evidence_status"] == "pending_ruling"
    inputs["overlay_doc"]["operations"].append({"op": "add_row", **deepcopy(row)})
    result = build_action_assets(**inputs)
    admitted = _admission(result)[row["review_id"]]
    assert admitted["user_approved_for_patch"] is True
    assert row["review_id"] not in result["admission"]["pending_review_ids"]
    mobile = result["mobility"]["heroes"]["npc_dota_hero_test"]["abilities"][-1]
    assert mobile["fact"]["condition"] == _condition("shard_upgrade")
    assert mobile["distance_values"] == {"blink_range": [600.0, 800.0]}
    assert mobile["distance_interpretation_verified"] is False
    assert mobile["cooldowns"] == [12.0, 10.0]


@pytest.mark.parametrize("change", ["basis", "condition", "mechanism", "decision"])
def test_mismatched_overlay_does_not_approve_user_ruling(inputs, change):
    row = _row(
        "7.42:c108", "undying_bite", "self_mobility", basis="user:U188", context="shard_upgrade"
    )
    _add(inputs, row, lane="user_cat8")
    inputs["pending_review_ids"].append(row["review_id"])
    op = {"op": "add_row", **deepcopy(row)}
    op[change] = _condition() if change == "condition" else "wrong"
    inputs["overlay_doc"]["operations"].append(op)
    assert (
        _admission(build_action_assets(**inputs))[row["review_id"]]["user_approved_for_patch"]
        is False
    )


@pytest.mark.parametrize(
    ("key", "subject", "mechanism", "basis"),
    [
        ("62613f1350de1228dd41", "troll_warlord_battle_trance", "slow_resistance", "user:U183"),
        (
            "audit:death_prophet_spirit_siphon:lifesteal:base",
            "death_prophet_spirit_siphon",
            "lifesteal",
            "user:U187",
        ),
    ],
)
def test_applied_rejection_is_user_approved_but_not_a_capability(
    inputs, key, subject, mechanism, basis
):
    row = _row(key, subject, mechanism, basis=basis, decision="reject")
    _add(inputs, row, lane="user_cat8")
    inputs["overlay_doc"]["operations"].append(
        {
            "op": "decision_change",
            "review_id": key,
            "from": "accept",
            "to": "reject",
            "basis": basis,
        }
    )
    admitted = _admission(build_action_assets(**inputs))[key]
    assert admitted["user_approved_for_patch"] is True
    assert admitted["candidate_usable"] is False


def test_u183_status_resistance_is_distinct_from_slow_resistance(inputs):
    row = _row("7.42:c079", "troll_warlord_battle_trance", "status_resistance", basis="user:U183")
    _add(inputs, row, lane="user_cat8")
    inputs["overlay_doc"]["operations"].append({"op": "add_row", **row})
    admitted = _admission(build_action_assets(**inputs))[row["review_id"]]
    assert admitted["user_approved_for_patch"] is admitted["candidate_usable"] is True
    assert admitted["mechanism"] == "status_resistance"


def test_two_ai_overlay_is_not_user_approval(inputs):
    row = _row("new-ai", "new_escape", "self_mobility")
    _add(inputs, row, lane="change_two_ai")
    inputs["overlay_doc"]["operations"].append(
        {"op": "add_row", "claude": "accept", "codex": "accept", **row}
    )
    admitted = _admission(build_action_assets(**inputs))[row["review_id"]]
    assert admitted["patch_evidence_status"] == "two_ai_overlay"
    assert admitted["candidate_usable"] is True
    assert admitted["user_approved_for_patch"] is False


def test_unclear_two_ai_review_does_not_reuse_old_agreement(inputs):
    inputs["review_doc"]["rows"][0]["codex"] = "unclear"
    assert _admission(build_action_assets(**inputs))["move"]["candidate_usable"] is False


@pytest.mark.parametrize(
    ("behavior", "team"), [("2", 0), (16, 2), (None, 0), ("not-numeric", 0), (16, None)]
)
def test_save_filter_uses_current_targeting_fields(inputs, behavior, team):
    raw = inputs["patch_registry"]["heroes"][0]["abilities"][0]["raw_mechanics"]
    raw.update(behavior=behavior, target_team=team)
    result = build_action_assets(**inputs)
    assert "blink_spell" not in result["save_means"]["means"]
    assert (
        result["mobility"]["heroes"]["npc_dota_hero_test"]["abilities"][0]["ability"]
        == "blink_spell"
    )


def test_haste_selection_scope_does_not_assert_every_haste_is_save(inputs):
    _add(inputs, _row("haste-known", "mirana_leap", "haste"))
    _add(inputs, _row("haste-other", "other_haste", "haste"))
    means = build_action_assets(**inputs)["save_means"]
    assert "mirana_leap" in means["means"]
    assert "other_haste" not in means["means"]
    assert any(r["reason"] == "outside_U121_U131_haste_selection" for r in means["blocked"])


@pytest.mark.parametrize("pending_rule", ["R06", "R18", "R20"])
def test_complete_graph_retains_evidence_and_pending_rule_edges(inputs, pending_rule):
    inputs["rules_doc"]["rules"][1]["id"] = pending_rule
    inputs["evaluation_doc"]["rules"][1]["id"] = pending_rule
    graph = build_action_assets(**inputs)["counter_graph"]
    assert graph["schema"] == "candidate-counter-graph/1"
    assert graph["pairs_verified"] is False
    edges = {edge["rule"]: edge for edge in graph["item_to_hero"]}
    assert edges["R01"]["candidate_usable"] is True
    assert edges["R01"]["fact_ids"] == ["item", "move"]
    assert edges[pending_rule]["candidate_usable"] is False
    assert edges[pending_rule]["status"] == "pending"
    assert all(edge["confirmed"] is False for edge in edges.values())
    assert all(node["confirmed"] is False for rule in graph["rules"] for node in rule["sources"])


def test_pending_target_blocks_edge_even_if_graph_derivation_still_lists_it(inputs):
    inputs["pending_review_ids"].append("move")
    graph = build_action_assets(**inputs)["counter_graph"]
    assert all(not edge["candidate_usable"] for edge in graph["item_to_hero"])
    assert all(edge["blocked_fact_ids"] == ["move"] for edge in graph["item_to_hero"])


def test_existing_u181_rule_note_is_not_reopened_as_pending(inputs):
    path = (
        Path(__file__).resolve().parents[1] / "knowledge/mechanics/reviews/rules-v14-draft-001.json"
    )
    rule = next(r for r in json.loads(path.read_text())["rules"] if r["id"] == "R09")
    assert "U181" in rule["decision"]
    assert "魔法抗性结算" in rule["note"]
    inputs["rules_doc"]["rules"].append(rule)
    inputs["evaluation_doc"]["rules"].append(
        {
            "id": "R09",
            "sources": [],
            "targets": [],
            "source_conditions": {},
            "target_conditions": {},
        }
    )
    result = build_action_assets(**inputs)
    derived = next(r for r in result["counter_graph"]["rules"] if r["id"] == "R09")
    assert derived["pending"] is None
    assert derived["note"] == rule["note"]


@pytest.mark.parametrize(
    ("key", "subject", "mechanism"),
    [
        ("7c2911cf7844f3051597", "pugna_life_drain", "channeled"),
        ("fe8476a622f929db996e", "death_prophet_witchcraft", "haste"),
    ],
)
def test_explicit_u182_retention_does_not_require_a_change_operation(
    inputs, key, subject, mechanism
):
    _add(inputs, _row(key, subject, mechanism), lane="user_cat8")
    inputs["pending_review_ids"].append(key)
    result = build_action_assets(**inputs)
    row = _admission(result)[key]
    assert row["basis"] == "two_ai"
    assert row["original_user_basis"] is False
    assert row["applied_user_decision"] == "user:U182"
    assert row["patch_approval_evidence"] == "existing_user_retention_decision"
    assert row["candidate_usable"] is row["user_approved_for_patch"] is True
    assert key not in result["admission"]["pending_review_ids"]


def test_applied_meepo_grant_correction_is_two_ai_evidence_not_user_ruling(inputs):
    key = "audit:meepo_petrify:healing:shard"
    row = _row(key, "meepo_petrify", "healing", context="scepter_upgrade")
    _add(inputs, row, lane="user_old_error")
    ability = inputs["patch_registry"]["heroes"][0]["abilities"][-1]
    ability.update(granted_by_scepter=True, granted_by_shard=False)
    inputs["pending_review_ids"].append(key)
    inputs["overlay_doc"]["operations"].append(
        {
            "op": "condition_change",
            "review_id": key,
            "subject": row["subject"],
            "mechanism": row["mechanism"],
            "basis": "two_ai",
            "from": _condition("shard_upgrade"),
            "to": _condition("scepter_upgrade"),
        }
    )
    result = build_action_assets(**inputs)
    admitted = _admission(result)[key]
    assert admitted["patch_evidence_status"] == "two_ai_overlay"
    assert admitted["candidate_usable"] is True
    assert admitted["user_approved_for_patch"] is False
    assert key not in result["admission"]["pending_review_ids"]
    ability["granted_by_scepter"] = False
    assert _admission(build_action_assets(**inputs))[key]["candidate_usable"] is False


def test_trait_counts_preserve_candidate_numbers_and_do_not_encode_unknown_as_zero(inputs):
    traits = build_action_assets(**inputs)["hero_traits"]["traits"]
    mobile = traits["mobile"]["counts"][0]
    assert mobile["candidate_base"] == mobile["base"] == 1
    assert mobile["fact_ids"] == ["move"]
    pending = traits["strong_dispel"]["counts"][0]
    assert pending["candidate_base"] == 1
    assert pending["base"] is pending["with_upgrades"] is None
    assert pending["blocked_fact_ids"] == ["pending"]
    assert all(row["base"] is None for row in traits["old_named"]["counts"])
    assert all(not row["absence_verified"] for trait in traits.values() for row in trait["counts"])


def test_old_extra_catalog_cannot_admit_trait_without_current_registry_identity(inputs):
    hero = inputs["patch_registry"]["heroes"][0]
    moved = hero["abilities"].pop(0)
    inputs["extra_abilities_doc"]["heroes"] = [{"hero_id": hero["hero_id"], "abilities": [moved]}]
    result = build_action_assets(**inputs)
    count = result["hero_traits"]["traits"]["mobile"]["counts"][0]
    assert count["candidate_base"] == count["candidate_with_upgrades"] == 1
    assert count["base"] is count["with_upgrades"] is None
    assert count["candidate_usable"] is False
    assert count["unknown_registry_subjects"] == ["blink_spell"]
    assert count["blocked_fact_ids"] == []
    assert _admission(result)["move"]["candidate_usable"] is True
    assert all(not edge["candidate_usable"] for edge in result["counter_graph"]["item_to_hero"])


def test_inputs_and_returned_artifacts_do_not_share_mutable_state(inputs):
    before = deepcopy(inputs)
    result = build_action_assets(**inputs)
    assert inputs == before
    result["admission"]["rows"][0]["condition"]["context"] = "changed"
    result["profiles"]["source_refs"]["facts"]["sha256"] = "changed"
    assert (
        result["mobility"]["heroes"]["npc_dota_hero_test"]["abilities"][0]["fact"]["condition"]
        == _condition()
    )
    assert result["admission"]["source_refs"]["facts"]["sha256"] == "0" * 64
    assert inputs == before


@pytest.mark.parametrize(
    "damage",
    [
        "missing-ref",
        "bad-sha",
        "bad-condition",
        "duplicate-fact",
        "wrong-review",
        "wrong-evaluation",
        "nonfinite-numeric",
    ],
)
def test_invalid_evidence_inputs_fail_closed(inputs, damage):
    if damage == "missing-ref":
        inputs["source_refs"].pop("overlay")
    elif damage == "bad-sha":
        inputs["source_refs"]["facts"]["sha256"] = "a" * 63
    elif damage == "bad-condition":
        inputs["facts_doc"]["rows"][0]["condition"]["requires_shard"] = 0
    elif damage == "duplicate-fact":
        inputs["facts_doc"]["rows"].append(deepcopy(inputs["facts_doc"]["rows"][0]))
    elif damage == "wrong-review":
        inputs["review_doc"]["rows"][0]["subject"] = "wrong"
    elif damage == "wrong-evaluation":
        inputs["evaluation_doc"]["rules"].pop()
    else:
        inputs["patch_registry"]["heroes"][0]["abilities"][0]["cooldowns"] = [float("nan")]
    with pytest.raises(ValueError):
        build_action_assets(**inputs)
