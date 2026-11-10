"""U133: the track B holdout depends only on the match ID and is about 20%."""

from dota_items.data.awareness_split import HOLDOUT_PERCENT, describe, is_holdout


def test_holdout_is_stable_and_about_twenty_percent():
    ids = range(9_080_000_000, 9_080_020_000)
    share = sum(map(is_holdout, ids)) / len(ids)
    assert abs(share - HOLDOUT_PERCENT / 100) < 0.01
    assert is_holdout(9_080_000_123) == is_holdout("9080000123")
    assert describe()["decision"] == "U133"
