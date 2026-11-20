import copy

from dota_items.data import lane_decisions as lane


def position(team, points):
    return {"team": team, "pos": points}


def test_hidden_enemy_coordinates_and_future_sight_do_not_change_evidence():
    tracks = {"self": position(2, {900: (10, 10)}), "enemy": position(3, {900: (11, 10)})}
    past = lane.evidence_at(tracks, {("enemy", 2): [873]}, "self", 900)
    tracks["enemy"]["pos"][900] = (9000, 9000)
    assert lane.evidence_at(tracks, {("enemy", 2): [873, 901]}, "self", 900) == past
    assert past["enemies"] == [{"hero": "enemy", "last_seen": 873, "distance": None}]
    assert [m["hero"] for m in past["markers"]] == ["self"]


def test_future_changes_only_action_and_outcome():
    t = 920
    track = {s: (16384, 16384) for s in range(910, 927)}
    match = {
        "tracks": {"self": position(2, track)},
        "fronts": {t: {"radiant_mid": {"count": 1, "front": track[t]}}},
        "combat": [],
        "last": 950,
    }
    states = {t: {"unit_state_raw": 0}}
    base, action, outcome = next(
        lane.make_cases(match, 1, "self", [t, t + 2, t + 2], {}, states, {}, [])
    )
    other = copy.deepcopy(match)
    for delta in range(1, 7):
        other["tracks"]["self"]["pos"][t + delta] = (16384 - 100 * delta, 16384 - 100 * delta)
    same, alt, later = next(lane.make_cases(other, 1, "self", [t], {}, states, {}, [t + 15]))
    assert base == same and action["lean"] == alt["lean"]
    assert (action["action"], alt["action"]) == ("farm", "retreat")
    assert outcome["lane_last_hits"] == 2 and later["death_seconds"] == [t + 15]
    assert "lean" not in base and "action" not in base and "death_seconds" not in action


def test_control_limits_assessment_and_mixed_movement_abstains():
    frame = {"t": 1000, "enemies": [{"last_seen": 1000, "distance": 500}], "ally": None}
    assert lane.assess(frame, {"unit_state_raw": 1 << 5})[0] == "unknown"
    assert lane.assess(frame, {"unit_state_raw": 0})[0] == "retreat"
    path = {i: (-100 * i, -100 * i) for i in range(7)}
    assert lane.observe_action(path, [2], 2, 0, (0, 0))[0] == "unknown"
