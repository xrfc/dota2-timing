"""State cards ignore future calibration data and do not turn zero CD into can-cast."""

from copy import deepcopy

import pytest

from dota_items.data.decision_state import state_card


def fixture():
    def row(tick, cd):
        return {
            "tick": tick,
            "player_id": 0,
            "level": 14,
            "parser_game_time_s": tick / 30,
            "hero": {
                "entity_index": 1,
                "entity_serial": 2,
                "values": {
                    "m_iHealth": 100,
                    "m_iMaxHealth": 200,
                    "m_flMana": 70.0,
                    "m_flMaxMana": 80.0,
                    "m_lifeState": 0,
                },
            },
            "items": [
                {
                    "name": "item_tpscroll",
                    "slot": 15,
                    "handle": 123,
                    "entity": {
                        "entity_index": 3,
                        "entity_serial": 4,
                        "values": {"m_fCooldown": cd, "m_iCurrentCharges": 1},
                    },
                }
            ],
            "abilities": [],
        }

    capture = {
        "match_id": 1,
        "decision_tick": 300,
        "rows": [row(270, 4.0), row(300, 3.0), row(330, 2.0)],
    }
    decision = {"match_id": 1, "tick": 300, "target_slot": 0}
    old = {
        "tick": 300,
        "player_id": 0,
        "entity_index": 1,
        "entity_serial": 2,
        "hp": 100,
        "max_hp": 200,
        "mana": 70.0,
        "max_mana": 80.0,
        "life_state": 0,
    }
    return capture, decision, old


def test_past_countdown_zero_missing_and_cast_gate():
    cap, d, old = fixture()
    out = state_card(cap, d, old)
    assert out["tp"]["cooldown_status"] == "countdown_consistent"
    assert out["tp"]["cooldown_source_value"] == 3
    assert out["tp"]["can_cast"] is None and out["arrival_seconds"] is None
    cap["rows"][1]["items"][0]["entity"]["values"]["m_fCooldown"] = 0.0
    assert state_card(cap, d, old)["tp"]["cooldown_status"] == "zero_observed"
    cap["rows"][1]["items"][0]["entity"]["values"]["m_fCooldown"] = None
    assert state_card(cap, d, old)["tp"]["cooldown_source_value"] is None


def test_future_sample_changes_do_not_change_card_but_current_changes_do():
    cap, d, old = fixture()
    before = state_card(cap, d, old)
    unchanged = deepcopy(cap)
    cap["rows"][2]["items"][0]["entity"]["values"]["m_fCooldown"] = 99999.0
    cap["rows"][2]["hero"]["values"]["m_flMana"] = 99999.0
    assert state_card(cap, d, old) == before
    cap["rows"][1]["items"][0]["entity"]["values"]["m_fCooldown"] = 2.5
    assert state_card(cap, d, old) != before
    assert unchanged["rows"][2]["hero"]["values"]["m_flMana"] == 70.0


@pytest.mark.parametrize("change", ["identity", "resources", "duplicate", "missing"])
def test_mismatched_or_ambiguous_source_refused(change):
    cap, d, old = fixture()
    if change == "identity":
        old["entity_serial"] = 999
    elif change == "resources":
        old["mana"] = 999
    elif change == "duplicate":
        cap["rows"].append(deepcopy(cap["rows"][1]))
    else:
        cap["rows"] = cap["rows"][:1]
    with pytest.raises(ValueError):
        state_card(cap, d, old)
