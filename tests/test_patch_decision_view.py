"""An as-of projection cannot reveal hidden targets or later completed packets."""

from copy import deepcopy

import pytest

from dota_items.data.patch_decision_view import VisionDecisionIndex
from dota_items.data.patch_vision_evidence import STATE_COLUMNS

REF = {"path": "/diagnostic/capture.json", "sha256": "a" * 64}
COL = {key: index for index, key in enumerate(STATE_COLUMNS)}


def capture():
    specs = [
        (65, 2, "CDOTA_Unit_Hero_Friendly"),
        (66, 2, "CDOTA_Unit_Hero_Enemy"),
        (70, 3, "CDOTA_BaseNPC_Creep_Neutral"),
        (130, 4, "CDOTA_BaseNPC_Tower"),
        (2, 1, "CDOTA_DataRadiant"),
        (3, 1, "CDOTA_DataDire"),
        (71, 1, "CDOTA_TempTree"),
        (72, 1, "CDOTA_BaseNPC_Creep_Neutral"),
        (73, 1, "CDOTA_BaseNPC_Creep_Neutral"),
        (74, 1, "CDOTA_BaseNPC_Creep_Neutral"),
    ]
    catalog = [
        {
            "entity_index": index,
            "entity_serial": serial,
            "class_name": cls,
            "first_seen_tick": 0,
            "npc_name_first_seen": f"first_seen_{index}",
        }
        for index, serial, cls in specs
    ]
    states = [
        [eid, 100 + eid, 200 + eid, True, team, life, hp, waiting, 1800, 800, None, 0, 123456, 999]
        for eid, team, life, hp, waiting in [
            (0, 2, 0, 800, False),
            (1, 3, 0, 700, False),
            (2, 4, 0, 500, False),
            (3, 3, 0, 2000, False),
            (6, None, None, None, None),
            (7, 4, 0, 500, True),
            (8, 4, 2, 0, False),
            (9, 4, 0, 500, None),
        ]
    ]
    # The later friendly state must not overwrite the earlier HP.
    states.append([*states[0]])
    states[-1][COL["health"]] = 50
    first_word = sum(1 << bit for bit in (1, 6, 7, 8, 9, 10))
    frames = []
    for t, tick, time, word, state_ids in [
        (0, 30, 0.75, 0, list(range(8))),
        (1, 60, 1.25, 2, [8, *range(1, 8)]),
    ]:
        frames.append(
            {
                "t": t,
                "tick": tick,
                "game_time": time,
                "entity_state_ids": state_ids,
                "canonical_heroes": [[0, 0, 2 * 16384 + 65], [5, 1, 2 * 16384 + 66]],
                "team_word_refs": {
                    "radiant": {"entity_id": 4, "snapshot_id": word},
                    "dire": {"entity_id": 5, "snapshot_id": 1},
                },
                "tree_word_refs": {"radiant": {"entity_id": 4, "snapshot_id": 0}},
                "tree_model_replacements_raw": {},
                "rules_raw": {"future_sensitive_rule": t},
            }
        )
    return {
        "schema": "map-vision-evidence/1",
        "patch": "7.42",
        "coordinate_space": "world",
        "omniscient": True,
        "training_allowed": False,
        "action_review_allowed": False,
        "match_id": 123,
        "game_build": 6993,
        "post_game_tick": 90,
        "parse_error": None,
        "truncated_at_tick": None,
        "state_columns": list(STATE_COLUMNS),
        "entity_catalog": catalog,
        "states": states,
        "team_word_snapshots": [
            [[1, first_word], [2, 4]],
            [[1, 4 | 64], [2, 0]],
            [[1, first_word | 4], [2, 4]],
        ],
        "tree_word_snapshots": [[0, 1]],
        "temporary_tree_events": [],
        "frames": frames,
        "field_schemas": {
            cls: {
                "is_networked_npc_schema": (
                    cls not in ("CDOTA_DataRadiant", "CDOTA_DataDire", "CDOTA_TempTree")
                )
            }
            for _, _, cls in specs
        },
        "sampling": {"boundary": "completed_packet", "end_game_time": 2.3},
    }


def index(doc=None):
    return VisionDecisionIndex(
        capture() if doc is None else doc, exact_patch="7.42", source_ref=REF
    )


def at(idx, **changes):
    query = {"game_time": 0.75, "replay_tick": 30, "observer_team": 2, "max_age_seconds": 0}
    return idx.at(**(query | changes))


