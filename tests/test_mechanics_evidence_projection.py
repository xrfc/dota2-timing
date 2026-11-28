from copy import deepcopy

import pytest

from dota_items.data import mechanics_evidence_projection as module
from dota_items.data.mechanics_evidence_projection import BASE_SCHEMAS, project_evidence_assets


def fact(key, *, usable, mechanism="unit_target_spell"):
    return {
        "review_id": key,
        "subject": key,
        "mechanism": mechanism,
        "decision": "accept",
        "basis": "two_ai",
        "candidate_usable": usable,
        "user_approved_for_patch": False,
        "condition": {"context": "base", "requires_scepter": False, "requires_shard": False},
    }


@pytest.fixture
def inputs(monkeypatch):
    old = [
        fact("target", usable=False),
        fact("fence", usable=True, mechanism="aoe_damage"),
        fact("sphere", usable=True, mechanism="spell_block"),
    ]
    new = deepcopy(old)
    for row, usable in zip(new, (True, False, True), strict=True):
        if row["review_id"] != "sphere":
            row.update(
                candidate_usable=usable,
                engineering_admission={
                    "conditions": {
                        "target_scope": "enemy_nonhero",
                        "requires_shard": True,
                        "can_multiply": False,
                    },
                    "unproven_capabilities": ["spell_block_interaction"],
                    "effect_identity": None,
                },
            )
    baseline = {"schema": "mechanics-action-admission/1", "rows": old, "source_refs": {}}
    admission = {
        "schema": "mechanics-evidence-admission/1",
        "patch": "7.42",
        "rows": new,
        "formal_use_allowed": False,
        "training_allowed": False,
        "action_review_allowed": False,
    }
    assets = {
        name: {
            "schema": schema,
            "policy": "mechanics-action-assets/7.42-v1",
            "patch": "7.42",
            "formal_use_allowed": False,
            "training_allowed": False,
            "source_refs": {},
        }
        for name, schema in BASE_SCHEMAS.items()
    }
    assets["profiles"].update(
        heroes={
            "hero": {
                "hero_id": 1,
                "abilities": [{"ability": r["subject"], "facts": [deepcopy(r)]} for r in old],
            }
        },
        other_subjects={},
    )
    graph = assets["counter_graph"]
    graph.update(rules=[], item_to_hero=[])
    for key, usable in (("target", False), ("fence", True)):
        graph["rules"].append(
            {
                "id": key,
                "sources": [
                    {
                        "subject": "sphere",
                        "fact_ids": ["sphere"],
                        "candidate_usable": True,
                        "blocked_fact_ids": [],
                    }
                ],
                "targets": [
                    {
                        "subject": key,
                        "kind": "ability",
                        "hero_id": 1,
                        "fact_ids": [key],
                        "candidate_usable": usable,
                        "blocked_fact_ids": [] if usable else [key],
                    }
                ],
            }
        )
        graph["item_to_hero"].append(
            {
                "rule": key,
                "item": "sphere",
                "hero_id": 1,
                "abilities": [key],
                "fact_ids": sorted(["sphere", key]),
                "candidate_usable": usable,
                "blocked_fact_ids": [],
                "status": "candidate" if usable else "pending",
            }
        )
    assets["hero_traits"]["traits"] = {
        "t": {
            "counts": [
                {
                    "hero_id": 1,
                    "fact_ids": ["fence"],
                    "candidate_usable": True,
                    "base": 1,
                    "with_upgrades": 1,
                    "candidate_base": 1,
                    "candidate_with_upgrades": 1,
                    "blocked_fact_ids": [],
                }
            ],
            "heroes": [
                {
                    "hero_id": 1,
                    "ability_count": 1,
                    "abilities": [
                        {"subject": "fence", "evidence": [{"quote": "legacy description"}]}
                    ],
                }
            ],
        }
    }
    assets["save_means"].update(means={}, blocked=[])
    assets["mobility"].update(heroes={}, items=[], blocked=[])
    # Isolate projection semantics. Actual proof reconstruction has its own tests
    # and the real-bundle CLI check; a fixed independent expected result catches
    # attempts to pass mutated admission into this consumer.
    expected = deepcopy(admission)
    monkeypatch.setattr(module, "build_evidence_admission", lambda *a, **k: deepcopy(expected))
    return baseline, admission, assets


def run(values):
    return project_evidence_assets(
        *values, exact_patch="7.42", source_refs={}, engineering_evidence={}, documents={}
    )


def test_fact_promotion_does_not_invent_block_reflect_or_restore_legacy_counts(inputs):
    original = deepcopy(inputs)
    result = run(inputs)
    facts = result["profiles"]["heroes"]["hero"]["abilities"]
    assert facts[0]["facts"][0]["candidate_usable"] is True
    for rule in result["counter_graph"]["rules"]:
        node = rule["targets"][0]
        assert node["candidate_usable"] is False
        assert node["evidence_constraints"][0]["engineering_admission"]["conditions"] == {
            "target_scope": "enemy_nonhero",
            "requires_shard": True,
            "can_multiply": False,
        }
    assert all(
        not e["candidate_usable"] and e["status"] == "pending"
        for e in result["counter_graph"]["item_to_hero"]
    )
    count = result["hero_traits"]["traits"]["t"]["counts"][0]
    assert count["base"] is count["with_upgrades"] is None
    detail = result["hero_traits"]["traits"]["t"]["heroes"][0]
    assert detail["ability_count"] is None
    assert detail["abilities"][0]["evidence_constraints"]
    assert detail["abilities"][0]["baseline_evidence_only"] is True
    assert result["summary"]["newly_usable_graph_edges"] == 0
    assert result["summary"]["newly_blocked_graph_edges"] == 1
    assert inputs == original
    facts[0]["facts"][0]["engineering_admission"]["conditions"].clear()
    assert inputs == original
    assert result["counter_graph"]["rules"][0]["targets"][0]["evidence_constraints"][0][
        "engineering_admission"
    ]["conditions"]


