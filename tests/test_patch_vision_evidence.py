"""Pure evidence decoding distinguishes target labels from a full geometric FOW map."""

from copy import deepcopy

import pytest

from dota_items.data.patch_vision_evidence import (
    STATE_COLUMNS,
    analyze_vision_evidence,
    iter_hero_visibility_labels,
)


def document():
    classes = [
        "CDOTA_Unit_Hero_Test",
        "CDOTA_DataRadiant",
        "CDOTA_DataDire",
        "CDOTA_NPC_Observer_Ward_TrueSight",
        "CDOTA_BaseNPC_Announcer",
    ]
    return {
        "schema": "map-vision-evidence/1",
        "coordinate_space": "world",
        "match_id": 123,
        "game_build": 6993,
        "post_game_tick": 90,
        "parse_error": None,
        "truncated_at_tick": None,
        "state_columns": list(STATE_COLUMNS),
        "entity_catalog": [
            {"entity_index": i, "entity_serial": 2, "class_name": cls, "first_seen_tick": 0}
            for i, cls in zip([65, 2, 3, 70, 71], classes, strict=True)
        ],
        "states": [
            [0, 230.0, 20.0, True, 2, 0, 400, False, 1800, 800, None, None, None, 0],
            [3, 240.0, 20.0, True, 3, 0, 100, False, 0, 0, None, None, None, 0],
            [4, None, None, True, None, None, None, None, 575, 575, None, None, None, None],
        ],
        "team_word_snapshots": [[[1, 2]], [[1, 0]], [[1, None]]],
        "tree_word_snapshots": [[5, None], [7, None]],
        "temporary_tree_events": [],
        "frames": [
            {
                "t": t,
                "tick": tick,
                "game_time": t + 0.2,
                "entity_state_ids": [0, 1, 2],
                "canonical_heroes": [[0, 0, 32833]],
                "team_word_refs": {
                    "radiant": {"entity_id": 1, "snapshot_id": 0},
                    "dire": {"entity_id": 2, "snapshot_id": word},
                },
                "tree_word_refs": {"radiant": {"entity_id": 1, "snapshot_id": tree}},
                "tree_model_replacements_raw": {},
                "rules_raw": {
                    "m_pGameRules.m_iNetTimeOfDay": 16387,
                    "m_pGameRules.m_flDaytimeStart": 0.25,
                },
            }
            for t, tick, word, tree in [(-1, 0, 1, 0), (0, 30, 1, 0), (1, 60, 2, 1)]
        ],
        "sampling": {"boundary": "completed_packet", "end_game_time": 2.2},
    }


def test_recorded_words_are_target_labels_with_unknown_distinct_from_hidden():
    doc = document()
    before = deepcopy(doc)
    labels = list(iter_hero_visibility_labels(doc))
    assert [row["visible"] for row in labels] == [True, False, True, None]
    assert all(row["entity_index"] == 65 and row["entity_serial"] == 2 for row in labels)
    assert all(
        not row["sight_source_attributed"] and not row["coordinate_fow_inferred"] for row in labels
    )
    assert len(list(iter_hero_visibility_labels(doc, include_pre_game=True))) == 6
    assert doc == before


def test_summary_reports_denominators_zero_ranges_unknown_time_and_unmapped_trees():
    result = analyze_vision_evidence(document(), expected_duration=2)
    assert result["counts"]["game_frames"] == 2
    assert result["counts"]["pre_game_frames"] == 1
    assert result["counts"]["canonical_hero_samples"] == 2
    assert result["counts"]["missing_player_samples"] == 18
    assert result["counts"]["recorded_hero_team_labels_known"] == 3
    assert result["counts"]["recorded_hero_team_labels_unknown"] == 1
    assert result["timeline"]["missing_game_seconds"] == [2]
    assert result["timeline"]["duration_matches_expected"] is True
    sentry = result["potential_source_categories"]["sentry_ward"]
    assert sentry["day_vision_range_known"] == 2
    assert result["observed_ranges"]["sentry_ward.day_vision_range"] == {"0": 2}
    assert "other_networked_entity_unclassified" in result["potential_source_categories"]
    assert result["dynamic_trees"]["channel_raw_bit_flips"] == {"radiant": 1}
    assert result["dynamic_trees"]["world_tree_index_to_position_verified"] is False
    assert result["daynight_integer_encoding_verified"] is False
    assert result["current_effective_range_certified"] is False
    assert result["full_coordinate_fog_of_war_available"] is False
    assert result["training_allowed"] is False


