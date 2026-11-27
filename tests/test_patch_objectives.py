"""Semantic provenance, missing evidence and dynamic objective bounds."""

import copy

import pytest

from dota_items.data.patch_objectives import (
    build_camp_assets,
    build_objective_observations,
    build_objective_rules,
)

REFS = [{"path": "/caller/verified/source.json", "sha256": "a" * 64}]
KWARGS = {"exact_patch": "7.42", "source_refs": REFS}


def documents():
    return {
        "mapdata.json": {
            "data": {
                "trigger_multiple": [
                    {
                        "name": "neutralcamp_good_1",
                        "1": {"x": 0, "y": 0},
                        "2": {"x": 100, "y": 0},
                        "3": {"x": 100, "y": 100},
                        "4": {"x": 0, "y": 100},
                    }
                ],
                "npc_dota_neutral_spawner": [{"x": 50, "y": 50}],
            }
        }
    }


def row(index=1, serial=1, tick=0, waiting=False, life=0, **overrides):
    return {
        "entity_index": index,
        "entity_serial": serial,
        "tick": tick,
        "game_time": tick / 30,
        "active": True,
        "op": "observed",
        "x": 50.0,
        "y": 50.0,
        "npc_name": "npc_dota_neutral_radigull",
        "spawner_identity": [1, 1],
        "raw_fields": {
            "m_bIsWaitingToSpawn": waiting,
            "m_lifeState": life,
            "m_Type": 0,
            "m_hNeutralSpawner": (1 << 14) | 1,
        },
        **overrides,
    }


def record(rows, kind="neutral_unit"):
    return {
        "entity_index": rows[0]["entity_index"],
        "entity_serial": rows[0]["entity_serial"],
        "kind": kind,
        "observations": rows,
    }


def capture():
    return {
        "schema": "map-runtime-capture/1",
        "patch": "7.42",
        "match_id": 123,
        "game_build": 6993,
        "post_game_tick": 60000,
        "parse_error": None,
        "truncated_at_tick": None,
        "training_allowed": False,
        "omniscient": True,
        "coordinate_space": "world",
        "spawners": [record([row()], "spawner")],
        "neutral_units": [],
        "objectives": [],
        "objective_frames": [],
        "sampling": {"end_game_time": 2000.0},
    }


def official():
    rows = [{"note": "unused"} for _ in range(25)]
    for index, text in {
        8: "Small camps: Kobold camp; Hill Troll Berserker and Kobold camp; Hill Troll camp",
        9: "Medium camps: Wolf camp; Ogre camp; Radigull camp (new!)",
        10: "Large camps: Centaur camp; Wildwing camp; Eimermole camp (new!)",
        12: "Small camps: Vhoul camp; Ghost camp; Harpy camp",
        13: "Medium camps: Satyr camp; Golem camp; Odobenus camp (new!)",
        14: "Large camps: Large Satyr camp; Hellbear camp; Dark Troll camp",
    }.items():
        rows[index] = {"note": text}
    rows[21] = {
        "note": "Added a Radigull camp: New Medium camp for Radiant",
        "info": "Each camp consists of 2 Radigulls",
    }
    rows[22] = {
        "note": "Added an Odobenus camp: New Medium camp for Dire",
        "info": "Each camp consists of 1 Odobenus Frostmage and 2 Odobenus Footmen",
    }
    rows[23] = {
        "note": "Added an Eimermole camp: New Large camp for Radiant",
        "info": "Each camp consists of 1 Eimermole Foreman and 1 Eimermole",
    }
    rows[24] = {
        "note": "Added an Ancient Ogre Seal camp: New Ancient camp",
        "info": "Each camp consists of 1 Ancient Ogre Seal and 2 Ancient Ogre Seal Pups",
    }
    units = [
        ("radigull", "Radigull"),
        ("odobenus_frostmage", "Odobenus Frostmage"),
        ("odobenus_footman", "Odobenus Footman"),
        ("eimermole_foreman", "Eimermole Foreman"),
        ("eimermole", "Eimermole"),
        ("ogre_seal", "Ancient Ogre Seal"),
        ("ogre_seal_pup", "Ancient Ogre Seal Pup"),
        ("kobold", "Kobold"),
        ("ghost", "Ghost"),
        ("ogre_mauler", "Ogre Bruiser"),
    ]
    objectives = [{"note": "unused"} for _ in range(12)]
    objectives[1] = {"note": "Initial spawn time decreased from 20:00 to 15:00"}
    objectives[11] = {
        "note": (
            "Base respawn timer now decreases by 1 minute every time Roshan is defeated, "
            "to a minimum of 5 minutes"
        )
    }
    return {
        "success": True,
        "patch_number": "7.42",
        "patch_name": "7.42",
        "neutral_creeps": [{"neutral_creep_notes": rows}]
        + [{"name": "npc_dota_neutral_" + name, "localized_name": label} for name, label in units],
        "general_notes": [{}, {}, {"title": "Map Objectives", "generic": objectives}],
    }


