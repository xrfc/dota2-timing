"""B0 review clips: smoke intervals, clip contents and judgment validation."""

import pytest

from dota_items.data import gank_review as r


def modifier(t, kind, hero, name=r.SMOKE_MODIFIER, illusion=False):
    payload = {
        "log_type": kind,
        "inflictor_name": name,
        "target_name": hero,
        "target_is_illusion": illusion,
    }
    return {"time": t, "payload": payload}


def hero(name, team, pid, x, hp=500, alive=True):
    return {
        "hero": name,
        "team": team,
        "player_id": pid,
        "pos": [x, 16000.4],
        "hp": hp,
        "max_hp": 1000,
        "life_state": 0 if alive else 2,
    }


def test_smoke_intervals_pair_add_and_remove_and_close_open_ones():
    combat = [
        modifier(10, "MODIFIER_ADD", "a"),
        modifier(25, "MODIFIER_REMOVE", "a"),
        modifier(40, "MODIFIER_ADD", "a"),
        modifier(12, "MODIFIER_ADD", "b", illusion=True),
        modifier(12, "MODIFIER_ADD", "c", name="modifier_invisible"),
    ]
    assert r.smoke_intervals(combat, 100) == {"a": [(10, 25), (40, 100)]}


def test_smoked_attackers_use_the_lookback_before_the_start():
    intervals = {"a": [(10, 25)], "b": [(70, 90)], "c": [(101, 110)]}
    assert r.smoked_attackers(intervals, ["a", "b", "c", "d"], t0=100) == ["b"]
    assert r.smoked_attackers(intervals, ["a"], t0=50) == ["a"]  # ended 25s before the start
    assert r.smoked_attackers(intervals, ["a"], t0=56) == []


def test_build_clip_window_states_and_events():
    rows = [
        {
            "t": t,
            "heroes": [
                hero("v", 2, 0, 16000 + t),
                hero("e1", 3, 5, 17000, alive=t < 104),
                hero("e2", 3, 6, 17500),
            ],
        }
        for t in range(60, 131)
    ]
    episode = {"victim": "v", "t0": 100, "end": 110, "attackers": ["e1", "e2"]}
    damage = {
        "log_type": "DAMAGE",
        "attacker_name": "e1",
        "target_name": "v",
        "value": 40,
        "attacker_is_illusion": False,
        "target_is_illusion": False,
    }
    cast = {"log_type": "ITEM", "attacker_name": "v", "inflictor_name": "item_blink"}
    combat = [
        modifier(80, "MODIFIER_ADD", "e1"),
        modifier(97, "MODIFIER_REMOVE", "e1"),
        {"time": 100, "payload": damage},
        {"time": 100, "payload": damage},
        {"time": 100, "payload": {**damage, "attacker_is_illusion": True}},
        {"time": 101, "payload": cast},
        {"time": 104, "payload": {"log_type": "DEATH", "attacker_name": "v", "target_name": "e1"}},
        {"time": 20, "payload": damage},
    ]  # fmt: skip
    seen = {("e1", 2): {99, 100}, ("v", 3): set(range(60, 131))}
    clip = r.build_clip("D1", "death", episode, rows, combat, seen)
    assert (clip["start"], clip["stop"]) == (70, 115)
    assert [f["t"] for f in clip["frames"]] == list(range(70, 116))
    assert [h["hero"] for h in clip["heroes"]] == ["v", "e1", "e2"]
    assert clip["use"] == "review_and_label_only" and clip["omniscient"] is True
    assert clip["smoked_attackers"] == ["e1"]
    at = {f["t"]: f["h"] for f in clip["frames"]}
    assert at[90][1] == [17000, 16000, 500, 1000, 1, 0, 1]  # hidden from team 2, smoked
    assert at[100][1][4:] == [1, 1, 0]  # seen, smoke gone
    assert at[105][1][4] == 0  # dead
    assert at[100][0] == [16100, 16000, 500, 1000, 1, 1, 0]
    kinds = [(e["t"], e["kind"]) for e in clip["events"]]
    assert kinds == [(80, "smoke"), (100, "damage"), (101, "cast"), (104, "death")]
    assert clip["events"][1]["value"] == 80  # two hits in one second are summed


def test_build_clip_needs_the_victim_in_the_window():
    rows = [{"t": 100, "heroes": [hero("e1", 3, 5, 17000)]}]
    episode = {"victim": "v", "t0": 100, "end": 100, "attackers": ["e1"]}
    with pytest.raises(ValueError):
        r.build_clip("D1", "death", episode, rows, [], {})


@pytest.mark.parametrize(
    "value",
    [
        {"id": "X9", "verdict": "gank", "note": ""},
        {"id": "D1", "verdict": "right", "note": ""},
        {"id": "D1", "verdict": "gank", "note": "x" * 501},
        {"id": "D1", "verdict": "gank"},
        {"id": "D1", "verdict": "gank", "note": "", "extra": 1},
        ["D1"],
    ],
)
def test_validate_judgment_rejects(value):
    with pytest.raises(ValueError):
        r.validate_judgment(value, {"D1"})


