"""Temporal, observer and identity admission, plus meaningful current-state controls."""

from copy import deepcopy

import pytest

from dota_items.data.decision_comparison import comparison_card


def fixture():
    raw = {"match_id": 1, "players": [], "coach_state_snapshots": [], "hero_visibility_events": []}
    decision = {"match_id": 1, "tick": 300, "time": 10, "observer_team": "radiant", "positions": []}
    for pid, slot, visible in [(0, 0, True), (5, 128, True), (6, 129, False)]:
        raw["players"].append({"player_id": pid, "hero_id": pid + 8, "team": 2 if pid == 0 else 3})
        raw["coach_state_snapshots"].append(
            {
                "tick": 300,
                "player_id": pid,
                "entity_index": pid + 1,
                "entity_serial": 2,
                "hp": 100,
                "max_hp": 200,
                "life_state": 0,
                "level": 14,
                "items": {"0": "item_bfury"},
                "inventory_handles": {str(i): 123 if i == 0 else 16777215 for i in range(17)},
                "inventory_empty_handle": 16777215,
                "ability_levels": {"juggernaut_omni_slash": 2},
            }
        )
        raw["hero_visibility_events"].append(
            {
                "tick": 290,
                "player_id": pid,
                "entity_index": pid + 1,
                "entity_serial": 2,
                "radiant_state": "visible" if visible else "hidden",
            }
        )
        decision["positions"].append(
            {
                "player_slot": slot,
                "hero_id": pid + 8,
                "relation": "ally" if pid == 0 else "enemy",
                "visibility": "visible" if visible else "hidden",
                "life_state": 0 if visible else None,
                "position_status": "available" if visible else "hidden",
                "current_position": {"x": 10, "y": 20} if visible else None,
                "last_seen": None,
            }
        )
    live = {
        "tick": 300,
        "tp": {"cooldown_source_value": 3.0, "cooldown_status": "countdown_consistent"},
        "abilities": [
            {
                "name": "juggernaut_omni_slash",
                "cooldown_status": "countdown_consistent",
                "cooldown_source_value": 30.7,
            }
        ],
    }
    return raw, decision, live


def test_known_friendly_inventory_visible_enemy_health_not_enemy_inventory():
    raw, d, live = fixture()
    before = deepcopy(raw)
    out = comparison_card(raw, d, live)
    ally, enemy, hidden = out["team_state"]
    assert ally["inventory"]["slots"][0]["item"] == "item_bfury"
    assert enemy["health"]["current"] == 100 and enemy["inventory"] is None
    assert hidden["health"] is None and hidden["inventory"] is None
    assert out["arrival"]["tp_cooldown_wait_source_seconds"] == 3
    assert out["arrival"]["arrival_interval_seconds"] is None
    assert len(out["verified_constraints"]) == 2
    assert all(a["judgment"] is None for a in out["annotation"]["actions"])
    assert not out["training_allowed"] and raw == before


def test_hidden_enemy_future_and_inspection_only_fields_do_not_leak():
    raw, d, live = fixture()
    before = comparison_card(raw, d, live)
    raw["coach_state_snapshots"][2]["hp"] = 999999
    raw["coach_state_snapshots"][1]["items"] = {"0": "item_rapier"}
    raw["coach_state_snapshots"][1]["ability_levels"] = {"hidden": 99}
    future = deepcopy(raw["coach_state_snapshots"][0])
    future["tick"] = 301
    future["hp"] = 999999
    raw["coach_state_snapshots"].append(future)
    raw["hero_visibility_events"].append(
        {
            "tick": 301,
            "player_id": 0,
            "entity_index": 99,
            "entity_serial": 99,
            "radiant_state": "hidden",
        }
    )
    assert comparison_card(raw, d, live) == before
    raw["coach_state_snapshots"][1]["hp"] = 50
    assert comparison_card(raw, d, live) != before


@pytest.mark.parametrize("change", ["serial", "duplicate", "hero", "visibility"])
def test_bad_visible_identity_withholds_health(change):
    raw, d, live = fixture()
    if change == "serial":
        raw["coach_state_snapshots"][1]["entity_serial"] = 99
    elif change == "duplicate":
        raw["coach_state_snapshots"].append(deepcopy(raw["coach_state_snapshots"][1]))
    elif change == "hero":
        raw["players"][1]["hero_id"] = 99
    else:
        raw["hero_visibility_events"][1]["radiant_state"] = "hidden"
    out = comparison_card(raw, d, live)
    assert out["team_state"][1]["health"] is None


def test_unknown_tp_wait_not_zero_and_unknowns_not_negative_labels():
    raw, d, live = fixture()
    live["tp"]["cooldown_status"] = "positive_source_value"
    out = comparison_card(raw, d, live)
    assert out["arrival"]["tp_cooldown_wait_source_seconds"] is None
    assert all(a["expected_gain"] is None for a in out["alternatives"])
    live["tick"] = 301
    with pytest.raises(ValueError, match="cutoff"):
        comparison_card(raw, d, live)


@pytest.mark.parametrize("change", ["hidden_position", "future_last_seen"])
def test_untrusted_observer_projection_is_rejected(change):
    raw, d, live = fixture()
    if change == "hidden_position":
        d["positions"][2]["current_position"] = {"x": 123, "y": 456}
    else:
        d["positions"][2]["last_seen"] = {"source_tick": 301, "time": 11}
    with pytest.raises(ValueError):
        comparison_card(raw, d, live)


def test_join_readiness_not_inferred_from_zero_cd_and_friendly_item_positive_control():
    raw, d, live = fixture()
    live["tp"]["cooldown_status"] = "zero_observed"
    live["tp"]["cooldown_source_value"] = 0.0
    before = comparison_card(raw, d, live)
    assert before["arrival"]["tp_cooldown_wait_source_seconds"] == 0.0
    assert before["arrival"]["can_start_tp"] is None
    raw["coach_state_snapshots"][0]["items"]["0"] = "item_yasha"
    assert comparison_card(raw, d, live) != before
