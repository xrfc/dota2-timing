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


def test_visible_path_stops_at_sighting_gap_and_excludes_future():
    track = {s: (s, 0) for s in range(20)}
    seen = [1, 2, 7, 8, 9, 14, 15]
    assert lane.visible_trail(track, seen, 9) == [[7, 7, 0], [8, 8, 0], [9, 9, 0]]


def test_jungle_anchor_accepts_distant_camp_and_ignores_future_in_assessment():
    t = 920
    match = {"tracks": {"self": position(2, {t: (9000, 9000)})}, "last": t + 22}
    camp = [{"id": 7, "x": 0, "y": 0}]
    common = (1, "self")
    state = {t: {"unit_state_raw": 0}}
    c, action, result = next(
        lane.make_jungle_cases(match, *common, [t, t + 1, t + 1], {}, state, {}, [], camp)
    )
    c2, a2, result2 = next(
        lane.make_jungle_cases(match, *common, [t], {}, state, {}, [t + 9], camp)
    )
    assert c == c2 and c["camp_distance"] > 1000
    assert c["camp_id"] == 7 and c["history"][-1]["camp"] == [0, 0]
    assert action["reason"] == a2["reason"] and action["detail"] != a2["detail"]
    assert result["jungle_last_hits"] == 2 and result2["death_seconds"] == [t + 9]


def test_jungle_neutral_prefix_uses_only_own_nonillusion_kills():
    base = {"log_type": "DEATH", "attacker_name": "self", "target_name": "npc_dota_neutral_kobold"}
    rows = [
        {"time": 950, "payload": base | extra}
        for extra in (
            {},
            {},
            {"attacker_is_illusion": True},
            {"attacker_name": "other"},
            {"log_type": "DAMAGE"},
            {"target_name": "npc_dota_creep_badguys_melee"},
        )
    ]
    assert lane.jungle_seconds(rows, "self") == [950, 950]


def test_route_from_lane_uses_latest_strictly_prior_hit_and_exact_circle():
    track = {955: (0, 0), 1000: (3, 4), 1001: (10000, 10000)}
    camps = [{"id": 1, "x": 3, "y": 4}, {"id": 2, "x": -5, "y": 0}, {"id": 3, "x": 5, "y": 1}]
    route = lane.route_from_lane(track, [955, 1000, 1001], 1000, camps)
    assert route == {
        "lane_t": 955,
        "lane_pos": [0, 0],
        "camp_id": 1,
        "camp_pos": [3, 4],
        "candidate_count": 2,
        "radius": 5,
    }
    assert lane.route_from_lane(track, [954, 1000], 1000, camps) is None
    assert lane.route_from_lane(track, [955, 998], 1000, camps) is None
    assert lane.route_from_lane(track, [955], 999, camps) is None


def test_public_death_state_excludes_dead_enemies_until_respawn():
    tracks = {"carry": position(2, {900: (0, 0)}), "a": position(3, {}), "b": position(3, {})}
    dead = lane.evidence_at(tracks, {}, "carry", 900, {"a", "b"})
    assert all(e["dead"] for e in dead["enemies"])
    assert lane.assess(dead, {"unit_state_raw": 0})[0] == "unknown"
    alive = lane.evidence_at(tracks, {}, "carry", 900)
    assert lane.assess(alive, {"unit_state_raw": 0})[0] == "retreat"