def ids(view):
    return [
        (row["identity"]["entity_index"], row["identity"]["entity_serial"])
        for row in view["visible_entities"]
    ]


def test_whitelist_preserves_friendly_hp_but_no_other_health_or_omniscient_fields():
    result = at(index())
    view = result["known_view"]
    assert view["friendly_heroes"] == [
        {
            "player_id": 0,
            "status": "observed",
            "identity": {"entity_index": 65, "entity_serial": 2},
            "class_name": "CDOTA_Unit_Hero_Friendly",
            "npc_name": "first_seen_65",
            "team": 2,
            "position": {"x": 100, "y": 200},
            "observed_state": {"life_state": 0, "health": 800},
            "unknown_fields": [],
        }
    ]
    assert ids(view) == [(70, 3), (130, 4)]
    for row in view["visible_entities"]:
        assert set(row) == {
            "identity",
            "class_name",
            "npc_name",
            "team",
            "position",
            "unknown_fields",
        }
    assert set(view) == {
        "observer_team",
        "requested_game_time",
        "requested_replay_tick",
        "max_age_seconds",
        "observation",
        "friendly_roster_complete",
        "friendly_roster_unknown_reason",
        "friendly_heroes",
        "visible_entities",
    }
    assert result["training_allowed"] is result["action_review_allowed"] is False
    assert set(result["provenance"]) == {
        "source_ref",
        "capture_canonical_sha256",
        "match_id",
        "game_build",
    }


def test_actual_time_prevents_looking_forward_inside_the_same_floor_second():
    idx = index()
    early = at(idx, game_time=0.5, replay_tick=90, max_age_seconds=100)["known_view"]
    assert early["observation"]["status"] == "unknown"
    assert early["friendly_heroes"] == early["visible_entities"] == []
    later = at(idx, game_time=1.1, replay_tick=90, max_age_seconds=1)["known_view"]
    assert later["observation"]["game_time"] == 0.75
    assert later["observation"]["tick"] == 30
    assert later["friendly_heroes"][0]["observed_state"]["health"] == 800
    assert (66, 2) not in ids(later)


def test_both_time_and_tick_bounds_are_required_and_pause_age_does_not_mean_current():
    idx = index()
    before_tick = at(idx, replay_tick=29, max_age_seconds=100)["known_view"]
    assert before_tick["observation"]["status"] == "unknown"
    held = at(idx, game_time=1.25, replay_tick=59, max_age_seconds=1)["known_view"]
    assert held["observation"]["tick"] == 30
    assert held["observation"]["age_seconds"] == 0.5
    paused = at(idx, replay_tick=59)["known_view"]["observation"]
    assert paused["age_seconds"] == 0
    assert paused["age_replay_ticks"] == 29
    assert paused["exact_tick_match"] is False
    with pytest.raises(TypeError):
        idx.at(game_time=0.75, observer_team=2, max_age_seconds=0)


def test_stale_observation_never_carries_entities_as_current():
    result = at(index(), game_time=1.2, replay_tick=59, max_age_seconds=0.1)["known_view"]
    assert result["observation"]["reason"] == "stale_observation"
    assert result["observation"]["age_seconds"] == pytest.approx(0.45)
    assert result["friendly_heroes"] == result["visible_entities"] == []


@pytest.mark.parametrize(
    "query",
    [
        {"game_time": 2.3001, "replay_tick": 90},
        {"game_time": 2.3, "replay_tick": 91},
    ],
)
def test_outside_match_coverage_cannot_reuse_a_tail_frame_even_with_large_age_budget(query):
    view = at(index(), max_age_seconds=1000, **query)["known_view"]
    assert view["observation"]["reason"] == "outside_replay_coverage"
    assert view["observation"]["status"] == "unknown"
    assert view["observation"]["game_time"] is None
    assert view["friendly_heroes"] == view["visible_entities"] == []


def test_unknown_final_clock_does_not_certify_a_decision_time_inside_replay_coverage():
    doc = capture()
    doc["sampling"]["end_game_time"] = None
    view = at(index(doc))["known_view"]
    assert view["observation"]["reason"] == "replay_time_coverage_unknown"
    assert view["friendly_heroes"] == view["visible_entities"] == []


