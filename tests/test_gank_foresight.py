from dota_items.data import gank_foresight as f


def track(team, positions):
    return {"team": team, "player_id": 0, "pos": positions}


def test_snapshot_counts_only_what_his_team_could_know():
    seconds = range(90, 111)
    tracks = {
        "v": track(2, {t: (16000, 16000) for t in seconds}),
        "ally": track(2, {t: (16300, 16400) for t in seconds}),
        "seen": track(3, {t: (17000, 16000) for t in seconds}),
        "just_gone": track(3, {t: (20000, 20000) for t in seconds}),
        "long_gone": track(3, {t: (16100, 16000) for t in seconds}),  # next to him, unseen
        "dead": track(3, {t: (16000, 16100) for t in range(90, 95)}),
    }
    seen = {("seen", 2): set(seconds), ("just_gone", 2): {95}, ("long_gone", 3): set(seconds)}
    row = f.snapshot("v", 100, tracks, seen)
    assert row == {
        "enemies_missing": 2,
        "enemies_missing_10s": 1,
        "nearest_ally": 500,
        "depth": round(f.depth((16000, 16000), 2)),
        "nearest_visible_enemy": 1000,
    }
    assert f.snapshot("dead", 100, tracks, seen) is None


def test_quiet_seconds_stay_away_from_episodes_and_deaths():
    tracks = {"v": track(2, {t: (1, 1) for t in range(0, 200) if not 100 <= t < 130})}
    episodes = [{"t0": 60, "end": 70}]
    assert f.quiet_seconds("v", tracks, episodes, 0, 30, 20) == [0, 30, 150, 180]


def test_auc_and_compare():
    assert f.auc([3, 3], [1, 2]) == 1.0 and f.auc([1], [1]) == 0.5 and f.auc([], [1]) is None
    rows = [dict.fromkeys(f.FEATURES, v) for v in (1, 2, 3)]
    result = f.compare(rows[1:], rows[:1] + [dict.fromkeys(f.FEATURES)])
    assert result["depth"] == {
        "positives": 2,
        "negatives": 1,
        "median_before_gank": 3,
        "median_quiet": 1,
        "auc": 1.0,
    }
