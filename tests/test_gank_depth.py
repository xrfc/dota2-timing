"""Overextension signals and classes (U137, U138) on small synthetic situations."""

from dota_items.data import gank_depth as d

ZONES = {
    "towers": [
        {"name": "npc_dota_goodguys_tower1_mid", "team": 2, "x": 14840, "y": 14976},
        {"name": "npc_dota_badguys_tower1_mid", "team": 3, "x": 16908, "y": 17036},
        {"name": "npc_dota_goodguys_tower3_mid", "team": 2, "x": 11744, "y": 12240},
        {"name": "npc_dota_badguys_tower3_mid", "team": 3, "x": 20656, "y": 20143},
        {"name": "npc_dota_badguys_tower4_top", "team": 3, "x": 21328, "y": 21160},
        {"name": "npc_dota_badguys_tower4_bot", "team": 3, "x": 21664, "y": 20816},
    ],
    "forts": [
        {"name": "npc_dota_goodguys_fort", "team": 2, "x": 10464, "y": 11032},
        {"name": "npc_dota_badguys_fort", "team": 3, "x": 21912, "y": 21384},
    ],
    "fountains": [{"team": 2, "x": 8928, "y": 9446}, {"team": 3, "x": 23792, "y": 23232}],
    "camps": [
        {"id": 1, "team": 2, "x": 13000, "y": 15000},
        {"id": 2, "team": 3, "x": 18000, "y": 19000},
    ],
}


def track(team, pid, positions):
    return {"team": team, "player_id": pid, "pos": dict(positions)}


def still(x, y):
    return {t: (x, y) for t in range(80, 121)}


def walk(start, end, t0=90, t1=100):
    span = t1 - t0
    points = {
        t: (
            start[0] + (end[0] - start[0]) * (t - t0) / span,
            start[1] + (end[1] - start[1]) * (t - t0) / span,
        )
        for t in range(t0, t1 + 1)
    }
    return {**{t: start for t in range(80, t0)}, **points}


def death(t, name):
    return {"time": t, "payload": {"log_type": "DEATH", "target_name": name}}


def entry(t, tick, kind, source, target, inflictor=""):
    payload = {
        "log_type": kind,
        "tick": tick,
        "attacker_name": source,
        "target_name": target,
        "inflictor_name": inflictor,
        "attacker_is_hero": True,
    }
    return {"time": t, "payload": payload}


EPISODE = {"victim": "v", "t0": 100, "attackers": ["e1", "e2"]}


def test_depth_grows_toward_the_enemy_base_for_both_sides():
    assert d.depth((16384, 16384), 2) == 0
    assert d.depth((18000, 18000), 2) > 0 > d.depth((18000, 18000), 3)


def test_standing_towers_drop_the_dead_and_keep_the_forts():
    deaths = d.tower_deaths(
        [
            death(50, "npc_dota_badguys_tower1_mid"),
            death(60, "npc_dota_badguys_tower4"),
            death(70, "npc_dota_goodguys_tower1_mid"),
            death(10, "npc_dota_hero_axe"),
        ]
    )
    names = lambda second: sorted(t["name"][9:] for t in d.standing_towers(ZONES, deaths, second))  # noqa: E731
    assert len(names(40)) == 8
    assert "badguys_tower1_mid" not in names(55) and "goodguys_tower1_mid" in names(55)
    assert sum("tower4" in name for name in names(65)) == 1  # one of the pair fell
    assert names(200) == [
        "badguys_fort",
        "badguys_tower3_mid",
        "badguys_tower4_bot",
        "goodguys_fort",
        "goodguys_tower3_mid",
    ]


def test_carry_who_walks_into_the_enemy_jungle_alone_is_overextended():
    tracks = {
        "v": track(2, 0, walk((15000, 15000), (18200, 18600))),
        "ally": track(2, 1, still(13000, 13000)),
        "e1": track(3, 5, still(18500, 19000)),
        "e2": track(3, 6, still(18800, 18800)),
    }
    combat = [
        entry(99, 2990, "DAMAGE", "v", "e1"),
        entry(100, 3000, "DAMAGE", "e1", "v"),
    ]
    fronts = {"radiant_mid": {"count": 4, "front": [16000, 16000]}, "dire_mid": {"front": [1, 1]}}
    seen = {("e1", 2): set(range(90, 100))}
    result = d.depth_signals(EPISODE, tracks, combat, fronts, ZONES, {}, seen)
    assert result["signals"] == dict.fromkeys(d.SIGNALS, True)
    assert result["count"] == 7 and result["victim_closing_share"] == 1.0
    assert result["attackers_visible"] == ["e1"]
    assert result["first_strike"] == {"t": 99, "name": "attack", "target": "e1"}
    assert result["high_ground"] is None
    assert d.classify(result) == "overextended"
    unseen = d.depth_signals(EPISODE, tracks, combat, fronts, ZONES, {}, {})
    assert unseen["signals"]["saw_attackers"] is False
    assert d.classify(unseen, d.ROUND6) is None  # round 6: unseen is a gank however deep
    assert d.classify(unseen) == "overextended"  # U158: he went in, nobody was accounted for


