"""Quality admission checks identity, observed completion and complete game seconds."""

from copy import deepcopy

import pytest

from dota_items.data.replay_quality import ChannelAudit, inspect_base, quality_result


def base_inputs():
    players = [
        {"player_slot": slot, "hero_id": index + 1}
        for index, slot in enumerate([*range(5), *range(128, 133)])
    ]
    meta = {"match_id": 9_100_000_001, "duration": 900, "players": players}
    normalized = {
        **deepcopy(meta),
        "context": {
            "channels": {
                "coach_state_snapshots": [{"time": 1}],
                "combat_log": [{"time": 1}],
                "hero_visibility_events": [],
                "entity_visibility_events": [],
                "wards": [],
            }
        },
    }
    parser = {
        "match_id": meta["match_id"],
        "game_build": 6993,
        "game_start_tick": 10,
        "post_game_tick": 27010,
        "post_game_seconds": 901,
        "parse_error": None,
        "truncated_at_tick": None,
    }
    return normalized, parser, meta


def state_row(t):
    return {
        "t": t,
        "heroes": [
            {
                "player_id": pid,
                "hp": 100,
                "max_hp": 100,
                "mana": 50,
                "max_mana": 50,
                "level": 1,
                "pos": [100, 200],
                "abilities": [{"name": "ability", "cd": 0, "cd_len": 10}],
                "items": {"0": {"name": "item", "cd": 0, "cd_len": 30}},
            }
            for pid in range(10)
        ],
    }


def extras_row(t):
    return {"t": t, "creeps": [], "watchers": [], "outposts": [], "scan": {}}


def audit(kind, rows, duration=2):
    subject = ChannelAudit(kind, duration)
    decisions = [subject.accept(row) for row in rows]
    return subject.finish(), decisions


def test_observed_identity_and_completion_pass_without_model_support_claim():
    normalized, parser, meta = base_inputs()
    base = inspect_base(normalized, parser, meta)
    state, _ = audit("state", [state_row(t) for t in range(3)])
    extras, _ = audit("extras", [extras_row(t) for t in range(3)])
    combined = quality_result(base, state, extras)
    assert combined["status"] == "passed"
    assert combined["training_allowed"] is False
    assert combined["base"]["observed_build"] == 6993
    assert combined["base"]["channels"]["wards"] == 0
    assert combined["state"]["ten_hero_rows"] == 3


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("match_id", 9_100_000_002, "match_identity_mismatch"),
        ("game_build", None, "missing_observed_build"),
        ("game_build", True, "missing_observed_build"),
        ("game_build", 0, "missing_observed_build"),
        ("parse_error", "decode error", "parser_incomplete"),
        ("truncated_at_tick", 30000, "parser_incomplete"),
        ("post_game_tick", None, "missing_game_end"),
        ("post_game_tick", 10, "missing_game_end"),
        ("game_start_tick", True, "missing_game_end"),
        ("post_game_seconds", None, "end_time_disagreement"),
        ("post_game_seconds", float("nan"), "end_time_disagreement"),
        ("post_game_seconds", float("inf"), "end_time_disagreement"),
        ("post_game_seconds", 903, "end_time_disagreement"),
    ],
)
def test_parser_facts_cannot_be_replaced_by_successful_process_exit(field, value, reason):
    normalized, parser, meta = base_inputs()
    parser[field] = value
    assert reason in inspect_base(normalized, parser, meta)["errors"]


@pytest.mark.parametrize("change", ["id", "duration", "hero", "slot", "short", "bool_hero"])
def test_normalized_identity_and_duration_must_match_metadata(change):
    normalized, parser, meta = base_inputs()
    if change == "id":
        normalized["match_id"] += 1
    elif change == "duration":
        normalized["duration"] += 1
    elif change == "hero":
        normalized["players"][0]["hero_id"] = 99
    elif change == "slot":
        normalized["players"][0]["player_slot"] = 1
    elif change == "short":
        normalized["players"].pop()
    else:
        normalized["players"][0]["hero_id"] = True
    assert inspect_base(normalized, parser, meta)["errors"]


@pytest.mark.parametrize("channel", ["combat_log", "coach_state_snapshots", "wards"])
def test_absent_channel_does_not_become_known_empty(channel):
    normalized, parser, meta = base_inputs()
    normalized["context"]["channels"][channel] = None
    result = inspect_base(normalized, parser, meta)
    assert "missing_channel:" + channel in result["errors"]
    normalized["context"]["channels"][channel] = []
    result = inspect_base(normalized, parser, meta)
    if channel == "wards":
        assert not result["errors"]
    else:
        assert "empty_channel:" + channel in result["errors"]


@pytest.mark.parametrize("context", [None, [], {"channels": None}])
def test_malformed_base_context_fails_with_explicit_validation(context):
    normalized, parser, meta = base_inputs()
    normalized["context"] = context
    try:
        result = inspect_base(normalized, parser, meta)
    except ValueError:
        return
    assert result["errors"]


@pytest.mark.parametrize("kind,factory", [("state", state_row), ("extras", extras_row)])
def test_only_complete_game_seconds_are_admitted_and_outside_rows_are_excluded(kind, factory):
    rows = [{"t": -2}, {"t": -1}, *[factory(t) for t in range(3)], {"t": 3}, {"t": 10}]
    result, keep = audit(kind, rows)
    assert keep == [False, False, True, True, True, False, False]
    assert result["total_rows"] == 7
    assert result["in_game_rows"] == 3
    assert result["excluded_rows"] == 4
    assert not result["errors"]


