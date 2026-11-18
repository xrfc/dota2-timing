"""Death-risk samples use only what the player could know (U160)."""

from dota_items.data import death_risk as r

ZONES = {
    "towers": [
        {"name": "npc_dota_goodguys_tower1_mid", "team": 2, "x": 14000, "y": 14000},
        {"name": "npc_dota_badguys_tower1_mid", "team": 3, "x": 18000, "y": 18000},
    ],
    "forts": [],
}


def track(team, positions):
    return {"team": team, "player_id": 0, "pos": dict(positions)}


def event(t, kind, source, target, **more):
    return {"time": t, "payload": {"log_type": kind, "attacker_name": source,
                                   "target_name": target, **more}}  # fmt: skip


def test_features_ignore_enemies_the_team_cannot_see():
    seconds = range(80, 131)
    tracks = {
        "v": track(2, {t: (15000, 15000) for t in seconds}),
        "ally": track(2, {t: (15000, 16000) for t in seconds}),
        "seen": track(3, {t: (15600, 15800) for t in seconds}),
        "hidden": track(3, {t: (15100, 15100) for t in seconds}),  # next to him, unseen
        "dead": track(3, {t: (17000, 17000) for t in seconds if t < 90}),
    }
    vitals = {h: {t: (400, 1000, 50, 100, 7) for t in seconds} for h in tracks}
    seen_sorted = {("seen", 2): list(seconds), ("hidden", 2): [95, 96]}
    row = r.features("v", 100, tracks, vitals, seen_sorted, ZONES, {}, {99})
    assert row["enemies_visible"] == 1 and row["enemies_visible_near"] == 1
    assert row["nearest_visible_enemy_distance"] == 1000.0
    assert row["enemies_alive"] == 2 and row["enemies_missing"] == 1  # deaths are public
    assert row["missing_shortest_age"] == 4
    assert row["nearest_missing_last_seen_distance"] < 200  # where he was last seen
    assert row["hp_frac"] == 0.4 and row["allies_near"] == 1 and row["hit_recent"] == 1
    moved = {**tracks, "hidden": track(3, {t: (15100 + 50 * (t - 96), 15100) for t in seconds})}
    again = r.features("v", 100, moved, vitals, seen_sorted, ZONES, {}, set())
    hidden = {k: v for k, v in row.items() if k != "hit_recent"}
    assert {k: v for k, v in again.items() if k != "hit_recent"} == hidden  # unseen moves


def test_labels_and_samples_follow_the_real_deaths():
    combat = [
        event(118, "DEATH", "e", "v"),
        event(105, "DEATH", "e", "v", target_is_illusion=True),
        event(110, "DAMAGE", "e", "v"),
        event(111, "DAMAGE", "ally", "v"),
    ]
    assert r.death_times(combat, "v") == [118]
    assert r.hero_hit_seconds(combat, "v", {"v": 2, "e": 3, "ally": 2}) == {110}
    assert r.labels(100, [118], (10, 15, 20)) == {10: 0, 15: 0, 20: 1}
    assert r.labels(118, [118], (10,)) == {10: 0}  # the death itself is not "ahead"
    tracks = {
        "v": track(2, {t: (15000, 15000) for t in range(60, 118)}),
        "e": track(3, {t: (16000, 15000) for t in range(60, 131)}),
    }
    vitals = {h: {t: (500, 1000, 0, 0, 5) for t in range(60, 131)} for h in tracks}
    rows = r.samples(7, "v", tracks, vitals, {}, combat, ZONES, {}, 130)
    assert [row["t"] for row in rows] == list(range(60, 118, 5))  # none while dead
    assert [row["dies_10"] for row in rows][-3:] == [0, 1, 1]
    assert rows[-1]["hit_recent"] == 0 and rows[-2]["hit_recent"] == 1
    assert set(r.FEATURES_V1) <= set(rows[0])  # no context: version 1 features only


def test_save_state_counts_own_ready_save_means():
    means = {"item_black_king_bar": {}, "item_blink": {}, "jugg_spin": {}, "ember_remnant": {}}
    hero = {
        "mana": 40,
        "abilities": [
            {"name": "jugg_spin", "level": 1, "cd": 0.0, "mana_cost": 50},  # no mana
            {"name": "ember_remnant", "level": 2, "cd": 9.0, "charges": 1, "mana_cost": 0},
            {"name": "jugg_spin", "level": 0, "cd": 0.0},  # not learned
            {"name": "other", "level": 3, "cd": 0.0},
        ],
        "items": {
            "0": {"name": "item_black_king_bar", "cd": 0.0},
            "1": {"name": "item_blink", "cd": 3.0},
            "7": {"name": "item_black_king_bar", "cd": 0.0},  # backpack: not usable
        },
    }
    assert r.save_state(hero, means) == (4, 2)  # owned: spin, remnant, BKB, blink


