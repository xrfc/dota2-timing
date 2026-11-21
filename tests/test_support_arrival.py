from dota_items.data.support_arrival import (
    observed_approach,
    support_comparison,
    support_followup,
    walk_hit_window,
)


def test_routes_preserve_delay_and_distinguish_tp_ownership():
    state = {
        "team": 2,
        "move_speed": 300,
        "mana": 75,
        "pos": [0, 0],
        "items": {"15": {"name": "item_tpscroll", "cd": 0, "charges": 1}},
    }
    tower = {"name": "tower1", "x": 1450, "y": 0, "team": 2}
    result = support_comparison(state, [1500, 0], [tower], {})
    assert result["routes"]["walk"] == {"now": [5, 7], "after_six": [11, 13]}
    assert result["routes"]["tp"]["now"] == [4, 4]
    for mana in (0, 74, None):
        result = support_comparison(state | {"mana": mana}, [1500, 0], [tower], {})
        assert "tp" not in result["routes"]
        assert ("待确认" if mana is None else "不足") in result["summary"]
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


def test_walk_hit_window_keeps_delay_ties_and_censoring_separate():
    walk = {"now": [3, 5], "after_six": [9, 11]}
    for hits, complete, now, delayed in (
        ([1, 11], True, "both_before_hit", "both_before_hit"),
        ([1, 9], True, "both_before_hit", "direct_only"),
        ([3, 5], True, "both_before_hit", "after_observed_hits"),
        ([3, 5], False, "both_before_hit", "unknown"),
        ([2], True, "after_observed_hits", "after_observed_hits"),
        ([], True, "unknown", "unknown"),
    ):
        row = walk_hit_window(walk, {"hit_offsets": hits, "complete": complete})
        assert (row["now"], row["after_six"]) == (now, delayed)
    assert walk_hit_window({}, {"hit_offsets": [12], "complete": True})["now"] == "unknown"


def test_existing_report_exports_a_row_for_each_decision(tmp_path):
    import csv
    import json
    import os
    import subprocess
    import sys
    from io import StringIO

    mid = 9080976703
    key = f"{mid}-slark-912"
    case = {
        "id": key,
        "match": mid,
        "hero": "slark",
        "t": 912,
        "support_opportunity": {"hero": "rubick"},
        "arrival": {"routes": {"walk": {"now": [3, 4], "after_six": [9, 10]}}},
    }
    other = {**case, "id": f"{mid}-slark-1100", "t": 1100, "support_opportunity": None}
    (tmp_path / "cases.json").write_text(
        json.dumps({"schema": "lane-decision-review/1", "mode": "lane", "cases": [case, other]})
    )
    (tmp_path / "outcomes").mkdir()
    (tmp_path / "outcomes" / f"{key}.json").write_text(
        json.dumps({"support_followup": {"hit_offsets": [1, 7], "complete": True}})
    )
    result = subprocess.check_output(
        [sys.executable, "scripts/check_support_travel.py", "--review-dir", str(tmp_path)],
        env={**os.environ, "PYTHONPATH": "src"},
        text=True,
    )
    first, second = csv.DictReader(StringIO(result))
    assert (first["now"], first["after_six"]) == ("both_before_hit", "after_observed_hits")
    assert first["hit_offsets"] == "[1, 7]"
    assert second["reason"] == "no_target" and not second["now"]
