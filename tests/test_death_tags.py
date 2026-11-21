from dota_items.data import death_tags as d


def test_tags_hold_together_and_need_no_gank_class():
    episode = {
        "t0": 400,
        "flags": {"enough_enemies": True, "not_big_fight": True, "from_unseen": False,
                  "far_from_allies": True, "paid": True},
        "is_gank": False,
        "self_saves": [],
        "ally_saves": [],
        "smoked_attackers": ["e2"],
        "depth": {
            "signals": {"saw_attackers": True, "victim_approached": True, "struck_first": False,
                        "enemy_tower_area": False, "enemy_jungle": True},
            "attackers_from_other_lanes": ["e2"],
            "after_fight": {"first_trade": 380, "deaths": [], "most_heroes": 4},
            "high_ground": None,
        },
    }  # fmt: skip
    tags = [
        t for t, _ in d.death_tags(episode, teleported=["e2"], region={"name_zh": "夜魇主野区"})
    ]
    assert tags == [
        "laning", "other_lane", "teleported", "smoked", "seen_coming", "far_from_allies",
        "after_fight", "approached", "enemy_area", "region",
    ]  # fmt: skip
    late = {**episode, "t0": 1200, "depth": {**episode["depth"], "after_fight": {"most_heroes": 7}}}
    tags = [t for t, _ in d.death_tags(late)]
    assert "laning" not in tags and "other_lane" not in tags and "teamfight" in tags


def test_primary_reason_takes_the_first_row_that_holds():
    def reason(*names):
        return d.primary_reason([(n, "") for n in names])[0]

    assert reason("laning", "high_ground") == "laning"  # high ground is a tag only (U157)
    assert reason("from_unseen", "far_from_allies", "high_ground") == "other"  # U140: not a gank
    assert reason("laning", "other_lane", "from_unseen", "far_from_allies") == "ganked"
    assert reason("laning") == "laning"
    assert reason("after_fight", "approached", "enemy_area") == "pressed_on"
    assert reason("after_fight") == "after_fight"
    assert reason("seen_coming", "approached", "from_unseen", "far_from_allies") == "overextended"
    assert reason("from_unseen", "far_from_allies", "single") == "solo"
    assert reason("far_from_allies") == "other"
    assert reason() == "skirmish"  # allies within 1500


def test_death_matching_preserves_ambiguity_and_uses_exact_end():
    death = {"match_id": 1, "victim": "h", "t0": 8, "end": 20, "outcome": "death"}
    other = {**death, "t0": 15}
    index = d.death_episode_index([death, other, {**death, "outcome": "none"}])
    assert d.coverage_reason(index[1, "h", 20]) == d.AMBIGUOUS
    assert d.coverage_reason(index[1, "h", 21]) == d.MISSING
    assert d.coverage_reason([death]) is None
