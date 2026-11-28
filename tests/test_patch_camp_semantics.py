"""Current origin evidence stays separate from historical amphibian cohort hypotheses."""

import copy
import json

import pytest

from dota_items.data.patch_camp_semantics import build_camp_semantics

PREFIX = "npc_dota_neutral_"
HISTORY = {
    "8": "Every 5 minutes one of the creeps in that camp will be forever upgraded to a next tier",
    "9": (
        "Each camp consists of 3 units. As a result, at 15:00 Easy camp completely turns into a "
        "Medium camp, and both Medium camps will become Hard ones. At 30:00 Medium camp will "
        "become a Hard one, and both Hard camps will evolve to Ancient ones"
    ),
    "10": (
        "Each creep can only be upgraded twice, meaning an Easy camp will never reach an "
        "Ancient status (sorry, Pollywogs)"
    ),
    "11": (
        "Units are not upgraded if the camp is blocked. Amount of upgraded units can't be "
        "increased, so if there is only 1 Ancient creep, attempting to stack that camp will "
        "not create another Ancient creep"
    ),
    "13": "Easy camp is three Pollywogs ",
    "14": "Medium camp is two Boglets and a Marshmage Apprentice ",
    "15": "Hard camp is two Croakers and a Marshmage ",
    "16": "Ancient camp is two Ancient Croakers and an Ancient Marshmage ",
}
NAMES = {
    "tadpole": "Pollywog",
    "froglet": "Boglet",
    "froglet_mage": "Marshmage Apprentice",
    "grown_frog": "Croaker",
    "grown_frog_mage": "Marshmage",
    "ancient_frog": "Ancient Croaker",
    "ancient_frog_mage": "Ancient Marshmage",
}


def _text(values):
    return "\n".join(f"{json.dumps(key)} {json.dumps(value)}" for key, value in values.items())


def _official():
    rows = [{} for _ in range(16)]
    notes = [{} for _ in range(15)]
    notes[14] = {"note": "Large camps: Large Satyr camp; Hellbear camp; Dark Troll camp"}
    rows[0] = {"neutral_creep_notes": notes}
    rows[15] = {
        "name": PREFIX + "dark_troll",
        "localized_name": "Dark Troll Trapper",
        "neutral_creep_notes": [
            {
                "note": "Hill Troll (from Dark Troll camp) renamed to Dark Troll Trapper",
            }
        ],
    }
    return {"success": True, "patch_name": "7.42", "patch_number": "7.42", "neutral_creeps": rows}


def _row(index, name="tadpole", *, tick=1801, waiting=False, life=0, serial=1):
    return {
        "entity_index": index,
        "entity_serial": serial,
        "tick": tick,
        "game_time": tick / 30,
        "active": True,
        "op": "updated",
        "npc_name": PREFIX + name if name is not None else None,
        "npc_name_table": "UnitNames",
        "spawner_identity": [1, 1],
        "raw_fields": {
            "m_lifeState": life,
            "m_bIsWaitingToSpawn": waiting,
            "m_hNeutralSpawner": (1 << 14) | 1,
            "m_Type": 0,
        },
    }


def _unit(index, name="tadpole", *, tick=1801):
    return {
        "entity_index": index,
        "entity_serial": 1,
        "created_tick": 0,
        "observations": [_row(index, name, tick=0, waiting=True), _row(index, name, tick=tick)],
    }


def _inputs(names=("tadpole", "tadpole", "tadpole")):
    spawner = _row(1, tick=0)
    changed = _row(1, tick=27001)
    changed["raw_fields"]["m_Type"] = 1
    cap = {
        "schema": "map-runtime-capture/1",
        "patch": "7.42",
        "match_id": 101,
        "game_build": 6993,
        "post_game_tick": 60000,
        "parse_error": None,
        "truncated_at_tick": None,
        "training_allowed": False,
        "omniscient": True,
        "coordinate_space": "world",
        "spawners": [{"entity_index": 1, "entity_serial": 1, "observations": [spawner, changed]}],
        "neutral_units": [_unit(i + 2, name) for i, name in enumerate(names)],
    }
    camp = {
        "camp_id": "neutralcamp_good_11",
        "type": None,
        "runtime_spawners": [
            {
                "match_id": 101,
                "identity": [1, 1],
                "raw_type_timeline": [
                    {
                        "tick": row["tick"],
                        "game_time": row["game_time"],
                        "fields": {"m_Type": row["raw_fields"]["m_Type"]},
                        "pointer": f"/spawners/0/observations/{i}",
                    }
                    for i, row in enumerate((spawner, changed))
                ],
            }
        ],
        "activation_batches": [],
    }
    camp["activation_batches"].append(_batch(cap, list(range(len(names)))))
    asset = {
        "schema": "patch-camp-assets/1",
        "exact_patch": "7.42",
        "training_allowed": False,
        "action_review_allowed": False,
        "camps": [camp],
        "match_ids": [101],
    }
    return asset, cap


