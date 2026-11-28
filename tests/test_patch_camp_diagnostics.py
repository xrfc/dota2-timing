"""Raw association failures and post-hoc camp phases never become prior knowledge."""

import copy

import pytest
from test_patch_objectives import capture, documents, record, row

from dota_items.data.patch_camp_diagnostics import build_camp_diagnostics
from dota_items.data.patch_objectives import build_camp_assets


def _unit(index=2, *, handle=0xFFFFFF, association=None, name="npc_dota_neutral_mud_golem_split"):
    value = row(index=index, tick=1800, spawner_identity=association, npc_name=name)
    value["npc_name_table"] = "UnitNames"
    value["raw_fields"]["m_hNeutralSpawner"] = handle
    value["raw_fields"].update(m_iTeamNum=4, m_bIsNeutralUnitType=True)
    return record([value])


def _inputs(cap=None, docs=None):
    cap = cap or capture()
    cap["sampling"]["end_game_time"] = 2000.0
    if not cap["neutral_units"]:
        cap["neutral_units"] = [_unit()]
    asset = build_camp_assets(
        docs or documents(), [cap], exact_patch="7.42", source_refs={"capture": "caller-verified"}
    )
    semantic = {
        "schema": "patch-camp-semantics/1",
        "exact_patch": "7.42",
        "training_allowed": False,
        "action_review_allowed": False,
        "match_ids": asset["match_ids"],
        "camps": [
            {"camp_id": camp["camp_id"], "dynamic_composition_candidate": True}
            for camp in asset["camps"]
        ],
    }
    return asset, semantic, cap


def _build(asset, semantic, cap):
    return build_camp_diagnostics(
        asset, semantic, [cap], exact_patch="7.42", source_refs={"caller": "verified references"}
    )


def _diagnostic(result):
    return result["unresolved_unit_diagnostics"][0]


def test_invalid_sentinel_explains_unresolved_without_excluding_or_assigning_summoner():
    result = _build(*_inputs())
    unit = _diagnostic(result)
    assert unit["reason"] == "invalid_handle_sentinel"
    assert unit["first_active_pointer"] == "/neutral_units/0/observations/0"
    assert unit["decoded_target"] is unit["referenced_spawner_geometry"] is None
    assert unit["npc_name"] == "npc_dota_neutral_mud_golem_split"
    assert unit["mechanistic_origin"]["summoned"] is None
    assert unit["mechanistic_origin"]["controlled"] is None
    assert result["summary"]["automatically_excluded_units"] == 0
    assert result["player_prior_knowledge"] is result["training_allowed"] is False


@pytest.mark.parametrize(
    "handle,reason",
    [
        (None, "missing_handle_value"),
        (0xFFFFFFFF, "invalid_handle_sentinel"),
        (-1, "handle_out_of_range"),
        (1 << 40, "handle_out_of_range"),
        (0, "referenced_spawner_not_captured"),
    ],
)
def test_missing_invalid_and_zero_encoded_handles_remain_distinct(handle, reason):
    cap = capture()
    cap["neutral_units"] = [_unit(handle=handle)]
    assert _diagnostic(_build(*_inputs(cap)))["reason"] == reason


def test_absent_handle_field_is_not_confused_with_explicit_null():
    asset, semantic, cap = _inputs()
    cap["neutral_units"][0]["observations"][0]["raw_fields"].pop("m_hNeutralSpawner")
    result = _build(asset, semantic, cap)
    assert _diagnostic(result)["reason"] == "handle_field_missing"
    assert _diagnostic(result)["handle_field_present"] is False


def test_same_index_other_serial_never_resolves_to_old_spawner():
    cap = capture()
    cap["neutral_units"] = [_unit(handle=(2 << 14) | 1)]
    unit = _diagnostic(_build(*_inputs(cap)))
    assert unit["reason"] == "referenced_spawner_not_captured"
    assert unit["decoded_target"] == [1, 2]
    assert unit["same_index_other_serials"] == [[1, 1]]


def test_existing_target_does_not_override_original_unresolved_handle():
    cap = capture()
    cap["neutral_units"] = [_unit(handle=(1 << 14) | 1)]
    result = _build(*_inputs(cap))
    unit = _diagnostic(result)
    assert unit["reason"] == "handle_target_observed_but_unresolved"
    assert unit["referenced_spawner_geometry"]["camp_id"] == "neutralcamp_good_1"
    assert unit["resolved_spawner_identity"] is None
    assert result["summary"]["unresolved_active_units"] == 1


def test_spawner_outside_all_triggers_cannot_be_resolved_by_nearest_camp():
    cap = capture()
    cap["spawners"][0]["observations"][0].update(x=101.0, y=50.0)
    cap["neutral_units"] = [_unit(handle=(1 << 14) | 1, association=[1, 1])]
    result = _build(*_inputs(cap))
    assert _diagnostic(result)["reason"] == "no_unique_static_trigger"
    assert _diagnostic(result)["referenced_spawner_geometry"]["status"] == (
        "spawner_outside_static_triggers"
    )
    assert result["summary"]["unresolved_spawners"] == 1