@pytest.mark.parametrize("times", [[1, 2], [0, 2], [0, 1], [], [-1, 3]])
@pytest.mark.parametrize("kind,factory", [("state", state_row), ("extras", extras_row)])
def test_missing_beginning_middle_or_end_never_passes(kind, factory, times):
    result, _ = audit(kind, [factory(t) for t in times])
    assert "missing_in_game_seconds" in result["errors"]


@pytest.mark.parametrize("times", [[0, 0, 1], [1, 0], [0, 1.0], [True], [-1, -1]])
def test_duplicate_backward_and_noninteger_seconds_are_rejected(times):
    with pytest.raises(ValueError, match="strictly increasing integers"):
        audit("state", [state_row(t) for t in times])


@pytest.mark.parametrize("change", ["missing", "duplicate", "bool"])
def test_each_in_game_state_frame_requires_ten_canonical_players(change):
    rows = [state_row(t) for t in range(3)]
    if change == "missing":
        rows[1]["heroes"].pop()
    elif change == "duplicate":
        rows[1]["heroes"][-1]["player_id"] = 0
    else:
        rows[1]["heroes"][0]["player_id"] = False
    result, _ = audit("state", rows)
    assert "incomplete_hero_frame" in result["errors"]
    assert result["ten_hero_rows"] == 2


@pytest.mark.parametrize("field", ["hp", "max_hp", "mana", "max_mana", "level", "pos"])
def test_a_core_hero_null_requires_review_instead_of_zero_imputation(field):
    rows = [state_row(t) for t in range(3)]
    rows[1]["heroes"][0][field] = None
    result, _ = audit("state", rows)
    assert result["field_missing"]["hero." + field] == 1
    assert "missing_core_field:hero." + field in result["errors"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("hp", True),
        ("mana", "unknown"),
        ("max_hp", float("inf")),
        ("level", float("nan")),
        ("pos", [1]),
        ("pos", [1, 2, 3]),
        ("pos", [1, None]),
        ("pos", [1, float("nan")]),
        ("pos", "1,2"),
    ],
)
def test_nonfinite_or_malformed_hero_values_do_not_pass_presence_checks(field, value):
    rows = [state_row(t) for t in range(3)]
    rows[1]["heroes"][0][field] = value
    result, _ = audit("state", rows)
    assert "invalid_core_field:hero." + field in result["errors"]


@pytest.mark.parametrize("container", ["abilities", "items"])
def test_null_or_unavailable_cooldown_container_is_rejected(container):
    row = state_row(0)
    row["heroes"][0][container] = None
    with pytest.raises(ValueError, match="containers"):
        audit("state", [row])


@pytest.mark.parametrize("kind", ["ability", "item"])
@pytest.mark.parametrize("field", ["cd", "cd_len"])
def test_missing_cooldown_is_preserved_as_missing_and_requires_review(kind, field):
    rows = [state_row(t) for t in range(3)]
    hero = rows[1]["heroes"][0]
    record = hero["abilities"][0] if kind == "ability" else hero["items"]["0"]
    record.pop(field)
    result, _ = audit("state", rows)
    assert result["field_missing"][kind + "." + field] == 1
    assert "missing_core_field:" + kind + "." + field in result["errors"]


@pytest.mark.parametrize("kind", ["ability", "item"])
@pytest.mark.parametrize(
    "field,value",
    [("cd", float("nan")), ("cd_len", "10"), ("cd", True), ("name", ""), ("name", False)],
)
def test_recorded_but_invalid_cooldown_fields_require_review(kind, field, value):
    rows = [state_row(t) for t in range(3)]
    hero = rows[1]["heroes"][0]
    record = hero["abilities"][0] if kind == "ability" else hero["items"]["0"]
    record[field] = value
    result, _ = audit("state", rows)
    assert "invalid_core_field:" + kind + "." + field in result["errors"]


@pytest.mark.parametrize("bad", ["row", "hero", "ability", "item"])
def test_invalid_record_containers_raise_validation_errors(bad):
    row = state_row(0)
    if bad == "row":
        row = None
    elif bad == "hero":
        row["heroes"][0] = None
    elif bad == "ability":
        row["heroes"][0]["abilities"][0] = None
    else:
        row["heroes"][0]["items"]["0"] = None
    with pytest.raises(ValueError):
        audit("state", [row])


def test_talent_without_cooldown_is_not_treated_as_a_missing_active_ability():
    rows = [state_row(t) for t in range(3)]
    for row in rows:
        row["heroes"][0]["abilities"].append({"name": "special_bonus_health_100"})
    result, _ = audit("state", rows)
    assert not result["errors"]
    assert result["field_observations"]["ability.cd"] == 30


@pytest.mark.parametrize("field", ["creeps", "watchers", "outposts", "scan"])
def test_extras_distinguishes_recorded_empty_from_unavailable(field):
    rows = [extras_row(t) for t in range(3)]
    rows[1].pop(field)
    result, _ = audit("extras", rows)
    assert "missing_" + field in result["errors"]
    rows[1] = extras_row(1)
    result, _ = audit("extras", rows)
    assert not result["errors"]


def test_one_bad_channel_keeps_combined_result_in_review():
    base = inspect_base(*base_inputs())
    state, _ = audit("state", [state_row(t) for t in range(3)])
    extras, _ = audit("extras", [extras_row(0), extras_row(2)])
    result = quality_result(base, state, extras)
    assert result["status"] == "review_required"
    assert result["training_allowed"] is False
    assert "missing_in_game_seconds" in result["errors"]