@pytest.mark.parametrize("missing", ["canonical", "state"])
def test_missing_friendly_binding_never_claims_a_complete_roster(missing):
    doc = capture()
    if missing == "canonical":
        doc["frames"][0]["canonical_heroes"] = [doc["frames"][0]["canonical_heroes"][1]]
    else:
        doc["frames"][0]["entity_state_ids"].remove(0)
    view = at(index(doc))["known_view"]
    assert view["friendly_heroes"] == []
    assert view["friendly_roster_complete"] is False
    assert view["friendly_roster_unknown_reason"] == "complete_friendly_roster_not_certified"


@pytest.mark.parametrize("missing", ["canonical", "state"])
def test_missing_hidden_enemy_evidence_does_not_change_roster_completeness_or_known_view(missing):
    doc = capture()
    before = at(index(doc))["known_view"]
    if missing == "canonical":
        doc["frames"][0]["canonical_heroes"] = [doc["frames"][0]["canonical_heroes"][0]]
    else:
        doc["frames"][0]["entity_state_ids"].remove(1)
    assert at(index(doc))["known_view"] == before


def test_future_valid_states_catalog_and_global_rules_do_not_change_earlier_known_view():
    original = capture()
    altered = deepcopy(original)
    future = {
        "entity_index": 1000,
        "entity_serial": 8,
        "class_name": "CDOTA_BaseNPC_Creep_Neutral",
        "first_seen_tick": 70,
        "npc_name_first_seen": "future_only_secret",
    }
    altered["entity_catalog"].append(future)
    altered["states"].append([10, 9999, -9999, True, 4, 0, 123, False, 500, 500, None, 0, 0, 0])
    altered["frames"][1]["entity_state_ids"].append(9)
    altered["frames"][1].update(game_time=1.8, tick=80)
    altered["frames"][1]["rules_raw"] = {"future_sensitive_rule": 12345}
    altered["states"][8][COL["health"]] = 999
    altered["tree_word_snapshots"][0] = [123, None]
    before, after = at(index(original)), at(index(altered))
    assert before["known_view"] == after["known_view"]
    assert (
        before["provenance"]["capture_canonical_sha256"]
        != (after["provenance"]["capture_canonical_sha256"])
    )


def test_hidden_enemy_perturbations_never_leak_identity_health_position_or_count():
    original = capture()
    hidden = deepcopy(original)
    hidden["states"][1][COL["x"]] = -9999
    hidden["states"][1][COL["y"]] = 9876
    hidden["states"][1][COL["health"]] = 1
    hidden["states"][1][COL["owner_handle"]] = 987654
    hidden["states"][1][COL["unit_state_raw"]] = 987654321
    hidden["entity_catalog"][1]["npc_name_first_seen"] = "secret_hidden_identity"
    # Add another currently hidden NPC: even its existence must not appear in the view.
    hidden["entity_catalog"].append(
        {
            "entity_index": 75,
            "entity_serial": 20,
            "class_name": "CDOTA_BaseNPC_Creep_Neutral",
            "first_seen_tick": 0,
            "npc_name_first_seen": "secret_hidden_addition",
        }
    )
    hidden["states"].append([10, 5, 6, True, 4, 0, 500, False, 500, 500, None, 0, 0, 0])
    hidden["frames"][0]["entity_state_ids"].append(9)
    assert at(index(original))["known_view"] == at(index(hidden))["known_view"]


def test_reindexing_all_internal_pools_cannot_change_feature_view_or_expose_row_ids():
    doc = capture()
    old = at(index(doc))["known_view"]
    entity_count = len(doc["entity_catalog"])
    state_count = len(doc["states"])
    word_count = len(doc["team_word_snapshots"])
    doc["entity_catalog"].reverse()
    for row in doc["states"]:
        row[0] = entity_count - 1 - row[0]
    doc["states"].reverse()
    doc["team_word_snapshots"].reverse()
    for frame in doc["frames"]:
        frame["entity_state_ids"] = [state_count - 1 - i for i in frame["entity_state_ids"]]
        for hero in frame["canonical_heroes"]:
            hero[1] = entity_count - 1 - hero[1]
        for ref in frame["team_word_refs"].values():
            ref["entity_id"] = entity_count - 1 - ref["entity_id"]
            ref["snapshot_id"] = word_count - 1 - ref["snapshot_id"]
        for ref in frame["tree_word_refs"].values():
            ref["entity_id"] = entity_count - 1 - ref["entity_id"]
    assert at(index(doc))["known_view"] == old