def _batch(cap, indexes):
    units = []
    for i in indexes:
        record = cap["neutral_units"][i]
        index = next(
            j
            for j, row in enumerate(record["observations"])
            if row["raw_fields"]["m_bIsWaitingToSpawn"] is False
            and row["raw_fields"]["m_lifeState"] == 0
        )
        row = record["observations"][index]
        prior = record["observations"][index - 1] if index else None
        units.append(
            {
                "entity": [row["entity_index"], row["entity_serial"]],
                "npc_name": row["npc_name"],
                "game_time": row["game_time"],
                "pointer": f"/neutral_units/{i}/observations/{index}",
                "left_censored": prior is None,
                "last_waiting_tick": prior["tick"] if prior else None,
                "last_waiting_game_time": prior["game_time"] if prior else None,
            }
        )
    return {
        "match_id": 101,
        "tick": row["tick"],
        "game_time": row["game_time"],
        "units": units,
        "any_left_censored_unit": any(u["left_censored"] for u in units),
    }


def _build(asset, cap, *, official=None, history=None, localization=None):
    return build_camp_semantics(
        asset,
        [cap] if isinstance(cap, dict) else cap,
        official or _official(),
        _text({"DOTA_Patch_7_38_Flooded_Camps_" + k: v for k, v in HISTORY.items()})
        if history is None
        else history,
        _text({PREFIX + k: v for k, v in NAMES.items()}) if localization is None else localization,
        exact_patch="7.42",
        source_refs={"verified_inputs": "caller receipt"},
    )


def _observation(result):
    return result["camps"][0]["historical_composition_observations"][0]


@pytest.mark.parametrize(
    "names,tier",
    [
        (("tadpole",) * 3, "easy"),
        (("froglet", "froglet", "froglet_mage"), "medium"),
        (("grown_frog", "grown_frog", "grown_frog_mage"), "hard"),
        (("ancient_frog", "ancient_frog", "ancient_frog_mage"), "ancient"),
    ],
)
def test_complete_cohort_has_historical_hypothesis_without_current_type_or_approval(names, tier):
    result = _build(*_inputs(names))
    camp, observation = result["camps"][0], _observation(result)
    assert observation["cohort_status"] == "fully_observed_activation_cohort"
    assert observation["historical_tier_candidate"] == tier
    assert observation["historical_status"] == "historical_unverified_for_patch"
    assert observation["spawn_completeness_verified"] is False
    assert camp["current_patch_type_candidate"] is None
    assert camp["full_742_evolution_rule_verified"] is False
    assert camp["control_team"] is camp["strategic_region"] is None
    assert result["summary"]["current_patch_type_candidates"] == 0
    assert result["summary"]["formal_type_approved_camps"] == 0
    assert result["training_allowed"] is result["action_review_allowed"] is False


def test_raw_transition_keeps_float_time_and_does_not_decode_enum():
    result = _build(*_inputs())
    camp = result["camps"][0]
    assert camp["dynamic_composition_candidate"] is False
    transition = camp["raw_type_transitions"][0]
    assert transition["game_time"] == 900 + 1 / 30
    assert transition["from_raw_type"] == 0
    assert transition["to_raw_type"] == 1
    assert transition["type_enum_interpretation_verified"] is False
    assert camp["historical_initial_tier_candidate"] == "easy"


def test_dynamic_composition_needs_actual_complete_cohort_change_and_raw_type_change():
    asset, cap = _inputs()
    for record in cap["neutral_units"]:
        record["observations"].append(_row(record["entity_index"], tick=18000, life=1))
    cap["neutral_units"].extend(
        [
            _unit(5, "froglet", tick=27002),
            _unit(6, "froglet", tick=27002),
            _unit(7, "froglet_mage", tick=27002),
        ]
    )
    asset["camps"][0]["activation_batches"].append(_batch(cap, [3, 4, 5]))
    assert _build(asset, cap)["camps"][0]["dynamic_composition_candidate"] is True
    asset["camps"][0]["activation_batches"][1]["units"].pop()
    assert _build(asset, cap)["camps"][0]["dynamic_composition_candidate"] is False


