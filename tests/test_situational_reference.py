"""M2b-T5 baseline 针对装 reference counts (U20, U21)."""

from dota_items.modeling import situational_reference as sr


def player(match_id, slot, hero, position=None, collapsed=False):
    return {
        "match_id": match_id,
        "player_slot": slot,
        "hero_id": hero,
        "position": position,
        "collapsed_carry": collapsed,
        "is_radiant": slot < 128,
    }


def buy(match_id, slot, item, t=1000):
    return {"match_id": match_id, "player_slot": slot, "item": item, "time_s": t}


def test_counts_use_only_given_matches_and_count_each_player_once():
    players = []
    for m in (1, 2, 3, 4):
        players += [player(m, 0, 8, 1, collapsed=m == 3), player(m, 1, 30, 5)]
        players += [player(m, 128 + i, 60 + i) for i in range(5)]
    purchases = [
        buy(1, 0, "basher", 900),
        buy(1, 0, "skadi", 1200),
        buy(1, 0, "skadi", 1300),  # repeat purchase counts once
        buy(1, 1, "spirit_vessel"),
        buy(1, 1, "spirit_vessel"),
        buy(2, 0, "disperser"),
        buy(2, 1, "glimmer_cape"),
        buy(3, 0, "skadi"),  # collapsed carry excluded
        buy(4, 0, "monkey_king_bar"),  # match 4 is outside the given split
        buy(4, 1, "pipe"),
    ]
    ref = sr.reference(players, purchases, [1, 2, 3])
    jugg = ref["juggernaut"]
    assert (jugg["games"], jugg["games_with_any"]) == (2, 2)
    assert jugg["first_counts"] == {
        "monkey_king_bar": 0,
        "skadi": 0,
        "basher": 1,
        "sange_and_yasha": 0,
        "nullifier": 0,
        "diffusal": 1,
    }
    assert jugg["bought_counts"]["skadi"] == 1 and jugg["bought_counts"]["monkey_king_bar"] == 0
    wd = ref["supports"][0]
    assert wd["spec"] == [30, 5] and wd["games"] == 3
    assert wd["bought_counts"]["spirit_vessel"] == 1 and wd["bought_counts"]["pipe"] == 0
    assert set(wd["bought_counts"]) == set(sr.SUPPORT_ITEMS)
    assert [s["games"] for s in ref["supports"][1:]] == [0, 0]
