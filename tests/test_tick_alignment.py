"""Adversarial observer privacy and ambiguity tests for tick joins."""

from dota_items.data.tick_alignment import align_player


def fixture():
    ps = [
        dict(
            match_id=1,
            player_slot=0,
            hero_id=8,
            source_tick=t,
            time=t // 30,
            x=t,
            y=t + 1,
            source_ref=f"p[{i}]",
        )
        for i, t in enumerate([0, 30, 60, 90])
    ]
    ss = [
        dict(
            tick=p["source_tick"],
            entity_index=10,
            entity_serial=1,
            life_state=0,
            source_ref=f"s[{i}]",
        )
        for i, p in enumerate(ps)
    ]
    vv = [
        dict(
            tick=t,
            entity_index=10,
            entity_serial=1,
            radiant_state="visible",
            dire_state=v,
            source_ref=f"v[{i}]",
        )
        for i, (t, v) in enumerate(
            [(0, "visible"), (30, "hidden"), (60, "unknown"), (90, "visible")]
        )
    ]
    return ps, ss, vv, {p["source_ref"] for p in ps}


def test_hidden_and_unknown_coordinate_and_life_mutations_do_not_leak():
    p, s, v, a = fixture()
    old = list(align_player(p, s, v, a))
    for i in [1, 2]:
        p[i]["x"] = 999999
        p[i]["y"] = -999999
        s[i]["life_state"] = 2
    new = list(align_player(p, s, v, a))
    assert [r[1][1] for r in old] == [r[1][1] for r in new]
    assert old[2][1][1]["last_seen"]["source_tick"] == 0
    assert old[2][1][1]["current_position"] is None


def test_future_changes_do_not_affect_prefix():
    p, s, v, a = fixture()
    old = list(align_player(p, s, v, a))
    p[-1]["x"] = 1e6
    s[-1]["life_state"] = 2
    v[-1]["dire_state"] = "hidden"
    assert old[:3] == list(align_player(p, s, v, a))[:3]


def test_ambiguous_same_tick_state_withholds_all_positions():
    p, s, v, a = fixture()
    s.append(dict(s[0], life_state=2))
    first = list(align_player(p, s, v, a))[0]
    assert "state_ambiguous" in first[0]["quality_flags"]
    assert first[0]["life_state"] is None
    assert all(x["current_position"] is None for x in first[1])


def test_same_tick_visibility_conflict_is_unknown_until_new_event():
    p, s, v, a = fixture()
    v.append(dict(v[0], dire_state="hidden"))
    first = list(align_player(p, s, v, a))[0]
    assert first[1][1]["visibility"] == "unknown"
    assert first[1][1]["current_position"] is None


def test_identity_change_does_not_reuse_old_visibility():
    p, s, v, a = fixture()
    s[0]["entity_serial"] = 2
    assert list(align_player(p, s, v, a))[0][1][0]["visibility"] == "unknown"


def test_quarantined_duplicate_position_never_restored():
    p, s, v, a = fixture()
    p.append(dict(p[0], x=99, source_ref="p[4]"))
    rows = list(align_player(p, s, v, a))
    assert len(rows) == 5
    for row, obs in rows[:2]:
        assert "duplicate_position_tick" in row["quality_flags"]
        assert all(x["current_position"] is None for x in obs)


def test_pause_repeated_second_kept_without_interpolation():
    p, s, v, a = fixture()
    p[1]["time"] = p[0]["time"]
    rows = list(align_player(p, s, v, a, [{"start_tick": 0, "end_tick": 31}]))
    assert len(rows) == 4
    assert "pause" in rows[1][0]["quality_flags"]
    assert "repeated_game_second" in rows[1][0]["quality_flags"]
    assert rows[1][1][1]["seconds_since_last_seen"] == 0
    assert rows[1][1][1]["ticks_since_last_seen"] == 30


def test_no_visibility_or_state_does_not_default_hidden():
    p, s, v, a = fixture()
    obs = list(align_player(p, [], [], a))[0][1][0]
    assert obs["visibility"] == "unknown" and obs["last_seen"] is None


def test_dead_visible_position_not_used_as_live_location():
    p, s, v, a = fixture()
    s[0]["life_state"] = 2
    obs = list(align_player(p, s, v, a))[0][1][0]
    assert obs["current_position"] is None and obs["visible_life_state"] == 2


def test_cleaning_rejection_withholds_even_valid_state():
    p, s, v, a = fixture()
    a.remove(p[0]["source_ref"])
    obs = list(align_player(p, s, v, a))[0][1][0]
    assert obs["current_position"] is None


def test_visible_positive_control_and_no_input_mutation():
    import copy

    p, s, v, a = fixture()
    before = copy.deepcopy((p, s, v, a))
    old = list(align_player(p, s, v, a))
    assert (p, s, v, a) == before
    p[0]["x"] += 50
    new = list(align_player(p, s, v, a))
    assert new[0][1][1]["current_position"] != old[0][1][1]["current_position"]
    assert new[1][1][1]["last_seen"] != old[1][1][1]["last_seen"]