def _anchor(asset, cap, camp_id, label, raw_type):
    index = len(cap["spawners"])
    identity = 100 + index
    row = _row(identity, tick=0)
    row["spawner_identity"] = [identity, 1]
    row["raw_fields"]["m_hNeutralSpawner"] = (1 << 14) | identity
    row["raw_fields"]["m_Type"] = raw_type
    cap["spawners"].append({"entity_index": identity, "entity_serial": 1, "observations": [row]})
    asset["camps"].append(
        {
            "camp_id": camp_id,
            "type": label,
            "activation_batches": [],
            "runtime_spawners": [
                {
                    "match_id": 101,
                    "identity": [identity, 1],
                    "raw_type_timeline": [
                        {
                            "tick": 0,
                            "game_time": 0.0,
                            "fields": {"m_Type": raw_type},
                            "pointer": f"/spawners/{index}/observations/0",
                        }
                    ],
                }
            ],
        }
    )


def test_empirical_mapping_uses_distinct_current_camps_and_preserves_timeline():
    asset, cap = _inputs()
    for number, label, value in [
        (1, "small", 0),
        (2, "small", 0),
        (3, "medium", 1),
        (4, "medium", 1),
    ]:
        _anchor(asset, cap, f"anchor_{number}", label, value)
    result = _build(asset, cap)
    calibration = result["observed_enum_calibration"][0]
    assert calibration["distinct_anchor_camps"] == 4
    assert calibration["authoritative_enum"] is False
    assert calibration["game_build"] == 6993
    for mapping in calibration["values"]:
        assert mapping["distinct_anchor_camps"] == 2
        assert all(check["agrees_with_excluded_camp"] for check in mapping["leave_one_camp_out"])
        assert all(
            check["remaining_distinct_anchor_camps"] == 1 for check in mapping["leave_one_camp_out"]
        )
        assert all(
            row["type_evidence_document"] == "camp_assets" for row in mapping["anchor_evidence"]
        )
    camp = result["camps"][0]
    assert [row["empirical_type_candidate"] for row in camp["empirical_type_timeline"]] == [
        "small",
        "medium",
    ]
    assert camp["current_patch_type_candidate"] is None
    assert result["summary"]["unknown_static_type_with_empirical_phase_candidates"] == 1


def test_repeated_matches_never_count_as_two_independent_anchor_camps():
    asset, cap = _inputs()
    _anchor(asset, cap, "one_anchor", "small", 0)
    second = copy.deepcopy(cap)
    second["match_id"] = 102
    asset["match_ids"].append(102)
    for camp in asset["camps"]:
        entry = copy.deepcopy(camp["runtime_spawners"][0])
        entry["match_id"] = 102
        camp["runtime_spawners"].append(entry)
    result = _build(asset, [cap, second])
    mapping = result["observed_enum_calibration"][0]["values"][0]
    assert mapping["distinct_anchor_camps"] == 1
    assert mapping["observation_count"] == 2
    assert mapping["type_candidate"] is None
    assert mapping["status"] == "insufficient_distinct_anchor_camps"


def test_enum_calibration_never_crosses_game_builds():
    asset, cap = _inputs()
    _anchor(asset, cap, "small_1", "small", 0)
    _anchor(asset, cap, "small_2", "small", 0)
    second = copy.deepcopy(cap)
    second.update(match_id=102, game_build=7000)
    asset["match_ids"].append(102)
    entry = copy.deepcopy(asset["camps"][0]["runtime_spawners"][0])
    entry["match_id"] = 102
    asset["camps"][0]["runtime_spawners"].append(entry)
    result = _build(asset, [cap, second])
    timeline = result["camps"][0]["empirical_type_timeline"]
    assert timeline[0]["empirical_type_candidate"] == "small"
    assert all(
        row["empirical_type_candidate"] is None for row in timeline if row["game_build"] == 7000
    )
    assert result["observed_enum_calibration"][1]["values"] == []


@pytest.mark.parametrize(
    "raw_types,labels",
    [
        ((0, 0), ("small", "medium")),
        ((0, 1), ("small", "small")),
    ],
)
def test_conflicting_and_inverse_ambiguous_enum_anchors_never_map(raw_types, labels):
    asset, cap = _inputs()
    for number, (raw_type, label) in enumerate(zip(raw_types, labels, strict=True)):
        _anchor(asset, cap, f"anchor_{number}", label, raw_type)
    result = _build(asset, cap)
    assert all(
        row["status"] == "conflicting_anchor_evidence" and row["type_candidate"] is None
        for row in result["observed_enum_calibration"][0]["values"]
    )