@pytest.mark.parametrize("condition", ["missing_coordinates", "crossing"])
def test_invalid_spawner_geometry_is_reported_from_all_observations(condition):
    cap = capture()
    cap["neutral_units"] = [_unit(handle=(1 << 14) | 1, association=[1, 1])]
    if condition == "missing_coordinates":
        cap["spawners"][0]["observations"][0].update(x=None, y=None)
    else:
        cap["spawners"][0]["observations"].append(row(tick=300, x=200, y=200))
    result = _build(*_inputs(cap))
    assert result["summary"]["unresolved_spawners"] == 1
    assert _diagnostic(result)["referenced_spawner_geometry"]["camp_id"] is None


def test_team_and_exact_skeleton_name_are_identity_evidence_not_control_proof():
    cap = capture()
    cap["neutral_units"] = [_unit(name="npc_dota_wraith_king_skeleton_warrior")]
    cap["neutral_units"][0]["observations"][0]["raw_fields"]["m_iTeamNum"] = 2
    cap["neutral_units"][0]["observations"][0]["player_id_primary"] = 3
    unit = _diagnostic(_build(*_inputs(cap)))
    assert unit["identity_state_observations"][0]["raw_team"] == 2
    assert unit["identity_state_observations"][0]["player_id_primary"] == 3
    assert unit["mechanistic_origin"]["status"] == "unproven"


def _dynamic():
    cap = capture()
    changed = row(tick=27001)
    changed["raw_fields"]["m_Type"] = 1
    cap["spawners"][0]["observations"].append(changed)
    waiting = row(index=2, tick=0, waiting=True)
    alive = row(index=2, tick=27001)
    for value in (waiting, alive):
        value["npc_name"] = "npc_dota_neutral_tadpole"
        value["npc_name_table"] = "UnitNames"
    cap["neutral_units"] = [record([waiting, alive])]
    return _inputs(cap)


def test_boundary_reports_actual_transition_waiting_and_alive_as_posthoc_states():
    result = _build(*_dynamic())
    boundary = result["dynamic_boundary_diagnostics"][0]
    assert boundary["boundary_seconds"] == 900.0
    assert boundary["raw_transition_status"] == "transition_observed"
    assert boundary["raw_transitions"][0]["game_time"] == 27001 / 30
    assert boundary["before"]["lifecycle_state_counts"] == {"waiting": 1}
    assert boundary["after"]["lifecycle_state_counts"] == {"alive": 1}
    assert boundary["after"]["alive_name_counts"] == {"npc_dota_neutral_tadpole": 1}
    assert boundary["activation_batches_in_window"][0]["unit_count"] == 1
    assert boundary["activation_batches_in_window"][0]["complete_spawn_verified"] is False
    assert boundary["cause_status"] == "unproven"
    assert boundary["spawn_blocked"] is None
    assert boundary["player_prior_knowledge"] is False


def test_no_30m_change_is_not_a_blocked_camp_or_failed_timer():
    result = _build(*_dynamic())
    boundary = result["dynamic_boundary_diagnostics"][1]
    assert boundary["raw_transition_status"] == "no_transition_observed_in_window"
    assert boundary["window_coverage"] == "window_reached"
    assert boundary["spawn_blocked"] is None
    assert boundary["permanent_stage_rule_verified"] is False


def test_replay_end_before_boundary_never_invents_observation_or_zero_occupancy():
    asset, semantic, cap = _dynamic()
    cap["sampling"]["end_game_time"] = 1200.0
    boundary = _build(asset, semantic, cap)["dynamic_boundary_diagnostics"][1]
    assert boundary["raw_transition_status"] == "window_not_reached"
    assert boundary["after"]["status"] == "beyond_replay_end"
    assert boundary["after"]["lifecycle_state_counts"] is None


def test_unknown_lifecycle_field_stays_unknown_at_boundary():
    asset, semantic, cap = _dynamic()
    cap["neutral_units"][0]["observations"].insert(1, row(index=2, tick=26970, waiting=None))
    # The original activation pointer changes when the source list changes.
    asset, semantic, cap = _inputs(cap)
    before = _build(asset, semantic, cap)["dynamic_boundary_diagnostics"][0]["before"]
    assert before["lifecycle_state_counts"] == {"unknown_activation_state": 1}
    assert before["alive_name_counts"] == {}


def test_future_spawner_association_is_not_backfilled_into_prior_state():
    asset, semantic, cap = _dynamic()
    first = cap["neutral_units"][0]["observations"][0]
    first["spawner_identity"] = None
    first["raw_fields"]["m_hNeutralSpawner"] = 0xFFFFFF
    asset, semantic, cap = _inputs(cap)
    boundary = _build(asset, semantic, cap)["dynamic_boundary_diagnostics"][0]
    assert boundary["before"]["observations"] == []
    assert boundary["after"]["lifecycle_state_counts"] == {"alive": 1}