def test_validate_judgment_accepts_and_trims():
    value = {"id": "D1", "verdict": None, "note": " 正面打架 "}
    assert r.validate_judgment(value, {"D1"}) == {"id": "D1", "verdict": None, "note": "正面打架"}


def _episode(match, label, is_gank=True, flags=None):
    return {
        "match_id": match,
        "victim": "v",
        "t0": 100,
        "is_gank": is_gank,
        "label": label,
        "flags": flags or {"a": True, "b": True},
    }


def test_acceptance_sample_skips_reviewed_matches_and_hides_the_class_in_ids():
    episodes = [_episode(m, "death") for m in range(10)]
    episodes += [_episode(m, "laning") for m in range(10, 14)]
    episodes += [_episode(20, None, False, {"a": True, "b": False})]  # one condition short
    episodes += [_episode(21, None, False, {"a": False, "b": False})]  # never sampled
    quota = {"death": 3, "laning": 9, "near_miss": 1}
    items, population = r.draw_acceptance(episodes, {0, 1, 2, 10}, quota, 7)
    assert population == {"death": 7, "laning": 3, "near_miss": 1}
    assert [i["id"] for i in items] == [f"A{n:03d}" for n in range(1, 8)]
    assert sorted(i["stratum"] for i in items) == ["death"] * 3 + ["laning"] * 3 + ["near_miss"]
    assert not {i["episode"]["match_id"] for i in items} & {0, 1, 2, 10, 21}
    assert items == r.draw_acceptance(episodes, {0, 1, 2, 10}, quota, 7)[0]  # reproducible
    assert [r.rule_category(e) for e in (episodes[0], episodes[10], episodes[-1])] == [
        "gank",
        "laning",
        "other",
    ]


def test_review_list_has_every_disagreement_and_a_few_agreed_per_class():
    items = [{"id": f"A{n:03d}", "episode": _episode(n, "death")} for n in range(1, 9)]
    items += [{"id": "A009", "episode": _episode(9, "laning")}]
    second = {i["id"]: "gank" for i in items}
    second["A002"] = "overextended"  # disagrees with the rule's gank
    ids, rows = r.review_list(items, second, 2, 1)
    assert "A002" in ids and "A009" in ids  # A009: rule laning, second reader gank
    agreed = [x for x in ids if x not in ("A002", "A009")]
    assert len(agreed) == 2 and len(ids) == 4
    assert sum(row["user_reviews"] for row in rows) == 4
    assert [row["agree"] for row in rows].count(False) == 2


def test_clip_text_shows_observations_but_never_the_rule_answer():
    clip = {
        "id": "A001",
        "start": 98,
        "stop": 102,
        "heroes": [{"hero": "npc_dota_hero_v", "team": 2}, {"hero": "npc_dota_hero_e", "team": 3}],
        "episode": {
            "victim": "npc_dota_hero_v",
            "t0": 100,
            "attackers": ["npc_dota_hero_e"],
            "label": "overextended",
            "rule_label": "death",
            "flags": {"paid": True},
            "self_saves": [{"t": 101, "name": "item_blink"}],
            "depth": {"attackers_from_other_lanes": ["npc_dota_hero_e"], "signals": {}},
        },
        "frames": [
            {"t": 100, "h": [[1000, 1000, 50, 100, 1, 1, 0], [1300, 1400, 80, 100, 1, 0, 1]]},
            {"t": 101, "h": [[1000, 1000, 0, 100, 0, 1, 0], [1300, 1400, 80, 100, 1, 0, 1]]},
        ],
        "events": [
            {"t": 100, "kind": "cast", "source": "npc_dota_hero_e", "name": "x_bolt",
             "target": None, "target_other": False, "hits": ["npc_dota_hero_v"]},
            {"t": 101, "kind": "death", "source": "npc_dota_hero_e", "target": "npc_dota_hero_v"},
        ],
        "towers": [[3, 1000, 1600]],
    }  # fmt: skip
    zones = {"fountains": [{"team": 2, "x": 0, "y": 0}, {"team": 3, "x": 4000, "y": 4000}]}
    text = r.clip_text(clip, zones, {2: 4667, 3: 5102})
    assert "+0 | 50 | 1414 | 4243 | 敌方塔600 | 无 | 0/1 | e 500 不见 雾" in text
    assert "+1 | 已死亡" in text and "item_blink@+1" in text
    assert "e（夜魇）用 x_bolt（打中 v）" in text and "别的路：e" in text
    for hidden in ("overextended", "rule_label", "flags", "signals", "paid"):
        assert hidden not in text


