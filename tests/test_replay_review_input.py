"""Review projection of verified replay channels, using only synthetic inputs."""

from copy import deepcopy

import pytest

from dota_items.data.gank_review import SMOKE_MODIFIER
from dota_items.data.replay_review_input import project_match

SOURCE = {"schema": "review-source/1", "manifest_sha256": "a" * 64}


def parsed(duration=2):
    counts = [80, 10, 70, 50, 40, 40, 30, 20, 10, 5]
    return {
        "duration": duration,
        "players": [
            {
                "player_slot": pid if pid < 5 else pid - 5 + 128,
                "hero_id": pid + 1,
                "economy_log": [{"time": min(900, duration), "last_hits": counts[pid]}],
            }
            for pid in range(10)
        ],
        "context": {"channels": {"hero_visibility_events": [], "combat_log": []}},
    }


def frame(second):
    points = {0: [22384, 10384], 1: [21384, 9884], 5: [10384, 22384], 6: [10384, 21384]}
    return {
        "t": second,
        "heroes": [
            {
                "hero": f"hero{pid}",
                "player_id": pid,
                "team": 2 if pid < 5 else 3,
                "life_state": 0,
                "pos": points.get(pid, [16384, 16384]),
                "items": {"unused": "full inventory is not retained"},
            }
            for pid in range(10)
        ],
        "world": {"lane_fronts": {"radiant_bot": {"count": 2, "front": [22384, 10384]}}},
    }


def visibility(second, radiant="visible", dire="visible", hero="hero5"):
    return {
        "time": second,
        "payload": {"hero_name": hero, "radiant_state": radiant, "dire_state": dire},
    }


def combat(second, kind="DAMAGE", **fields):
    return {
        "time": second,
        "payload": {"log_type": kind, "attacker_name": "hero0", "target_name": "hero5", **fields},
    }


def project(value=None, rows=None):
    value = value or parsed()
    return project_match(
        value,
        rows if rows is not None else (frame(t) for t in range(value["duration"] + 1)),
        source_key=SOURCE,
    )


def test_complete_projection_uses_game_end_and_detaches_retained_values():
    value, rows = parsed(), [frame(t) for t in range(3)]
    value_before, rows_before = deepcopy(value), deepcopy(rows)
    key = {"manifest": "a" * 64, "nested": {"match": 123}}
    result = project_match(value, iter(rows), source_key=key)
    assert set(result) == {"key", "tracks", "seen", "positions", "combat", "fronts", "last"}
    assert result["last"] == 2 and set(result["fronts"]) == {0, 1, 2}
    assert result["tracks"]["hero0"] == {
        "team": 2,
        "player_id": 0,
        "pos": {t: (22384, 10384) for t in range(3)},
    }
    assert value == value_before and rows == rows_before
    key["nested"]["match"] = 999
    rows[0]["world"]["lane_fronts"]["radiant_bot"]["front"][0] = 0
    rows[0]["heroes"][0]["pos"][0] = 0
    assert result["key"]["nested"]["match"] == 123
    assert result["fronts"][0]["radiant_bot"]["front"] == [22384, 10384]
    assert result["tracks"]["hero0"]["pos"][0] == (22384, 10384)


def test_negative_visibility_initialization_and_last_second_are_preserved():
    value = parsed()
    value["context"]["channels"]["hero_visibility_events"] = [
        visibility(-10),
        visibility(1, "hidden"),
        visibility(3, "visible", "hidden"),
    ]
    result = project(value)
    assert result["seen"] == {("hero5", 2): {0}, ("hero5", 3): {0, 1, 2}}
    value["context"]["channels"]["hero_visibility_events"][-1] = visibility(99999999, "hidden")
    assert project(value)["seen"] == result["seen"]


def test_only_pre_game_sighting_with_later_hide_does_not_leave_empty_seen_key():
    value = parsed()
    value["context"]["channels"]["hero_visibility_events"] = [
        visibility(-10),
        visibility(-1, "hidden", "unknown"),
    ]
    assert project(value)["seen"] == {}


def test_combat_projection_keeps_existing_fields_and_excludes_outside_window():
    value = parsed()
    kept = [
        combat(0, value=10, tick=1, attacker_is_illusion=False, source_tick=3),
        combat(1, "DEATH", target_name="tower"),
        combat(1, "ABILITY", inflictor_name="spell"),
        combat(2, "ITEM", inflictor_name="item_blink"),
        combat(2, "MODIFIER_ADD", inflictor_name=SMOKE_MODIFIER),
    ]
    value["context"]["channels"]["combat_log"] = [
        combat(-1),
        *kept,
        combat(3),
        combat(1, "GOLD"),
        combat(1, attacker_name="creep_a", target_name="creep_b"),
        combat(1, "MODIFIER_ADD", inflictor_name="modifier_stun"),
    ]
    result = project(value)
    assert len(result["combat"]) == 5
    assert [event["time"] for event in result["combat"]] == [0, 1, 1, 2, 2]
    assert result["combat"][0]["payload"]["attacker_is_illusion"] is False
    assert "source_tick" not in result["combat"][0]["payload"]