@pytest.mark.parametrize("changed", ["timeline", "unit_name", "pointer", "omitted_unresolved"])
def test_derived_assets_cannot_substitute_for_original_capture(changed):
    asset, semantic, cap = _dynamic() if changed != "omitted_unresolved" else _inputs()
    if changed == "timeline":
        asset["camps"][0]["runtime_spawners"][0]["raw_type_timeline"][0]["fields"]["m_Type"] = 7
    elif changed == "unit_name":
        asset["camps"][0]["activation_batches"][0]["units"][0]["npc_name"] = "fake"
    elif changed == "pointer":
        asset["camps"][0]["activation_batches"][0]["units"][0]["pointer"] = "/spawners/0"
    else:
        asset["unresolved_associations"].clear()
    with pytest.raises(ValueError):
        _build(asset, semantic, cap)


def test_crossserial_resolved_association_is_rejected():
    asset, semantic, cap = _inputs()
    row = cap["neutral_units"][0]["observations"][0]
    row["raw_fields"]["m_hNeutralSpawner"] = (2 << 14) | 1
    row["spawner_identity"] = [1, 1]
    with pytest.raises(ValueError, match="contradicts"):
        _build(asset, semantic, cap)


@pytest.mark.parametrize(
    "field,value",
    [
        ("patch", "7.42a"),
        ("training_allowed", True),
        ("omniscient", False),
        ("post_game_tick", None),
        ("parse_error", "partial"),
    ],
)
def test_wrong_patch_purpose_or_incomplete_capture_is_rejected(field, value):
    asset, semantic, cap = _inputs()
    cap[field] = value
    with pytest.raises(ValueError, match="completion mismatch"):
        _build(asset, semantic, cap)


def test_objective_capture_schema_and_input_immutability():
    asset, semantic, cap = _inputs()
    cap["schema"] = "map-objective-evidence/1"
    previous = copy.deepcopy((asset, semantic, cap))
    assert _build(asset, semantic, cap)["summary"]["unresolved_active_units"] == 1
    assert (asset, semantic, cap) == previous


def test_overlapping_trigger_membership_remains_ambiguous():
    docs = documents()
    data = docs["mapdata.json"]["data"]
    second = copy.deepcopy(data["trigger_multiple"][0])
    second["name"] = "neutralcamp_evil_1"
    for i in range(1, 5):
        second[str(i)]["x"] += 75
    data["trigger_multiple"].append(second)
    data["npc_dota_neutral_spawner"] = [{"x": 25, "y": 50}, {"x": 150, "y": 50}]
    cap = capture()
    cap["spawners"][0]["observations"][0]["x"] = 85
    cap["neutral_units"] = [_unit(handle=(1 << 14) | 1, association=[1, 1])]
    result = _build(*_inputs(cap, docs))
    geometry = _diagnostic(result)["referenced_spawner_geometry"]
    assert geometry["status"] == "static_trigger_not_unique"
    assert geometry["observations"][0]["containing_camp_ids"] == [
        "neutralcamp_good_1",
        "neutralcamp_evil_1",
    ]


def test_missing_time_after_known_state_cannot_certify_boundary_composition():
    asset, semantic, cap = _dynamic()
    cap["neutral_units"][0]["observations"].append(row(index=2, tick=27500, life=1, game_time=None))
    asset, semantic, cap = _inputs(cap)
    after = _build(asset, semantic, cap)["dynamic_boundary_diagnostics"][0]["after"]
    assert after["lifecycle_state_counts"] == {"unknown_boundary_state_time": 1}
    assert after["alive_name_counts"] == {}
    assert after["unknown_time_pointers"] == ["/neutral_units/0/observations/2"]


def test_missing_spawner_type_is_not_evidence_of_no_change():
    asset, semantic, cap = _dynamic()
    for observed in cap["spawners"][0]["observations"]:
        observed["raw_fields"]["m_Type"] = None
    asset, semantic, cap = _inputs(cap)
    boundary = _build(asset, semantic, cap)["dynamic_boundary_diagnostics"][0]
    assert boundary["raw_transition_status"] == "insufficient_spawner_observation"


@pytest.mark.parametrize("change", ["omit_batch", "repeat_batch", "repeat_semantic_camp"])
def test_derived_batch_and_camp_coverage_cannot_be_omitted_or_duplicated(change):
    asset, semantic, cap = _dynamic()
    if change == "omit_batch":
        asset["camps"][0]["activation_batches"].clear()
    elif change == "repeat_batch":
        asset["camps"][0]["activation_batches"] *= 2
    else:
        semantic["camps"] *= 2
    with pytest.raises(ValueError):
        _build(asset, semantic, cap)