def test_serial_reuse_is_not_a_visibility_or_identity_continuation():
    doc = capture()
    doc["team_word_snapshots"][0][0][1] |= 4
    doc["entity_catalog"].append(
        {
            "entity_index": 66,
            "entity_serial": 9,
            "class_name": "CDOTA_Unit_Hero_Enemy",
            "first_seen_tick": 60,
            "npc_name_first_seen": "new_incarnation",
        }
    )
    doc["states"].append([10, 400, 600, True, 3, 0, 100, False, 1800, 800, None, 0, 0, 0])
    doc["frames"][1]["entity_state_ids"][1] = 9
    doc["frames"][1]["canonical_heroes"][1] = [5, 10, 9 * 16384 + 66]
    idx = index(doc)
    assert (66, 2) in ids(at(idx)["known_view"])
    later = at(idx, game_time=1.25, replay_tick=60)["known_view"]
    assert (66, 9) in ids(later) and (66, 2) not in ids(later)


def test_hidden_again_entity_is_not_carried_from_an_earlier_visible_frame():
    doc = capture()
    doc["team_word_snapshots"][0][0][1] |= 4
    doc["team_word_snapshots"][2][0][1] &= ~4
    idx = index(doc)
    assert (66, 2) in ids(at(idx)["known_view"])
    assert (66, 2) not in ids(at(idx, game_time=1.25, replay_tick=60)["known_view"])


@pytest.mark.parametrize("word", [0, None])
def test_missing_or_false_word_never_creates_an_unverified_friendly_slot(word):
    doc = capture()
    doc["team_word_snapshots"][0][0][1] = word
    view = at(index(doc))["known_view"]
    assert view["friendly_heroes"] == []
    assert view["friendly_roster_complete"] is False
    assert view["friendly_roster_unknown_reason"] == "complete_friendly_roster_not_certified"
    assert (65, 2) not in ids(view)
    assert (70, 3) not in ids(view)


@pytest.mark.parametrize("life", [1, 2])
def test_non_live_friendly_retains_raw_hp_life_without_position(life):
    doc = capture()
    doc["states"][0][COL["life_state"]] = life
    doc["states"][0][COL["health"]] = 0
    row = at(index(doc))["known_view"]["friendly_heroes"][0]
    assert row["observed_state"] == {"health": 0, "life_state": life}
    assert row["position"] is None and "position" in row["unknown_fields"]


@pytest.mark.parametrize("waiting", [True, None])
def test_waiting_and_missing_spawn_evidence_do_not_create_friendly_slots(waiting):
    doc = capture()
    doc["states"][0][COL["waiting_to_spawn"]] = waiting
    view = at(index(doc))["known_view"]
    assert view["friendly_heroes"] == []
    assert view["friendly_roster_complete"] is False


@pytest.mark.parametrize("mutation", ["team", "class", "membership", "slot", "combined"])
@pytest.mark.parametrize("missing_word", [False, True])
def test_hidden_canonical_team_class_and_membership_never_change_known_view(mutation, missing_word):
    doc = capture()
    if missing_word:
        doc["team_word_snapshots"][0][0][1] = None
    before = at(index(doc))["known_view"]
    if mutation in ("team", "combined"):
        doc["states"][1][COL["team"]] = 2
    if mutation in ("class", "combined"):
        name = "CDOTA_Unit_Hero_HiddenAlternative"
        doc["entity_catalog"][1]["class_name"] = name
        doc["field_schemas"][name] = {"is_networked_npc_schema": True}
    if mutation in ("membership", "combined"):
        doc["frames"][0]["canonical_heroes"].pop()
    if mutation == "slot":
        doc["frames"][0]["canonical_heroes"][1][0] = 6
    assert at(index(doc))["known_view"] == before


def test_hidden_raw_friendly_membership_does_not_reveal_a_slot_either():
    doc = capture()
    doc["team_word_snapshots"][0][0][1] &= ~(1 << 1)
    before = at(index(doc))["known_view"]
    assert before["friendly_heroes"] == []
    doc["frames"][0]["canonical_heroes"].pop(0)
    assert at(index(doc))["known_view"] == before


@pytest.mark.parametrize("waiting", [True, None])
def test_visible_but_not_known_spawned_canonical_team_cannot_create_a_friendly_slot(waiting):
    doc = capture()
    doc["team_word_snapshots"][0][0][1] |= 4
    doc["states"][1][COL["waiting_to_spawn"]] = waiting
    before = at(index(doc))["known_view"]
    doc["states"][1][COL["team"]] = 2
    assert at(index(doc))["known_view"] == before


