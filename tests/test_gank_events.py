"""B0 gank rules (U115, U116, U131) on small synthetic matches."""

from dota_items.data import gank_events as g

C = 16384
SAVE = {"item_blink": {}, "item_glimmer_cape": {}, "item_tpscroll": {}}


def track(team, pid, positions):
    return {"team": team, "player_id": pid, "pos": dict(positions)}


def still(x, y, seconds=range(0, 120)):
    return {t: (x, y) for t in seconds}


def hit(t, attacker, victim="v"):
    payload = {
        "log_type": "DAMAGE",
        "attacker_is_hero": True,
        "attacker_is_illusion": False,
        "target_is_illusion": False,
        "attacker_name": attacker,
        "target_name": victim,
    }
    return {"time": t, "payload": payload}


def cast(t, caster, name, target=""):
    payload = {
        "log_type": "ITEM",
        "attacker_name": caster,
        "attacker_is_illusion": False,
        "inflictor_name": name,
        "target_name": target,
    }
    return {"time": t, "payload": payload}


def death(t, victim="v"):
    return {
        "time": t,
        "payload": {"log_type": "DEATH", "target_name": victim, "target_is_illusion": False},
    }


def lonely_match():
    """Victim alone on the map edge, two enemies, a teammate far away."""
    return {
        "v": track(2, 0, still(C, C)),
        "ally": track(2, 1, still(C - 5000, C - 5000)),
        "e1": track(3, 5, still(C + 300, C)),
        "e2": track(3, 6, still(C, C + 300)),
    }


def seen_all_except(hidden, seconds):
    seen = {}
    for hero in ("v", "ally", "e1", "e2"):
        for team in (2, 3):
            seen[(hero, team)] = set(range(0, 120))
    seen[(hidden, 2)] -= set(seconds)
    return seen


def run(combat, tracks=None, seen=None, positions=None):
    tracks = tracks or lonely_match()
    seen = seen if seen is not None else seen_all_except("e1", range(25, 30))
    positions = positions or {"v": 1}
    return g.detect_ganks(1, tracks, combat, seen, positions, SAVE)


def test_two_enemies_from_fog_kill_a_lonely_player():
    [episode] = run([hit(30, "e1"), hit(31, "e2"), death(35)])
    assert episode["is_gank"] and episode["outcome"] == "death"
    assert episode["attackers"] == ["e1", "e2"] and episode["unseen_attackers"] == ["e1"]
    assert episode["end"] == 35


def test_one_enemy_is_not_a_gank():
    [episode] = run([hit(30, "e1"), death(35)])
    assert not episode["flags"]["enough_enemies"] and not episode["is_gank"]


def test_surviving_without_a_save_is_only_being_hit():
    [episode] = run([hit(30, "e1"), hit(31, "e2")])
    assert episode["outcome"] == "none" and not episode["is_gank"]


def test_own_save_and_teammate_save_both_count():
    [own] = run([hit(30, "e1"), hit(31, "e2"), cast(33, "v", "item_blink")])
    assert own["is_gank"] and own["outcome"] == "self_save"
    [ally] = run([hit(30, "e1"), hit(31, "e2"), cast(33, "ally", "item_glimmer_cape", "v")])
    assert ally["outcome"] == "ally_save" and ally["ally_saves"][0]["by"] == "ally"


def test_save_used_on_an_enemy_does_not_count():
    [episode] = run([hit(30, "e1"), hit(31, "e2"), cast(33, "v", "item_glimmer_cape", "e1")])
    assert episode["outcome"] == "none"


def test_teleport_counts_only_when_the_hero_moved():
    tracks = lonely_match()
    stayed = run([hit(30, "e1"), hit(31, "e2"), cast(32, "v", "item_tpscroll")], tracks)
    assert stayed[0]["outcome"] == "none"
    tracks["v"]["pos"].update({t: (C - 6000, C - 6000) for t in range(36, 120)})
    moved = run([hit(30, "e1"), hit(31, "e2"), cast(32, "v", "item_tpscroll")], tracks)
    assert moved[0]["outcome"] == "self_save"


def test_a_new_episode_needs_ten_quiet_seconds():
    episodes = run([hit(30, "e1"), hit(38, "e2"), hit(47, "e1"), hit(58, "e2")])
    assert [e["t0"] for e in episodes] == [30, 58]