def test_camp_type_uses_real_association_and_official_composition_never_death_position():
    cap = capture()
    cap["neutral_units"] = [
        record(
            [
                row(index=2, waiting=True),
                row(index=2, tick=1800, x=2000),
                row(index=2, tick=2400, life=1, x=5000),
            ]
        )
    ]
    result = build_camp_assets(documents(), [cap], official_notes=official(), **KWARGS)
    camp = result["camps"][0]
    assert camp["type"] == "medium"
    assert camp["source_side_token"] == "good"
    assert camp["control_team"] is camp["strategic_region"] is None
    assert camp["type_evidence"][0]["note_pointer"] == "/neutral_creeps/0/neutral_creep_notes/21"
    batch = camp["activation_batches"][0]
    assert batch["tick"] == 1800
    assert batch["units"][0]["last_waiting_game_time"] == 0
    assert batch["units"][0]["left_censored"] is False
    assert result["action_review_allowed"] is False


def test_zero_spawner_enum_and_unknown_units_never_inherit_old_types():
    cap = capture()
    cap["neutral_units"] = [record([row(index=2, npc_name="npc_dota_neutral_ogre_mauler")])]
    camp = build_camp_assets(documents(), [cap], official_notes=official(), **KWARGS)["camps"][0]
    assert camp["type"] is None
    assert camp["raw_spawner_types"] == [{"field": "m_Type", "value": 0}]
    assert camp["observed_units"] == {"npc_dota_neutral_ogre_mauler": 1}


def test_exact_camp_and_localized_unit_name_adds_evidence_without_fuzzy_family_match():
    cap = capture()
    cap["neutral_units"] = [record([row(index=2, npc_name="npc_dota_neutral_ghost")])]
    camp = build_camp_assets(documents(), [cap], official_notes=official(), **KWARGS)["camps"][0]
    assert camp["type"] == "small"
    assert camp["type_evidence"][0]["method"] == "camp_name_equals_localized_unit_name"
    assert camp["type_evidence"][0]["note_pointer"] == "/neutral_creeps/0/neutral_creep_notes/12"


def test_missing_association_does_not_fall_back_to_creep_coordinates():
    cap = capture()
    cap["neutral_units"] = [record([row(index=2, spawner_identity=None)])]
    result = build_camp_assets(documents(), [cap], official_notes=official(), **KWARGS)
    assert result["camps"][0]["type"] is None
    assert result["unresolved_associations"][0]["reason"] == "no_resolved_spawner_trigger"


def test_conflicting_observed_official_types_stay_unknown():
    cap = capture()
    cap["neutral_units"] = [
        record([row(index=2)]),
        record([row(index=3, npc_name="npc_dota_neutral_eimermole")]),
    ]
    camp = build_camp_assets(documents(), [cap], official_notes=official(), **KWARGS)["camps"][0]
    assert camp["type"] is None
    assert camp["type_status"] == "conflicting_evidence"


def test_dynamic_raw_spawner_type_timeline_is_not_collapsed_into_a_static_semantic_type():
    cap = capture()
    changed = row(tick=18000)
    changed["raw_fields"]["m_Type"] = 1
    cap["spawners"][0]["observations"].append(changed)
    camp = build_camp_assets(documents(), [cap], **KWARGS)["camps"][0]
    assert camp["type"] is None
    timeline = camp["runtime_spawners"][0]["raw_type_timeline"]
    assert [r["fields"]["m_Type"] for r in timeline] == [0, 1]
    assert timeline[1]["game_time"] == 600
    assert timeline[1]["pointer"] == "/spawners/0/observations/1"