def test_version_2_features_use_only_own_team_knowledge():
    seconds = range(80, 131)
    tracks = {
        "v": track(2, {t: (15000, 15000) for t in seconds}),
        "init": track(3, {t: (15200, 15000) for t in seconds}),  # unseen initiator
        "seen": track(3, {t: (16000, 15000) for t in seconds}),
    }
    vitals = {h: {t: (400, 1000, 50, 100, 7) for t in seconds} for h in tracks}
    seen_sorted = {("seen", 2): list(seconds), ("init", 2): [90]}
    fronts = {100: {"radiant_mid": {"count": 4, "front": (14000, 14000)},
                    "dire_mid": {"count": 4, "front": (15100, 15000)}}}  # fmt: skip
    wards = [
        {"type": "observer", "team": 2, "x": 15500, "y": 15000, "start": 50, "end": 200},
        {"type": "observer", "team": 2, "x": 19000, "y": 15000, "start": 50, "end": 200},
    ]
    context = {"kit": {100: (3, 1)}, "fronts": fronts, "wards": wards,
               "initiators": {"init", "seen"}}  # fmt: skip
    row = r.features("v", 100, tracks, vitals, seen_sorted, ZONES, {}, set(), context=context)
    assert (row["saves_owned"], row["saves_ready"]) == (3, 1)
    assert round(row["own_creeps_distance"]) == 1414  # the radiant wave, not the dire one
    assert row["ahead_of_own_creeps"] > 0
    assert row["own_observers_covering"] == 1
    assert row["missing_initiators"] == 1 and row["visible_initiators_mid"] == 1
    assert set(r.FEATURES_V2) <= set(row) and "reach_min" not in row  # no speeds given
    assert set(r.FEATURES_V1) == set(r.features("v", 100, tracks, vitals, seen_sorted, ZONES,
                                                {}, set()))  # fmt: skip


def test_reach_pairs_each_missing_enemy_with_his_own_age_and_speed():
    seconds = range(60, 131)
    tracks = {
        "v": track(2, {t: (15000, 15000) for t in seconds}),
        "near_old": track(3, {t: (17000, 15000) for t in seconds}),  # 2000 away, gone 20 s
        "far_new": track(3, {t: (25000, 15000) for t in seconds}),  # 10000 away, gone 2 s
    }
    vitals = {h: {t: (400, 1000, 50, 100, 7) for t in seconds} for h in tracks}
    seen_sorted = {("near_old", 2): [80], ("far_new", 2): [98]}
    context = {"kit": {}, "fronts": {}, "wards": [], "initiators": set(),
               "speeds": {"near_old": 255, "far_new": 255}}  # fmt: skip
    row = r.features("v", 100, tracks, vitals, seen_sorted, ZONES, {}, set(), context=context)
    # near_old: (2000 - 600) / 300 - 20 < 0, could be here; far_new: 9400 / 300 - 2 = 29.3
    assert row["reach_now"] == 1 and row["reach_10"] == 1
    assert row["reach_min"] < 0 and round(row["reach_second"], 1) == 29.3
    # The v2 features keep the nearest spot and the shortest age apart, from two heroes:
    assert row["missing_shortest_age"] == 2 and row["nearest_missing_last_seen_distance"] == 2000


def test_trends_use_only_rows_exactly_one_lag_earlier():
    base = dict.fromkeys(r.TREND_OF, 0.0)
    rows = [
        {**base, "t": 60, "enemies_visible": 3},
        {**base, "t": 65, "enemies_visible": 1},
        {**base, "t": 80, "enemies_visible": 0},  # 70 and 75 missing (he was dead)
    ]
    r.add_trends(rows)
    assert rows[1]["enemies_visible_d1"] == -2 and rows[1]["vanished_10"] == 0
    assert rows[2]["enemies_visible_d1"] == 0.0  # no row at 75
    assert rows[2]["enemies_visible_d3"] == -1  # the row at 65
    assert set(r.FEATURES_V3_TREND) <= set(rows[0])


def test_damage_to_his_illusion_is_not_a_hit_on_him():
    team = {"v": 2, "e": 3}
    combat = [
        event(100, "DAMAGE", "e", "v", target_is_illusion=True),  # same name, an illusion
        event(110, "DAMAGE", "e", "v", target_is_illusion=False),
        event(120, "DAMAGE", "e", "v", attacker_is_illusion=True),
    ]
    assert r.hero_hit_seconds(combat, "v", team) == {110}


def test_damage_taken_keeps_every_enemy_source_by_second():
    team = {"v": 2, "e": 3, "ally": 2}
    combat = [
        event(100, "DAMAGE", "e", "v", value=50),
        event(100, "DAMAGE", "e", "v", value=30),  # same second, same source: summed
        event(101, "DAMAGE", "e", "v", value=20, attacker_is_illusion=True),
        event(102, "DAMAGE", "npc_dota_badguys_tower1_mid", "v", value=100),
        event(103, "DAMAGE", "npc_dota_creep_badguys_melee", "v", value=10),
        event(104, "DAMAGE", "npc_dota_creep_goodguys_melee", "v", value=10),  # own creep
        event(105, "DAMAGE", "npc_dota_neutral_kobold", "v", value=5),
        event(106, "DAMAGE", "ally", "v", value=5),  # own team
        event(107, "DAMAGE", "e", "v", value=99, target_is_illusion=True),  # his illusion
    ]
    rows = r.damage_taken(combat, "v", team)
    assert [(x["t"], x["source"], x["value"]) for x in rows] == [
        (100, "hero", 80), (101, "illusion", 20), (102, "tower", 100), (103, "creep", 10),
        (105, "neutral", 5),
    ]  # fmt: skip
    hero_seconds = {x["t"] for x in rows if x["source"] == "hero"}
    assert hero_seconds == r.hero_hit_seconds(combat, "v", team)  # same rule as hit_recent
