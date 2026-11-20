from dota_items.data.support_arrival import observed_approach, support_comparison, support_followup


def test_routes_preserve_delay_and_distinguish_tp_ownership():
    state = {
        "team": 2,
        "move_speed": 300,
        "pos": [0, 0],
        "items": {"15": {"name": "item_tpscroll", "cd": 0, "charges": 1}},
    }
    tower = {"name": "tower1", "x": 1450, "y": 0, "team": 2}
    result = support_comparison(state, [1500, 0], [tower], {})
    assert result["routes"]["walk"] == {"now": [5, 7], "after_six": [11, 13]}
    assert result["routes"]["tp"]["now"] == [4, 4]
    assert "tp" not in support_comparison(state, [1500, 0], [tower | {"team": 3}], {})["routes"]


def test_observed_damage_uses_target_and_censored_window():
    evidence = {9: {"ally"}, 10: {"other"}, 13: {"ally"}, 16: {"ally"}}
    out = support_followup(evidence, "ally", 9, 15)
    assert not out["complete"] and out["hit_offsets"] == [4]


def test_approach_uses_fixed_target_radius_and_keeps_gaps_unknown():
    target = (1000, 0)
    track = {t: (0, 0) for t in range(100, 121)}
    assert observed_approach(track, 100, 120, target)["status"] == "outside"
    assert observed_approach(track, 100, 110, target)["status"] == "truncated"
    track[105] = (600, 0)
    out = observed_approach(track, 100, 120, target)
    assert out["status"] == "observed_near" and out["first_entry_offset"] == 5
    del track[104]
    out = observed_approach(track, 100, 120, target)
    assert out["first_seen_offset"] == 5 and out["first_entry_offset"] is None
    assert observed_approach(track, 100, 104, target)["status"] == "missing"
    assert observed_approach(track, 105, 105, target)["status"] == "already_near"