def test_carry_jumped_in_his_own_area_stays_a_gank():
    tracks = {
        "v": track(2, 0, still(14500, 14500)),
        "ally": track(2, 1, still(15500, 15500)),
        "e1": track(3, 5, walk((18000, 18000), (14700, 14700))),
        "e2": track(3, 6, walk((18000, 17000), (14900, 14500))),
    }
    combat = [
        entry(100, 3000, "DAMAGE", "e1", "v"),
        entry(100, 3005, "DAMAGE", "v", "e1"),  # hits back after being hit
        entry(100, 2990, "DAMAGE", "v", "e1", "spectre_dispersion"),  # a passive is no strike
    ]
    fronts = {"radiant_mid": {"count": 4, "front": [16000, 16000]}}
    seen = {("e1", 2): {95, 96}}  # glimpsed for two of ten seconds
    result = d.depth_signals(EPISODE, tracks, combat, fronts, ZONES, {}, seen)
    assert result["signals"] == dict.fromkeys(d.SIGNALS, False)
    assert result["victim_closing_share"] == 0.0 and result["first_strike"] is None
    assert d.classify(result) is None


def test_overextended_needs_sight_and_either_approach_or_enemy_area():
    base = {"high_ground": None, "laning": False}
    off = dict.fromkeys(d.SIGNALS, False)
    for on, expected in (
        ({"saw_attackers"}, None),
        ({"enemy_tower_area", "alone_ahead", "beyond_creeps"}, None),
        ({"victim_approached", "struck_first"}, None),
        ({"saw_attackers", "enemy_jungle"}, "overextended"),
        ({"saw_attackers", "victim_approached"}, "overextended"),
    ):
        result = {**base, "signals": {**off, **dict.fromkeys(on, True)}}
        assert d.classify(result, d.ROUND6) == expected, on


def test_high_ground_is_the_quarter_circle_around_each_fountain():
    # radius = fountain to tier-3 tower (about 3970 / 4400) plus 700 attack range
    assert d.high_ground_side((11744, 12240), ZONES) == 2
    assert d.high_ground_side((12200, 12700), ZONES) == 2  # just outside the tower, in range
    assert d.high_ground_side((13200, 13600), ZONES) is None
    assert d.high_ground_side((20656, 20143), ZONES) == 3
    assert d.high_ground_side((16384, 16384), ZONES) is None
    for team in (2, 3):
        tracks = {
            "v": track(team, 0, still(21000, 20500)),
            "e1": track(5 - team, 5, still(21200, 20700)),
            "e2": track(5 - team, 6, still(21300, 20400)),
        }
        result = d.depth_signals(EPISODE, tracks, [], None, ZONES, {})
        assert result["high_ground"] == 3 and d.classify(result) == "high_ground"
        assert result["signals"]["beyond_creeps"] is None  # no lane fronts given
        assert result["signals"]["alone_ahead"] is None  # no living ally
        assert result["signals"]["saw_attackers"] is None  # no visibility table given


def test_laning_fight_with_only_lane_opponents_is_set_aside():
    def tracks_at(t0):
        seconds = range(60, t0 + 30)
        lane = {t: (21000, 10500) for t in seconds}  # bottom lane
        mid = {t: (16384, 16384) for t in seconds}
        return {
            "v": track(2, 0, lane),
            "e1": track(3, 5, {t: (21500, 10800) for t in seconds}),
            "e2": track(3, 6, {t: (21600, 11000) for t in seconds}),
            "roamer": track(3, 7, {**mid, **{t: (21300, 10700) for t in range(t0 - 3, t0 + 30)}}),
        }

    early = {"victim": "v", "t0": 300, "attackers": ["e1", "e2"]}
    tracks = tracks_at(300)
    lanes = d.hero_lanes(tracks)
    assert lanes == {"v": "bot", "e1": "bot", "e2": "bot", "roamer": "mid"}
    result = d.depth_signals(early, tracks, [], None, ZONES, {}, None, lanes)
    assert result["laning"] is True and d.classify(result) == "laning"
    helped = {**early, "attackers": ["e1", "roamer"]}
    result = d.depth_signals(helped, tracks, [], None, ZONES, {}, None, lanes)
    assert result["attackers_from_other_lanes"] == ["roamer"] and result["laning"] is False
    late = {**early, "t0": 700}
    tracks = tracks_at(700)
    result = d.depth_signals(late, tracks, [], None, ZONES, {}, None, d.hero_lanes(tracks))
    assert result["laning"] is False  # after ten minutes the rule no longer applies