def test_cast_events_say_whom_the_cast_hit_by_damage_or_debuff():
    rows = [
        {"t": t, "heroes": [hero("v", 2, 0, 16000), hero("e1", 3, 5, 16300)]}
        for t in range(95, 111)
    ]
    episode = {"victim": "v", "t0": 100, "end": 105, "attackers": ["e1"]}

    def log(t, kind, source, target, name):
        payload = {"log_type": kind, "attacker_name": source, "target_name": target}
        return {"time": t, "payload": {**payload, "inflictor_name": name, "value": 10}}

    combat = [
        log(100, "ABILITY", "e1", None, "e1_nova"),
        log(101, "DAMAGE", "e1", "v", "e1_nova"),
        log(102, "ITEM", "e1", "creep", "item_orchid"),
        log(102, "MODIFIER_ADD", "e1", "v", "modifier_orchid_malevolence_debuff"),
        log(103, "ABILITY", "e1", "v", "e1_gaze"),
        log(103, "MODIFIER_ADD", "e1", "v", "modifier_e1_gaze"),
        log(104, "ABILITY", "e1", None, "e1_buff"),
        log(104, "MODIFIER_ADD", "e1", "e1", "modifier_e1_buff"),  # on himself: not a hit
    ]
    clip = r.build_clip("D1", "death", episode, rows, combat, {}, lead=5, tail=5)
    casts = {e["name"]: e for e in clip["events"] if e["kind"] == "cast"}
    assert casts["e1_nova"]["hits"] == ["v"] and casts["e1_nova"]["target"] is None
    assert casts["item_orchid"]["hits"] == ["v"] and casts["item_orchid"]["target_other"] is True
    assert casts["e1_gaze"]["target"] == "v" and casts["e1_gaze"]["hits"] == ["v"]
    assert casts["e1_buff"]["hits"] == []


def test_acceptance_score_extends_the_agreed_sample_to_the_agreed_rest():
    rows = [
        {"id": "A1", "rule": "gank", "agree": False, "user_reviews": True},
        {"id": "A2", "rule": "gank", "agree": False, "user_reviews": True},
        {"id": "A3", "rule": "gank", "agree": True, "user_reviews": True},
        {"id": "A4", "rule": "gank", "agree": True, "user_reviews": True},
        {"id": "A5", "rule": "gank", "agree": True, "user_reviews": False},
        {"id": "A6", "rule": "gank", "agree": True, "user_reviews": False},
        {"id": "A7", "rule": "laning", "agree": True, "user_reviews": True},
        {"id": "A8", "rule": "laning", "agree": True, "user_reviews": False},
    ]
    judged = {"A1": "overextended", "A2": "gank", "A3": "gank", "A4": "unsure", "A7": "other"}
    judgments = {k: {"verdict": v} for k, v in judged.items()}
    score = r.acceptance_score(rows, judgments)
    gank = score["gank"]
    assert (gank["disagreed_judged"], gank["disagreed_user_sides_with_rule"]) == (2, 1)
    assert (gank["agreed"], gank["agreed_judged"], gank["agreed_user_sides_with_rule"]) == (4, 1, 1)
    assert gank["estimated_share_rule_right_on_gank_or_not"] == round((1 + 4) / 6, 3)
    # "other" is not the rule's class but still "not a gank": the rule is right on that.
    assert score["laning"]["estimated_share_rule_right_on_gank_or_not"] == 1.0
    assert score["laning"]["user_picked_same_class"] == 0
    unjudged = r.acceptance_score(rows, {})
    assert unjudged["gank"]["estimated_share_rule_right_on_gank_or_not"] is None


def test_ward_spans_and_wards_in_a_clip():
    def ward(time, tick, kind, **extra):
        payload = {"tick": tick, "ward_type": kind, "team": 3, "x": 100.4, "y": 200.6,
                   "expires_tick": None, "killed_tick": None, "killer": None, **extra}  # fmt: skip
        return {"time": time, "payload": payload}

    spans = r.ward_spans(
        [
            ward(10, 300, "observer", expires_tick=300 + 360 * 30),
            ward(50, 1500, "observer", killed_tick=1500 + 40 * 30, killer="npc_dota_hero_x"),
            ward(60, 1800, "sentry", killed_tick=1800 + 420 * 30),  # ran out, nobody killed it
            ward(500, 15000, "observer"),  # still standing when the replay ends
        ]
    )
    assert [(w["start"], w["end"], w["dewarded"]) for w in spans] == [
        (10, 370, False),
        (50, 90, True),
        (60, 480, False),
        (500, 860, False),
    ]
    assert spans[0]["x"] == 100 and spans[0]["y"] == 201 and spans[0]["team"] == 3
    rows = [{"t": t, "heroes": [hero("v", 2, 0, 16000)]} for t in range(60, 131)]
    episode = {"victim": "v", "t0": 100, "end": 110, "attackers": []}
    clip = r.build_clip("D1", "death", episode, rows, [], {}, wards=spans)
    assert [w["start"] for w in clip["wards"]] == [10, 50, 60]  # the last is placed later


def test_kappa_takes_out_agreement_by_chance():
    from dota_items.data.gank_review import agreement, cohen_kappa

    assert cohen_kappa([("a", "a"), ("b", "b")]) == 1.0
    assert cohen_kappa([("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]) == 0.0
    assert cohen_kappa([]) is None and cohen_kappa([("a", "a")]) is None
    result = agreement([("gank", "gank"), ("laning", "teamfight"), ("gank", "unsure"), (None, "x")])
    assert result["pairs"] == 2 and result["class_agreement"] == 0.5
    assert result["gank_or_not_agreement"] == 1.0 and result["gank_or_not_kappa"] == 1.0
