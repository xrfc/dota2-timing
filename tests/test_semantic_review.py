"""Derived purchase/role fields must not masquerade as independent labels."""

import json

import pytest

from dota_items.data.feasibility import AuditConfig, audit_paths


def run(tmp_path, *, log=None, fields=None):
    raw = {
        "match_id": 123,
        "duration": 2000,
        "players": [
            {"player_slot": slot, "hero_id": hero, "lane_role": 1}
            for slot, hero in zip(
                [0, 1, 2, 3, 4, 128, 129, 130, 131, 132],
                [8, 2, 3, 4, 5, 6, 7, 9, 10, 11],
                strict=True,
            )
        ],
    }
    raw["players"][0].update(purchase_log=log)
    raw["players"][0].update(fields or {})
    path = tmp_path / "match.json"
    path.write_text(json.dumps(raw))
    report = audit_paths([path], AuditConfig())
    assert report["results"][0]["status"] == "inspectable"
    assert not report["training_allowed"]
    return report["results"][0]["semantic_review"]


def test_time_sum_not_completion_or_first_timestamp(tmp_path):
    result = run(
        tmp_path,
        log=[{"key": "manta", "time": 1200}, {"key": "manta", "time": 1500}],
        fields={
            "purchase_time": {"manta": 2700},
            "first_purchase_time": {"manta": 1200},
            "item_usage": {"manta": 1},
            "item_uses": {"manta": 12},
        },
    )
    row = result["aggregate_comparisons"][0]
    assert row["purchase_time"]["status"] == "consistent"
    assert row["first_purchase_time"]["status"] == "consistent"
    assert row["item_usage"]["status"] == "consistent"
    assert row["event_refs"] == ["players[0].purchase_log[0]", "players[0].purchase_log[1]"]
    assert not any(
        r["completion_time_available"] or r["negative_label_available"]
        for r in result["candidate_label_decisions"]
    )
    assert not result["independent_evidence"]


def test_zero_timestamp_first_purchase_overwrite_detected(tmp_path):
    result = run(
        tmp_path,
        log=[{"key": "manta", "time": 0}, {"key": "manta", "time": 20}],
        fields={"first_purchase_time": {"manta": 20}},
    )
    check = result["aggregate_comparisons"][0]["first_purchase_time"]
    assert check == {"reported": 20, "recomputed": 0, "status": "inconsistent"}


def test_unsorted_and_pregame_events_recompute_earliest(tmp_path):
    result = run(
        tmp_path,
        log=[{"key": "manta", "time": 10}, {"key": "manta", "time": -20}],
        fields={"first_purchase_time": {"manta": -20}, "purchase_time": {"manta": -10}},
    )
    assert result["aggregate_comparisons"][0]["first_purchase_time"]["status"] == "consistent"
    assert result["aggregate_comparisons"][0]["purchase_time"]["status"] == "consistent"


@pytest.mark.parametrize(
    "value,expected", [(None, "missing"), (True, "invalid"), ("2", "invalid"), (2, "inconsistent")]
)
def test_missing_bad_and_conflicting_aggregate(tmp_path, value, expected):
    fields = {} if value is None else {"item_usage": {"manta": value}}
    result = run(tmp_path, log=[{"key": "manta", "time": 10}], fields=fields)
    assert result["aggregate_comparisons"][0]["item_usage"]["status"] == expected


def test_filtered_recipes_and_invalid_events_not_certified(tmp_path):
    result = run(
        tmp_path,
        log=[
            {"key": "manta", "time": 10},
            {"key": "recipe_manta", "time": 10},
            {"key": "ward_dispenser", "time": 20},
            {"key": "manta", "time": 3000},
        ],
        fields={"purchase_time": {"manta": 10}, "item_usage": {"skadi": 1}},
    )
    assert len(result["aggregate_comparisons"]) == 1
    assert result["aggregate_comparisons"][0]["purchase_time"]["status"] == "unverifiable"
    assert result["aggregate_keys_without_valid_event"]["item_usage"] == ["skadi"]


@pytest.mark.parametrize(
    "position,status",
    [(None, "unknown"), (True, "unknown"), (1, "estimated_carry"), (5, "estimated_other")],
)
def test_lane_alone_is_not_carry_and_position_est_is_not_pregame(tmp_path, position, status):
    result = run(tmp_path, log=[], fields={"position_est": position})
    role = result["role_evidence"]
    assert role["status"] == status
    assert role["same_lane_team_slots"] == [0, 1, 2, 3, 4]
    assert not role["verified_position"]
    assert not role["usable_as_pregame_feature"]


@pytest.mark.parametrize(
    "inventory,status", [(None, "missing"), ([], "present_unverified"), ({}, "invalid")]
)
def test_inventory_field_never_certifies_completion(tmp_path, inventory, status):
    result = run(tmp_path, fields={"inventory_log": inventory, "item_0": 147})
    assert result["inventory_log_status"] == status
    assert not result["training_allowed"]
    assert not result["comparisons_complete_for_valid_log"]
