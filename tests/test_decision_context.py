"""No future/hidden endpoints or finished fight summaries in source projection."""

from copy import deepcopy

import pytest

from dota_items.data.decision_context import source_context


def inputs():
    players = [
        dict(player_id=0, hero_id=8, hero_name="jugg", team=2),
        dict(player_id=5, hero_id=29, hero_name="tide", team=3),
    ]
    event = dict(
        tick=290,
        visible_radiant=True,
        log_type="DAMAGE",
        attacker_name="jugg",
        target_name="tide",
        attacker_is_hero_present=True,
        target_is_hero_present=True,
        attacker_is_illusion_present=True,
        target_is_illusion_present=True,
        attacker_is_hero=True,
        target_is_hero=True,
        attacker_is_illusion=False,
        target_is_illusion=False,
    )
    raw = dict(
        match_id=1,
        players=players,
        combat_log=[event],
        wards=[
            dict(
                tick=280,
                team=2,
                x=10,
                y=20,
                ward_type="observer",
                killed_tick=999,
                expires_tick=9999,
            )
        ],
        smoke_events=[dict(tick=280, team=2, participants=[dict(removed_tick=999)])],
        teamfights=[dict(winner="radiant", end_tick=999)],
    )
    decision = dict(
        match_id=1, observer_team="radiant", tick=300, time=10, target_slot=0, target_hero_id=8
    )
    return raw, decision


def test_cutoff_side_and_real_hero_flags_with_positive_control():
    raw, decision = inputs()
    raw["combat_log"] += [
        dict(raw["combat_log"][0], tick=300),
        dict(raw["combat_log"][0], tick=301),
        dict(raw["combat_log"][0], tick=291, visible_radiant=None),
        dict(raw["combat_log"][0], tick=292, attacker_is_illusion=True),
    ]
    out = source_context(raw, decision, lambda t: t / 30)
    assert len(out["visible_real_hero_damage"]) == 1
    assert out["last10s_participant_hero_ids"] == [8, 29]
    raw["combat_log"][0]["visible_radiant"] = False
    assert source_context(raw, decision, lambda t: t / 30)["visible_real_hero_damage"] == []


def test_future_ward_smoke_endpoints_and_enemy_records_never_exported():
    raw, decision = inputs()
    raw["wards"].append(dict(tick=280, team=3, x=12345, y=67890))
    raw["smoke_events"].append(dict(tick=280, team=3, secret="enemy truth"))
    before = deepcopy(raw)
    out = source_context(raw, decision, lambda t: t / 30)
    assert len(out["friendly_recent_ward_placements"]) == 1
    assert len(out["friendly_recent_smoke_activations"]) == 1
    assert "killed_tick" not in str(out) and "removed_tick" not in str(out)
    assert "enemy truth" not in str(out) and "12345" not in str(out)
    assert out["enemy_smoke_truth"] is None and out["tp_arrival_seconds"] is None
    assert raw == before
    raw["wards"][0]["killed_tick"] = 7777
    raw["smoke_events"][0]["participants"] = [{"removed_tick": 7777}]
    raw["teamfights"][0]["winner"] = "dire"
    assert source_context(raw, decision, lambda t: t / 30) == out


def test_past_farming_is_not_resource_stock_or_tp_readiness():
    raw, decision = inputs()
    raw["combat_log"] += [
        dict(raw["combat_log"][0], target_name="npc_dota_neutral_centaur"),
        dict(
            tick=290,
            visible_radiant=True,
            log_type="ITEM",
            attacker_name="jugg",
            inflictor_name="item_tpscroll",
        ),
    ]
    out = source_context(raw, decision, lambda t: t / 30)
    assert out["own_farming_activity"]["neutral_damage_records"] == 1
    assert out["own_action_records"][0]["name"] == "item_tpscroll"
    assert out["tp_readiness"] is None and out["current_neutral_camp_stock"] is None


@pytest.mark.parametrize("change", ["match", "hero", "team", "view"])
def test_identity_mismatch_refused(change):
    raw, decision = inputs()
    if change == "match":
        decision["match_id"] = 2
    elif change == "hero":
        decision["target_hero_id"] = 29
    elif change == "team":
        raw["players"][0]["team"] = 3
    else:
        decision["observer_team"] = "omniscient"
    with pytest.raises(ValueError):
        source_context(raw, decision, lambda t: t / 30)