def test_missing_target_state_or_observer_channel_stays_unknown_without_fallback():
    doc = document()
    doc["frames"][1]["entity_state_ids"] = [1, 2]
    doc["frames"][2]["team_word_refs"] = {}
    assert all(row["visible"] is None for row in iter_hero_visibility_labels(doc))


def test_temporary_tree_does_not_inherit_npc_visibility_word_semantics():
    doc = document()
    doc["entity_catalog"][3]["class_name"] = "CDOTA_TempTree"
    result = analyze_vision_evidence(doc)
    tree = result["potential_source_categories"]["temporary_tree"]
    assert tree["recorded_radiant_None"] == tree["recorded_dire_None"] == 2
    assert "recorded_radiant_False" not in tree


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(sampling=None),
        lambda d: d.update(parse_error="truncated"),
        lambda d: d["states"][0].__setitem__(1, float("nan")),
        lambda d: d["states"][0].__setitem__(2, None),
        lambda d: d["states"][0].__setitem__(8, True),
        lambda d: d["states"][0].__setitem__(7, 1),
        lambda d: d["states"][0].__setitem__(13, -1),
        lambda d: d["team_word_snapshots"][0][0].__setitem__(1, 2**64),
        lambda d: d["team_word_snapshots"][0].append([1, 1]),
        lambda d: d["tree_word_snapshots"][0].__setitem__(0, False),
        lambda d: d["entity_catalog"].append(deepcopy(d["entity_catalog"][0])),
        lambda d: d["entity_catalog"][0].update(first_seen_tick=90),
        lambda d: d["frames"][1].update(t=1),
        lambda d: d["frames"][1].update(tick=91),
        lambda d: d["frames"].append(deepcopy(d["frames"][-1])),
        lambda d: d["frames"][0].pop("entity_state_ids"),
        lambda d: d["frames"][0]["entity_state_ids"].append(0),
        lambda d: d["frames"][0]["entity_state_ids"].append(999),
        lambda d: d["frames"][0]["canonical_heroes"][0].__setitem__(2, 49217),
        lambda d: d["frames"][0]["canonical_heroes"].append([0, 0, 32833]),
        lambda d: d["frames"][0]["team_word_refs"]["dire"].update(entity_id=1),
        lambda d: d["frames"][0]["team_word_refs"].update(
            {"radiant:fake": {"entity_id": 1, "snapshot_id": 0}}
        ),
        lambda d: d["frames"][0].update(rules_raw={"day": float("nan")}),
    ],
)
def test_structural_identity_and_raw_value_corruption_is_rejected(mutate):
    doc = document()
    mutate(doc)
    with pytest.raises(ValueError):
        analyze_vision_evidence(doc)
    with pytest.raises(ValueError):
        list(iter_hero_visibility_labels(doc))


def test_unknown_end_clock_empty_frames_do_not_assert_complete_coverage():
    doc = document()
    doc["frames"] = []
    doc["sampling"]["end_game_time"] = None
    result = analyze_vision_evidence(doc)
    assert result["timeline"]["missing_game_seconds"] is None
    assert result["counts"]["canonical_hero_samples"] == 0
    assert result["recorded_entity_visibility_labels_available"] is False
    assert list(iter_hero_visibility_labels(doc)) == []


@pytest.mark.parametrize("value", [-1, True, 1.5, "2"])
def test_expected_duration_is_explicit_integer(value):
    with pytest.raises(ValueError, match="duration"):
        analyze_vision_evidence(document(), expected_duration=value)