def test_unverified_npc_schema_does_not_create_friendly_metadata():
    doc = capture()
    doc["field_schemas"]["CDOTA_Unit_Hero_Friendly"]["is_networked_npc_schema"] = False
    view = at(index(doc))["known_view"]
    assert view["friendly_heroes"] == []
    assert (65, 2) not in ids(view)
    assert view["friendly_roster_complete"] is False


def test_missing_life_or_coordinates_stay_unknown_not_origin_or_alive():
    doc = capture()
    doc["states"][0][COL["life_state"]] = None
    doc["states"][0][COL["health"]] = None
    doc["states"][2][COL["x"]] = doc["states"][2][COL["y"]] = None
    view = at(index(doc))["known_view"]
    assert view["friendly_heroes"][0]["observed_state"] == {"life_state": None, "health": None}
    assert view["friendly_heroes"][0]["unknown_fields"] == ["life_state", "health", "position"]
    neutral = next(r for r in view["visible_entities"] if r["identity"]["entity_index"] == 70)
    assert neutral["position"] is None and neutral["unknown_fields"] == ["position"]


def test_observer_team_switch_does_not_reuse_other_teams_visibility_or_canonical_slots():
    view = at(index(), observer_team=3)["known_view"]
    assert [r["player_id"] for r in view["friendly_heroes"]] == [5]
    assert view["friendly_heroes"][0]["observed_state"]["health"] == 700
    assert (65, 2) not in ids(view)


def test_empty_or_only_pregame_frames_do_not_supply_post_horn_observation():
    doc = capture()
    doc["frames"] = []
    assert at(index(doc))["known_view"]["observation"]["status"] == "unknown"
    doc = capture()
    doc["frames"] = [doc["frames"][0]]
    doc["frames"][0].update(t=-1, game_time=-0.1)
    assert at(index(doc), max_age_seconds=100)["known_view"]["observation"]["status"] == "unknown"


def test_input_and_return_mutations_do_not_change_existing_index():
    doc = capture()
    before = deepcopy(doc)
    idx = index(doc)
    baseline = at(idx)
    assert doc == before
    doc["states"][0][COL["health"]] = 1
    doc["entity_catalog"][0]["npc_name_first_seen"] = "changed"
    doc["team_word_snapshots"][0][0][1] = 0
    result = at(idx)
    result["known_view"]["friendly_heroes"][0]["identity"]["entity_index"] = 999
    result["provenance"]["source_ref"]["path"] = "/changed"
    assert at(idx) == baseline


@pytest.mark.parametrize(
    "change",
    [
        {"game_time": -1},
        {"game_time": True},
        {"game_time": float("nan")},
        {"game_time": float("inf")},
        {"replay_tick": 30.0},
        {"replay_tick": -1},
        {"replay_tick": True},
        {"observer_team": 1},
        {"observer_team": 2.0},
        {"observer_team": True},
        {"max_age_seconds": -1},
        {"max_age_seconds": False},
        {"max_age_seconds": float("inf")},
    ],
)
def test_query_parameters_are_explicit_finite_and_strictly_typed(change):
    with pytest.raises(ValueError):
        at(index(), **change)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(patch="7.41f"),
        lambda d: d.update(omniscient=False),
        lambda d: d.update(training_allowed=True),
        lambda d: d.update(action_review_allowed=True),
        lambda d: d["sampling"].update(boundary="pre_tick"),
        lambda d: d["frames"][1].update(tick=91),
        lambda d: d["frames"][1]["canonical_heroes"][1].__setitem__(2, 66),
        lambda d: d["frames"][1]["entity_state_ids"].append(999),
        lambda d: d.update(field_schemas=None),
    ],
)
def test_complete_capture_validation_rejects_bad_version_boundary_or_future_structure(mutate):
    doc = capture()
    mutate(doc)
    with pytest.raises(ValueError):
        index(doc)


def test_source_reference_and_exact_patch_are_required_without_filesystem_access():
    with pytest.raises(ValueError):
        VisionDecisionIndex(capture(), exact_patch="7.42a", source_ref=REF)
    for ref in (
        {"path": "relative", "sha256": "a" * 64},
        {"path": "/capture.json", "sha256": "bad"},
        {**REF, "extra": 1},
    ):
        with pytest.raises(ValueError):
            VisionDecisionIndex(capture(), exact_patch="7.42", source_ref=ref)
    assert at(index())["provenance"]["source_ref"] == REF  # The nonexistent path is not opened.