def test_missing_raw_type_is_unknown_not_a_transition_or_mapped_enum():
    asset, cap = _inputs()
    cap["spawners"][0]["observations"][1]["raw_fields"]["m_Type"] = None
    asset["camps"][0]["runtime_spawners"][0]["raw_type_timeline"][1]["fields"]["m_Type"] = None
    camp = _build(asset, cap)["camps"][0]
    assert camp["raw_type_transitions"] == []
    assert camp["empirical_type_timeline"][1]["status"] == "unknown_value_for_build"


def test_single_dark_troll_supports_official_origin_but_not_complete_spawn():
    result = _build(*_inputs(("dark_troll",)))
    camp = result["camps"][0]
    assert camp["current_patch_type_candidate"] == "large"
    assert camp["current_patch_type_status"] == "new_direct_official_origin_candidate"
    assert camp["direct_origin_evidence"]["origin_pointer"] == (
        "/neutral_creeps/15/neutral_creep_notes/0"
    )
    assert result["summary"]["new_direct_current_patch_type_candidates"] == 1
    assert result["user_approved"] is False


@pytest.mark.parametrize("change", ["fuzzy_name", "changed_note", "changed_localized_name"])
def test_direct_origin_requires_all_exact_current_source_fields(change):
    asset, cap = _inputs(("dark_troll",))
    official = _official()
    if change == "fuzzy_name":
        for row in cap["neutral_units"][0]["observations"]:
            row["npc_name"] = PREFIX + "dark_troll_warlord"
        asset["camps"][0]["activation_batches"] = [_batch(cap, [0])]
    elif change == "changed_note":
        official["neutral_creeps"][15]["neutral_creep_notes"][0]["note"] += " changed"
    else:
        official["neutral_creeps"][15]["localized_name"] = "Dark Troll"
    assert _build(asset, cap, official=official)["camps"][0]["current_patch_type_candidate"] is None


def test_direct_origin_conflict_stays_unknown():
    asset, cap = _inputs(("dark_troll",))
    asset["camps"][0]["type"] = "medium"
    camp = _build(asset, cap)["camps"][0]
    assert camp["current_patch_type_candidate"] is None
    assert camp["current_patch_type_status"] == "conflicting_direct_evidence"


@pytest.mark.parametrize("source", ["history", "localization"])
def test_missing_historical_or_name_proof_cannot_assign_historical_label(source):
    result = _build(*_inputs(), **{source: ""})
    assert _observation(result)["historical_tier_candidate"] is None


def test_mixed_upgrade_tiers_remain_mixed_without_majority_label():
    result = _build(*_inputs(("tadpole", "tadpole", "froglet")))
    observation = _observation(result)
    assert observation["composition_status"] == "mixed_historical_tiers"
    assert observation["tier_counts"] == {"easy": 2, "medium": 1}
    assert observation["historical_tier_candidate"] is None


@pytest.mark.parametrize("names", [("tadpole",) * 2, ("tadpole",) * 4])
def test_partial_and_stacked_counts_cannot_claim_complete_composition(names):
    observation = _observation(_build(*_inputs(names)))
    assert "not_three_distinct_observed_activations" in observation["limitations"]
    assert observation["historical_tier_candidate"] is None


def test_omitted_raw_activation_cannot_turn_four_into_a_three_unit_cohort():
    asset, cap = _inputs(("tadpole",) * 4)
    asset["camps"][0]["activation_batches"][0]["units"].pop()
    observation = _observation(_build(asset, cap))
    assert "activation_batch_omits_or_adds_original_entities" in observation["limitations"]
    assert observation["historical_tier_candidate"] is None


def test_same_game_second_different_ticks_are_not_one_complete_refresh():
    asset, cap = _inputs()
    cap["neutral_units"].append(_unit(5, tick=1802))
    observation = _observation(_build(asset, cap))
    assert "same_second_activations_span_multiple_raw_ticks" in observation["limitations"]
    assert observation["historical_tier_candidate"] is None


def test_unassociated_same_second_unit_makes_cohort_ambiguous():
    asset, cap = _inputs()
    extra = _unit(5)
    for row in extra["observations"]:
        row["spawner_identity"] = None
    cap["neutral_units"].append(extra)
    observation = _observation(_build(asset, cap))
    assert "unassociated_activation_in_same_game_second" in observation["limitations"]
    assert observation["historical_tier_candidate"] is None


