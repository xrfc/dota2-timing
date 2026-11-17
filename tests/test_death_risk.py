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
    assert set(r.FEATURES) <= set(rows[0])