def test_teammate_nearby_or_enemies_in_sight_fail_their_conditions():
    tracks = lonely_match()
    tracks["ally"]["pos"] = still(C - 800, C)
    [near] = run([hit(30, "e1"), hit(31, "e2"), death(35)], tracks)
    assert not near["flags"]["far_from_allies"] and near["nearest_ally"] == 800
    [seen] = run([hit(30, "e1"), hit(31, "e2"), death(35)], seen=seen_all_except("e1", []))
    assert not seen["flags"]["from_unseen"]


def test_big_fight_is_excluded():
    tracks = lonely_match()
    for i in range(4):
        tracks[f"x{i}"] = track(3 if i % 2 else 2, 7 + i, still(C + 100 * i, C - 100))
    [episode] = run([hit(30, "e1"), hit(31, "e2"), death(35)], tracks)
    assert episode["most_heroes_near"] == 7 and not episode["flags"]["not_big_fight"]


def test_only_evaluated_positions_are_checked():
    assert run([hit(30, "e1"), hit(31, "e2"), death(35)], positions={"v": 3}) == []


def test_positions_follow_the_safelane_last_hit_rule():
    lane = range(60, 601)
    tracks = {
        "carry": track(2, 0, still(C + 6000, C - 6000, lane)),
        "support": track(2, 1, still(C + 5000, C - 6500, lane)),
        "mid": track(2, 2, still(C, C, lane)),
        "dire_a": track(3, 5, still(C - 6000, C + 6000, lane)),
        "dire_b": track(3, 6, still(C - 6000, C + 5000, lane)),
    }
    lh = {"carry": 80, "support": 10, "mid": 70, "dire_a": 40, "dire_b": 30}
    positions = g.infer_positions(tracks, lh)
    assert positions["carry"] == 1 and positions["support"] == 5 and positions["mid"] is None
    assert positions["dire_a"] is None and positions["dire_b"] is None  # gap 10 < 25


def test_visibility_table_keeps_state_between_changes():
    def event(t, radiant, dire):
        payload = {"hero_name": "e1", "radiant_state": radiant, "dire_state": dire}
        return {"time": t, "payload": payload}

    seen = g.visibility_table([event(0, "visible", "visible"), event(3, "hidden", "visible")], 5)
    assert seen[("e1", 2)] == {0, 1, 2} and seen[("e1", 3)] == set(range(6))


def test_save_means_follow_u131():
    class FakeKb:
        version = {"api": "test"}

        def trait_subject_filter(self, trait):
            return {"haste": ["mirana_leap"]}

        def subjects_with(self, mechanism):
            rows = {
                "self_mobility": [("antimage_blink", True), ("blink", False)],
                "haste": [
                    ("mirana_leap", True),
                    ("slardar_guardian_sprint", True),
                    ("phase_boots", False),
                    ("power_treads", False),
                ],
                "invisibility": [("enemy_only_spell", True), ("passive_spell", True)],
            }.get(mechanism, [])
            return [{"subject": s, "subject_zh": s, "is_ability": a} for s, a in rows]

        def ability_targeting(self, ability):
            return {
                "passive": ability == "passive_spell",
                "target_team": 2 if ability == "enemy_only_spell" else 0,
            }

    means = g.build_save_means(FakeKb())["means"]
    assert set(means) == {"antimage_blink", "item_blink", "mirana_leap", "item_phase_boots"}
    assert "damage_block" not in g.SAVE_MECHANISMS


def test_u132_position_one_only_and_death_is_the_main_label():
    assert g.PARAMS["positions"] == (1,)
    assert run([hit(30, "e1"), hit(31, "e2"), death(35)], positions={"v": 5}) == []
    [dead] = run([hit(30, "e1"), hit(31, "e2"), death(35)])
    [escaped] = run([hit(30, "e1"), hit(31, "e2"), cast(33, "v", "item_blink")])
    [hit_only] = run([hit(30, "e1"), hit(31, "e2")])
    assert (dead["label"], escaped["label"], hit_only["label"]) == ("death", "save_escape", None)
    summary = g.summarize([dead, escaped, hit_only], matches=1)
    assert summary["by_label"] == {"death": 1, "save_escape": 1}
    assert summary["ganks_per_player_match"] == 1.0