@pytest.mark.parametrize("last_state", ["alive", "unknown", "same_tick_death"])
def test_preexisting_survivors_or_unknowns_cannot_be_ignored(last_state):
    asset, cap = _inputs()
    extra = _unit(5, tick=900)
    if last_state == "unknown":
        extra["observations"].append(_row(5, tick=1200, life=None, waiting=None))
    elif last_state == "same_tick_death":
        extra["observations"].append(_row(5, tick=1801, life=1))
    cap["neutral_units"].append(extra)
    observation = _observation(_build(asset, cap))
    assert observation["cohort_status"] == "incomplete_or_ambiguous"
    assert observation["historical_tier_candidate"] is None


def test_known_earlier_death_does_not_make_new_cohort_stacked():
    asset, cap = _inputs()
    extra = _unit(5, tick=900)
    extra["observations"].append(_row(5, tick=1200, life=1))
    cap["neutral_units"].append(extra)
    assert _observation(_build(asset, cap))["cohort_status"] == "fully_observed_activation_cohort"


@pytest.mark.parametrize("change", ["missing_waiting", "left_censored", "same_tick_waiting"])
def test_no_observed_waiting_transition_never_claims_complete_cohort(change):
    asset, cap = _inputs()
    if change == "missing_waiting":
        cap["neutral_units"][0]["observations"][0]["raw_fields"]["m_bIsWaitingToSpawn"] = None
    elif change == "left_censored":
        asset["camps"][0]["activation_batches"][0]["units"][0]["left_censored"] = True
    else:
        cap["neutral_units"][0]["observations"][0]["tick"] = 1801
    observation = _observation(_build(asset, cap))
    assert "missing_observed_precreation_waiting_to_active_transition" in observation["limitations"]
    assert observation["historical_tier_candidate"] is None


def test_missing_unit_name_is_preserved_and_blocks_composition_label():
    asset, cap = _inputs(("tadpole", "tadpole", None))
    observation = _observation(_build(asset, cap))
    assert observation["unknown_name_count"] == 1
    assert observation["composition_status"] == "unknown_unit_or_localization"


@pytest.mark.parametrize("change", ["serial", "pointer", "table", "waiting_time", "type"])
def test_derived_evidence_cannot_override_original_source(change):
    asset, cap = _inputs()
    unit = asset["camps"][0]["activation_batches"][0]["units"][0]
    if change == "serial":
        cap["neutral_units"][0]["observations"][1]["raw_fields"]["m_hNeutralSpawner"] = 32769
    elif change == "pointer":
        unit["pointer"] = "/neutral_units/1/observations/1"
    elif change == "table":
        cap["neutral_units"][0]["observations"][1]["npc_name_table"] = "EntityNames"
    elif change == "waiting_time":
        unit["last_waiting_game_time"] = -1
    else:
        asset["camps"][0]["runtime_spawners"][0]["raw_type_timeline"][0]["fields"]["m_Type"] = 4
    with pytest.raises(ValueError):
        _build(asset, cap)


def test_one_spawner_cannot_supply_two_distinct_camp_ids():
    asset, cap = _inputs()
    second = copy.deepcopy(asset["camps"][0])
    second["camp_id"] = "neutralcamp_evil_14"
    asset["camps"].append(second)
    with pytest.raises(ValueError, match="two camps"):
        _build(asset, cap)


@pytest.mark.parametrize(
    "field,value",
    [
        ("patch", "7.42a"),
        ("training_allowed", True),
        ("omniscient", False),
        ("post_game_tick", None),
        ("truncated_at_tick", 33),
        ("parse_error", "bad"),
    ],
)
def test_runtime_scope_and_completeness_are_required(field, value):
    asset, cap = _inputs()
    cap[field] = value
    with pytest.raises(ValueError, match="identity, purpose or completeness"):
        _build(asset, cap)


def test_sources_are_not_mutated_and_missing_current_type_stays_unknown():
    asset, cap = _inputs()
    before = copy.deepcopy((asset, cap))
    result = _build(asset, cap)
    assert (asset, cap) == before
    assert result["summary"]["current_patch_type_unknown"] == 1
    assert result["historical_rules"]["thirty_minute_evolution_verified"] is False
    assert result["historical_rules"]["blocking_rule_verified"] is False