def test_annotate_relabels_only_ganks_and_keeps_the_rule_label():
    tracks = {
        "v": track(2, 0, walk((15000, 15000), (18200, 18600))),
        "ally": track(2, 1, still(13000, 13000)),
        "e1": track(3, 5, still(18500, 19000)),
        "e2": track(3, 6, still(18800, 18800)),
    }
    gank = {**EPISODE, "is_gank": True, "label": "death"}
    other = {**EPISODE, "is_gank": False, "label": None}
    seen = {("e1", 2): set(range(80, 121))}
    late = {**d.ROUND6, "laning_end": 0}  # the synthetic episode starts at 1:40
    d.annotate([gank, other], tracks, [], {}, ZONES, {"e1": [(80, 95)]}, seen, late)
    assert (gank["rule_label"], gank["label"]) == ("death", "overextended")
    assert (other["rule_label"], other["label"]) == (None, None)
    assert gank["smoked_attackers"] == ["e1"] and "depth" in other


def test_victim_without_a_position_gives_unknown_signals():
    tracks = {"v": track(2, 0, {}), "e1": track(3, 5, still(1, 1)), "e2": track(3, 6, still(1, 1))}
    result = d.depth_signals(EPISODE, tracks, [], None, ZONES, {})
    assert result["count"] is None and d.classify(result) is None


def test_rotation_in_lane_is_a_gank_even_when_the_lane_opponent_is_in_sight():
    seconds = range(60, 330)
    tracks = {
        "v": track(2, 0, {t: (21000, 10500) for t in seconds}),
        "e1": track(3, 5, {t: (21500, 10800) for t in seconds}),
        "roamer": track(3, 7, {t: (16384, 16384) for t in seconds}),
    }
    episode = {"victim": "v", "t0": 300, "attackers": ["e1", "roamer"]}
    seen = {("e1", 2): set(seconds)}
    lanes = d.hero_lanes(tracks)
    result = d.depth_signals(episode, tracks, [], None, ZONES, {}, seen, lanes)
    assert result["attackers_visible"] == ["e1"]
    assert result["signals"]["saw_attackers"] is False
    seen[("roamer", 2)] = set(seconds)
    result = d.depth_signals(episode, tracks, [], None, ZONES, {}, seen, lanes)
    assert result["signals"]["saw_attackers"] is True


def test_chase_after_a_skirmish_is_keeping_not_a_gank():
    def hit(t, source, target, kind="DAMAGE"):
        return {"time": t, "payload": {"log_type": kind, "attacker_name": source,
                                       "target_name": target, "value": 50}}  # fmt: skip

    seconds = range(900, 1010)
    tracks = {
        "v": track(2, 0, {t: (16000, 16000) for t in seconds}),
        "a": track(2, 1, {t: (16300, 16000) for t in seconds}),
        "e1": track(3, 5, {t: (16500, 16200) for t in seconds}),
        "e2": track(3, 6, {t: (16600, 16400) for t in seconds}),
    }
    assert d.recent_fight("v", 1000, tracks, [], d.PARAMS) is None
    traded = [hit(980, "e1", "v")]
    fight = d.recent_fight("v", 1000, tracks, traded, d.PARAMS)
    assert fight == {"first_trade": 980, "deaths": [], "most_heroes": 4}
    quiet = dict.fromkeys(d.SIGNALS, False)
    assert d.classify({"after_fight": fight, "signals": quiet}, d.ROUND6) == "after_fight"
    assert d.recent_fight("v", 1000, tracks, [hit(960, "e1", "v")], d.PARAMS) is None  # too old
    far = {**tracks, "a": track(2, 1, {t: (9000, 9000) for t in seconds})}
    assert d.recent_fight("v", 1000, far, traded, d.PARAMS) is None  # nobody else around
    died = [*traded, hit(985, "e1", "a", "DEATH")]
    far["a"] = track(2, 1, {t: (17800, 16000) for t in seconds})
    assert d.recent_fight("v", 1000, far, died, d.PARAMS)["deaths"] == [{"t": 985, "hero": "a"}]