@pytest.mark.parametrize(
    "damage",
    [
        "copy",
        "missing_profile",
        "duplicate_profile",
        "wrong_subject",
        "extra_edge",
        "edge_closure",
        "wrong_sources",
        "save_changed",
        "profile_owner",
        "node_owner",
        "edge_owner",
        "trait_owner",
    ],
)
def test_derived_identity_and_completeness_fail_closed(inputs, damage):
    assets = inputs[2]
    profiles = assets["profiles"]["heroes"]["hero"]["abilities"]
    if damage == "copy":
        profiles[0]["facts"][0]["condition"]["requires_scepter"] = True
    elif damage == "missing_profile":
        profiles.pop()
    elif damage == "duplicate_profile":
        profiles.append(deepcopy(profiles[0]))
    elif damage == "wrong_subject":
        profiles[0]["ability"] = "unrelated"
    elif damage == "extra_edge":
        assets["counter_graph"]["item_to_hero"][0]["abilities"].append("absent")
    elif damage == "edge_closure":
        assets["counter_graph"]["item_to_hero"][0]["fact_ids"] = []
    elif damage == "wrong_sources":
        assets["hero_traits"]["source_refs"] = {"forged": {}}
    elif damage == "save_changed":
        assets["save_means"]["means"] = {"impossible": {"facts": [deepcopy(inputs[0]["rows"][0])]}}
    elif damage == "profile_owner":
        assets["profiles"]["heroes"]["hero"]["hero_id"] = 99999
    elif damage == "node_owner":
        assets["counter_graph"]["rules"][0]["targets"][0]["hero_id"] = 99999
    elif damage == "edge_owner":
        assets["counter_graph"]["item_to_hero"][0]["hero_id"] = 99999
    elif damage == "trait_owner":
        assets["hero_traits"]["traits"]["t"]["heroes"][0]["hero_id"] = 99999
    with pytest.raises(ValueError):
        run(inputs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("subject", "imposter"),
        ("basis", "user:NEW"),
        ("user_approved_for_patch", True),
        ("decision", "reject"),
    ],
)
def test_new_admission_cannot_change_existing_identity_or_user_ruling(inputs, field, value):
    inputs[1]["rows"][0][field] = value
    with pytest.raises(ValueError):
        run(inputs)


def test_same_recovery_effect_is_grouped_without_claiming_executed_event_count(inputs, monkeypatch):
    old = inputs[0]["rows"]
    new = inputs[1]["rows"]
    for key, mechanism in (("lifesteal", "lifesteal"), ("healing", "healing")):
        row = fact(key, usable=True, mechanism=mechanism)
        row["subject"] = "infest"
        old.append(row)
        revised = deepcopy(row)
        revised["engineering_admission"] = {
            "conditions": {"duration": 3},
            "effect_identity": "infest:open_wounds:recovery",
            "unproven_capabilities": [],
        }
        new.append(revised)
    inputs[2]["profiles"]["other_subjects"]["infest"] = deepcopy(old[-2:])
    expected = deepcopy(inputs[1])
    monkeypatch.setattr(module, "build_evidence_admission", lambda *a, **k: deepcopy(expected))
    groups = run(inputs)["capabilities"]["groups"]
    recovery = [g for g in groups if g["subject"] == "infest"]
    assert len(recovery) == 1
    assert recovery[0]["mechanisms"] == ["healing", "lifesteal"]
    assert recovery[0]["event_count_inferred"] is False
    assert recovery[0]["conditions_evaluated"] is False


def test_unrelated_pending_row_cannot_be_promoted_with_forged_engineering_metadata(inputs):
    inputs[1]["rows"][2]["engineering_admission"] = {
        "conditions": {},
        "unproven_capabilities": [],
        "effect_identity": "forged",
    }
    with pytest.raises(ValueError, match="reconstruction"):
        run(inputs)


def test_forged_baseline_fingerprint_is_rejected(inputs):
    inputs[1]["baseline_document_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="reconstruction"):
        run(inputs)


@pytest.mark.parametrize("field,value", [("requires_shard", 1), ("can_multiply", 0)])
def test_integer_alias_cannot_replace_boolean_in_recomputed_conditions(inputs, field, value):
    inputs[1]["rows"][0]["engineering_admission"]["conditions"][field] = value
    with pytest.raises(ValueError, match="reconstruction"):
        run(inputs)


def test_derived_fact_copy_requires_exact_json_types(inputs):
    inputs[2]["profiles"]["heroes"]["hero"]["abilities"][0]["facts"][0]["candidate_usable"] = 0
    with pytest.raises(ValueError, match="fact copy"):
        run(inputs)


@pytest.mark.parametrize("field,value", [("hero_id", True), ("candidate_usable", 0)])
def test_graph_identity_and_eligibility_reject_boolean_integer_aliases(inputs, field, value):
    inputs[2]["counter_graph"]["rules"][0]["targets"][0][field] = value
    with pytest.raises(ValueError):
        run(inputs)