@pytest.mark.parametrize("change", ["wrong_channel", "boolean_life", "frame_time", "backwards"])
def test_malformed_runtime_evidence_is_rejected(change):
    cap = capture()
    if change == "wrong_channel":
        cap["spawners"][0]["kind"] = "roshan"
    elif change == "boolean_life":
        cap["spawners"][0]["observations"][0]["raw_fields"]["m_lifeState"] = False
    elif change == "frame_time":
        cap["objective_frames"] = [
            {
                "tick": 30,
                "game_time": 100,
                "roshan": [row(tick=30)],
                "tormentor": [],
            }
        ]
    else:
        cap["spawners"][0]["observations"] = [row(tick=30), row()]
    with pytest.raises(ValueError):
        build_camp_assets(documents(), [cap], **KWARGS)


@pytest.mark.parametrize("mutation", ["duplicate", "overlap", "missing", "irregular"])
def test_camp_geometry_requires_unique_rectangles_and_spawners(mutation):
    docs = documents()
    data = docs["mapdata.json"]["data"]
    if mutation in ("duplicate", "overlap"):
        data["trigger_multiple"].append(copy.deepcopy(data["trigger_multiple"][0]))
        if mutation == "overlap":
            data["trigger_multiple"][1]["name"] = "neutralcamp_evil_1"
    elif mutation == "missing":
        data["npc_dota_neutral_spawner"] = []
    else:
        data["trigger_multiple"][0]["1"]["x"] = 12
    with pytest.raises(ValueError):
        build_camp_assets(docs, [capture()], **KWARGS)


def test_tormentor_initial_presence_bounded_by_empty_frame_and_missing_respawn_is_unknown():
    cap = capture()
    unit = row(index=2, tick=27000)
    cap["objectives"] = [record([unit], "tormentor")]
    cap["objective_frames"] = [
        {"tick": 26970, "game_time": 899.0, "roshan": [], "tormentor": []},
        {"tick": 27030, "game_time": 901.0, "roshan": [], "tormentor": [row(index=2, tick=27030)]},
    ]
    data = build_objective_observations([cap], **KWARGS)["matches"][0]["objectives"]
    interval = data["tormentor"]["activation_observations"][0]
    assert interval["lower_game_time"] == 899
    assert interval["upper_game_time"] == 900
    assert data["tormentor"]["frame_coverage"] == {"absent": 1, "alive": 1}
    assert data["roshan"]["respawn_status"] == "no_positive_sample"


@pytest.mark.parametrize(
    "waiting,life,status",
    [
        (None, 0, "unknown_activation_state"),
        (False, None, "unknown_activation_state"),
        (True, 0, "waiting_only"),
        (False, 1, "non_alive_only"),
    ],
)
def test_nonactive_unit_records_remain_distinct_from_zero_observations(waiting, life, status):
    cap = capture()
    cap["neutral_units"] = [record([row(index=2, waiting=waiting, life=life)])]
    result = build_camp_assets(documents(), [cap], **KWARGS)
    assert result["summary"]["observed_unit_records"] == 1
    assert result["summary"]["unit_record_coverage"] == {status: 1}
    assert result["camps"][0]["unit_record_coverage"] == {status: 1}
    missing = result["unit_records_without_active_observation"][0]
    assert missing["pointer"] == "/neutral_units/0"
    assert missing["camp_id"] == "neutralcamp_good_1"


@pytest.mark.parametrize("handle", [None, (2 << 14) | 1, 0xFFFFFF, 0xFFFFFFFF])
def test_resolved_spawner_must_match_raw_handle_including_serial(handle):
    cap = capture()
    unit = row(index=2)
    unit["raw_fields"]["m_hNeutralSpawner"] = handle
    cap["neutral_units"] = [record([unit])]
    with pytest.raises(ValueError, match="handle"):
        build_camp_assets(documents(), [cap], **KWARGS)


def test_latest_waiting_and_alive_frames_tighten_lifecycle_bounds():
    cap = capture()
    cap["objectives"] = [
        record(
            [
                row(waiting=True),
                row(tick=27000),
                row(tick=27300, life=1),
            ],
            "roshan",
        )
    ]
    cap["objective_frames"] = [
        {
            "tick": 26970,
            "game_time": 899.0,
            "tormentor": [],
            "roshan": [row(tick=26970, waiting=True)],
        },
        {"tick": 27270, "game_time": 909.0, "tormentor": [], "roshan": [row(tick=27270)]},
    ]
    result = build_objective_observations([cap], **KWARGS)["matches"][0]["objectives"]["roshan"]
    assert result["activation_observations"][0]["lower_game_time"] == 899
    assert result["death_observations"][0]["lower_game_time"] == 909