def test_after_a_fight_team_fights_and_pressing_on_get_their_own_class():
    quiet = dict.fromkeys(d.SIGNALS, False)
    small = {"first_trade": 980, "deaths": [], "most_heroes": 5}
    for params in (d.ROUND6, d.PARAMS):
        base = {"after_fight": small, "t0": 1000, "attackers": 2, "attackers_accounted": []}
        assert d.classify({**base, "signals": quiet}, params) == "after_fight"
        big = {**small, "most_heroes": 6}
        assert d.classify({**base, "after_fight": big, "signals": quiet}, params) == "teamfight"
        pressed = {**quiet, "victim_approached": True, "enemy_jungle": True}
        assert d.classify({**base, "signals": pressed}, params) == "overextended"
        assert d.classify({**base, "signals": {**quiet, "enemy_jungle": True}}, params) == (
            "after_fight"
        )


def test_round_7_a_skirmish_must_be_earlier_and_real():
    quiet = dict.fromkeys(d.SIGNALS, False)
    base = {"t0": 1000, "attackers": 2, "attackers_accounted": ["e1", "e2"], "signals": quiet}
    just_now = {"first_trade": 996, "deaths": [{"t": 998, "hero": "a"}], "most_heroes": 4}
    assert d.classify({**base, "after_fight": just_now}) is None  # the gank's own opening
    thin = {"first_trade": 975, "deaths": [], "most_heroes": 4}
    assert d.classify({**base, "after_fight": thin}) is None  # traded hits, no fight
    assert d.classify({**base, "after_fight": thin}, d.ROUND6) == "after_fight"
    real = {"first_trade": 975, "deaths": [{"t": 980, "hero": "a"}], "most_heroes": 4}
    assert d.classify({**base, "after_fight": real}) == "after_fight"


def test_round_7_going_in_is_overextension_unless_attackers_were_accounted_for():
    off = dict.fromkeys(d.SIGNALS, False)
    deep = {**off, "enemy_tower_area": True}
    base = {"attackers": 2, "t0": 1000}
    assert d.classify({**base, "signals": deep, "attackers_accounted": ["e1"]}) == "overextended"
    assert d.classify({**base, "signals": deep, "attackers_accounted": ["e1", "e2"]}) is None
    seen = {**deep, "saw_attackers": True}  # he watched them come and stayed
    assert d.classify({**base, "signals": seen, "attackers_accounted": ["e1", "e2"]}) == (
        "overextended"
    )
    assert d.classify({**base, "signals": off, "attackers_accounted": []}) is None  # at home

    seconds = range(930, 1001)
    tracks = {
        "v": track(2, 0, {t: (16000, 16000) for t in seconds}),
        "e1": track(3, 5, {t: (22000, 16000) for t in seconds}),  # seen far away
        "e2": track(3, 6, {t: (17000, 16000) for t in seconds if not 940 < t < 971}),  # dead
        "e3": track(3, 7, {t: (19000, 16000) for t in seconds}),  # seen, but close
        "e4": track(3, 8, {t: (23000, 16000) for t in seconds}),  # far, never seen
    }
    visible = {("e1", 2): {950}, ("e3", 2): {950}}
    episode = {"victim": "v", "t0": 1000, "attackers": ["e1", "e2", "e3", "e4"]}
    assert d.accounted_attackers(episode, tracks, visible) == ["e1", "e2"]


def test_laning_ends_per_lane_at_the_first_tower_or_when_the_heroes_leave():
    def lane_then(spot, leave, away=(16384, 16384)):
        return {t: (spot if t < leave else away) for t in range(60, 900)}

    top, bot = (11000, 21500), (21500, 11000)
    tracks = {
        "t1": track(2, 0, lane_then(top, 10**6)),
        "t2": track(3, 5, lane_then(top, 10**6)),
        "b1": track(2, 1, lane_then(bot, 480)),
        "b2": track(3, 6, lane_then(bot, 10**6)),
        "m1": track(2, 2, lane_then((16384, 16384), 10**6)),
    }
    lanes = d.hero_lanes(tracks)
    assert lanes == {"t1": "top", "t2": "top", "b1": "bot", "b2": "bot", "m1": "mid"}
    falls = {"npc_dota_badguys_tower1_top": [700], "npc_dota_goodguys_tower1_mid": [200]}
    ends = d.laning_ends(tracks, falls, lanes)
    # top: the tower fell at 11:40 but nobody left, so it is not a reason by itself (U159);
    # mid: a tower lost at 3:20 does not end laning; bot: half of its heroes left at 8:00.
    assert ends == {"top": 840, "mid": 840, "bot": 480}
    tracks["t2"] = track(3, 5, lane_then(top, 660))  # one of three left, then the tower
    tracks["t3"] = track(3, 7, lane_then(top, 10**6))
    assert d.laning_ends(tracks, falls, d.hero_lanes(tracks))["top"] == 700
    assert d.laning_ends(tracks, falls, lanes, d.ROUND6) == dict.fromkeys(
        ("top", "mid", "bot"), 600
    )