def test_unchanged_safelane_rule_uses_fifteen_minute_last_hits_and_missing_is_unknown():
    value = parsed(901)
    value["players"][0]["economy_log"].append({"time": 901, "last_hits": 1000})
    value["players"][1]["economy_log"].append({"time": 901, "last_hits": 2000})
    positions = project(value)["positions"]
    assert positions["hero0"] == 1 and positions["hero1"] == 5
    assert positions["hero5"] is None and positions["hero6"] is None
    value["players"][0]["economy_log"][0]["last_hits"] = None
    positions = project(value)["positions"]
    assert positions["hero0"] is None and positions["hero1"] is None


def test_dead_and_unlocated_hero_seconds_are_not_track_positions():
    rows = [frame(t) for t in range(3)]
    rows[1]["heroes"][0]["life_state"] = 2
    rows[2]["heroes"][0]["pos"] = None
    result = project(rows=rows)
    assert result["tracks"]["hero0"]["pos"] == {0: (22384, 10384)}


def test_stream_is_consumed_once_without_copying_whole_state_payloads():
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise AssertionError("unused state payload was copied")

    class Once:
        def __init__(self):
            self.iterated = False

        def __iter__(self):
            assert not self.iterated
            self.iterated = True
            for second in range(3):
                row = frame(second)
                row["heroes"][0]["items"] = Uncopyable()
                row["world"]["summons"] = Uncopyable()
                yield row

    assert project(rows=Once())["last"] == 2


@pytest.mark.parametrize(
    "seconds",
    [
        [],
        [1, 2],
        [0, 2],
        [0, 1],
        [0, 1, 1, 2],
        [0, 1, 2, 3],
        [-1, 0, 1, 2],
        [0, True, 2],
        [0, 1.0, 2],
    ],
)
def test_incomplete_duplicate_out_of_order_or_outside_state_is_rejected(seconds):
    with pytest.raises(ValueError, match="0..duration"):
        project(rows=(frame(second) for second in seconds))


@pytest.mark.parametrize("duration", [True, 0, -1, 1.0, "2", 86401, None])
def test_duration_requires_a_bounded_integer(duration):
    value = parsed()
    value["duration"] = duration
    with pytest.raises(ValueError, match="duration"):
        project(value, rows=[])


@pytest.mark.parametrize(
    "field,bad",
    [
        ("player_id", True),
        ("player_id", 0.0),
        ("team", True),
        ("team", 3),
        ("life_state", False),
        ("life_state", 3),
        ("pos", [True, 0]),
        ("pos", [float("inf"), 0]),
        ("pos", [10**400, 0]),
        ("pos", [0]),
        ("hero", ""),
    ],
)
def test_state_identity_and_numeric_types_are_strict(field, bad):
    rows = [frame(t) for t in range(3)]
    rows[1]["heroes"][0][field] = bad
    with pytest.raises(ValueError):
        project(rows=rows)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda heroes: heroes.pop(),
        lambda heroes: heroes.__setitem__(1, deepcopy(heroes[0])),
        lambda heroes: heroes[0].update(hero="replacement"),
    ],
)
def test_missing_duplicate_or_changing_hero_identity_is_rejected(mutate):
    rows = [frame(t) for t in range(3)]
    mutate(rows[1]["heroes"])
    with pytest.raises(ValueError):
        project(rows=rows)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("time", True),
        ("time", 1.0),
        ("time", -1),
        ("last_hits", True),
        ("last_hits", "10"),
        ("last_hits", float("nan")),
        ("last_hits", 10**400),
        ("last_hits", -1),
    ],
)
def test_economy_numeric_types_are_strict(field, bad):
    value = parsed()
    value["players"][0]["economy_log"][0][field] = bad
    with pytest.raises(ValueError):
        project(value)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("value", True),
        ("value", float("nan")),
        ("value", 10**400),
        ("tick", True),
        ("attacker_is_hero", 1),
        ("attacker_name", []),
    ],
)
def test_combat_projection_rejects_invalid_used_field_types(field, bad):
    value = parsed()
    value["context"]["channels"]["combat_log"] = [combat(1, **{field: bad})]
    with pytest.raises(ValueError):
        project(value)


@pytest.mark.parametrize(
    "bad",
    [
        visibility(True),
        visibility(-3601),
        visibility(1, "invalid"),
        visibility(1, hero="untracked"),
    ],
)
def test_visibility_event_contract_is_enforced(bad):
    value = parsed()
    value["context"]["channels"]["hero_visibility_events"] = [bad]
    with pytest.raises(ValueError):
        project(value)


def test_invalid_normalized_structure_and_lane_front_are_rejected():
    value = parsed()
    value["players"][1]["player_slot"] = 0
    with pytest.raises(ValueError, match="slot"):
        project(value)
    value = parsed()
    value["context"]["channels"].pop("combat_log")
    with pytest.raises(ValueError, match="channels"):
        project(value)
    rows = [frame(t) for t in range(3)]
    rows[0]["world"]["lane_fronts"]["radiant_bot"]["count"] = True
    with pytest.raises(ValueError, match="lane front"):
        project(rows=rows)