def test_pre_update_empty_frame_at_event_tick_is_valid_lower_observation_boundary():
    cap = capture()
    cap["objectives"] = [record([row(tick=30)], "tormentor")]
    cap["objective_frames"] = [{"tick": 30, "game_time": 1.0, "tormentor": [], "roshan": []}]
    interval = build_objective_observations([cap], **KWARGS)["matches"][0]["objectives"][
        "tormentor"
    ]["activation_observations"][0]
    assert interval["lower_tick"] == interval["upper_tick"] == 30
    assert interval["lower_observation_boundary"] == "before_current_tick_entity_deltas"
    assert interval["upper_observation_boundary"] == "after_entity_delta"


def test_waiting_precreation_and_deletion_do_not_establish_spawn_or_death():
    cap = capture()
    cap["objectives"] = [
        record(
            [
                row(waiting=True),
                row(tick=1800),
                row(tick=2400, op="deleted"),
            ],
            "roshan",
        )
    ]
    result = build_objective_observations([cap], **KWARGS)["matches"][0]["objectives"]["roshan"]
    assert result["activation_observations"][0]["upper_game_time"] == 60
    assert result["death_observations"] == []
    assert result["respawn_status"] == "no_positive_sample"


def test_reentry_and_other_serial_cannot_serve_as_confirmed_respawn():
    cap = capture()
    cap["objectives"] = [
        record(
            [
                row(),
                row(tick=30, op="left"),
                row(tick=60),
                row(tick=90, life=1),
            ],
            "roshan",
        ),
        record([row(serial=2, tick=120)], "roshan"),
    ]
    result = build_objective_observations([cap], **KWARGS)["matches"][0]["objectives"]["roshan"]
    assert len(result["activation_observations"]) == 2
    assert len(result["death_observations"]) == 1
    assert result["respawn_status"] == "no_positive_sample"


def test_observed_death_then_same_entity_activation_is_retained_with_interval():
    cap = capture()
    cap["objectives"] = [
        record(
            [
                row(),
                row(tick=300, life=1),
                row(tick=600),
            ],
            "roshan",
        )
    ]
    result = build_objective_observations([cap], **KWARGS)["matches"][0]["objectives"]["roshan"]
    assert result["respawn_status"] == "observed_interval"
    assert result["death_to_next_activation_observations"][0]["death"]["upper_game_time"] == 10


@pytest.mark.parametrize(
    "field,value",
    [
        ("patch", "7.42a"),
        ("training_allowed", True),
        ("omniscient", False),
        ("post_game_tick", None),
        ("parse_error", "failed"),
        ("match_id", True),
    ],
)
def test_runtime_identity_or_purpose_mismatch_rejected(field, value):
    cap = capture()
    cap[field] = value
    with pytest.raises(ValueError):
        build_objective_observations([cap], **KWARGS)


def test_duplicate_replays_and_entity_serial_mismatch_rejected():
    with pytest.raises(ValueError, match="identity"):
        build_objective_observations([capture(), capture()], **KWARGS)
    cap = capture()
    cap["spawners"][0]["observations"][0]["entity_serial"] = 2
    with pytest.raises(ValueError, match="identity"):
        build_camp_assets(documents(), [cap], **KWARGS)


def test_objective_rules_preserve_unspecified_base_and_random_components():
    result = build_objective_rules(official(), **KWARGS)
    assert result["rules"][0]["value"] == 900
    assert result["rules"][1]["decrease_per_defeat_seconds"] == 60
    assert result["rules"][1]["minimum_seconds"] == 300
    assert result["rules"][1]["initial_base_seconds"] is None
    assert result["rules"][1]["random_extra_seconds"] is None


def test_official_patch_or_changed_statement_cannot_reuse_interpretation():
    notes = official()
    notes["general_notes"][2]["generic"][1]["note"] = "Initial spawn time 17:00"
    with pytest.raises(ValueError):
        build_objective_rules(notes, **KWARGS)
    notes = official()
    notes.update(patch_name="7.42a", patch_number="7.42a")
    with pytest.raises(ValueError):
        build_objective_rules(notes, exact_patch="7.42a", source_refs=REFS)


def test_builders_do_not_mutate_verified_inputs():
    cap, docs, notes = capture(), documents(), official()
    before = copy.deepcopy((cap, docs, notes, REFS))
    build_camp_assets(docs, [cap], official_notes=notes, **KWARGS)
    build_objective_observations([cap], **KWARGS)
    build_objective_rules(notes, **KWARGS)
    assert (cap, docs, notes, REFS) == before
