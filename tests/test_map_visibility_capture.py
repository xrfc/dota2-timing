"""Vision capture preserves observed fields without inventing current visibility."""

import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest

from dota_items.data.patch_terrain import visibility_observations
from dota_items.sources.map_visibility_capture import VisibilityCollector, capture


class Entity:
    def __init__(self, classname="CDOTA_Unit_Hero_Test", index=65, serial=2, **overrides):
        self.classname, self.index, self.serial, self.active = classname, index, serial, True
        self.fields = {
            "m_iDayTimeVisionRange": 1800,
            "m_iNightTimeVisionRange": 800,
            "m_iHealth": 400,
            "m_iTeamNum": 2,
            "m_lifeState": 0,
            "m_nPlayerID": 0,
            "m_iPlayerID": None,
            "CBodyComponent.m_cellX": 128,
            "CBodyComponent.m_cellY": 128,
            "CBodyComponent.m_vecX": 230.0,
            "CBodyComponent.m_vecY": 20.0,
            **overrides,
        }
        self.cls = SimpleNamespace(
            serializer=SimpleNamespace(
                _resolve_field=lambda name: SimpleNamespace(
                    path=(0,) if name in self.fields else None
                )
            )
        )

    def get_index(self):
        return self.index

    def get_serial(self):
        return self.serial

    def get_class_name(self):
        return self.classname

    def get(self, name):
        return self.fields.get(name)

    get_int32 = get
    get_uint32 = get
    get_float32 = get


def setup():
    hero = Entity()
    radiant = Entity("CDOTADataRadiant", index=2, **{"m_bNPCVisibleState.0001": 2})
    dire = Entity("CDOTA_DataDire", index=3, **{"m_bNPCVisibleState.0001": 0})
    rules = Entity("CDOTAGamerulesProxy", index=4, **{"m_pGameRules.m_iNetTimeOfDay": 16387})
    entities = {entity.classname: entity for entity in (hero, radiant, dire, rules)}
    parser = SimpleNamespace(
        tick=8,
        post_game_tick=60,
        game_time_s=0,
        entity_manager=SimpleNamespace(find_by_class_name=entities.get),
        game_clock=SimpleNamespace(
            game_time_at=lambda tick: tick / 30 - 0.25,
            game_start_time_s=0.25,
            net_tick_offset=0,
        ),
    )
    players = SimpleNamespace(
        _canonical_hero_entity=lambda pid: hero if pid == 0 else None,
        _hero_handle_for_player=lambda pid: 65601 if pid == 0 else None,
    )
    return parser, players, hero, entities


def document():
    parser, players, _, _ = setup()
    collector = VisibilityCollector(parser, players)
    collector.on_tick_start(8)
    return {
        "schema": "map-visibility-capture/1",
        "coordinate_space": "world",
        "match_id": 123,
        "game_build": 6993,
        "post_game_tick": parser.post_game_tick,
        "parse_error": None,
        "truncated_at_tick": None,
        **collector.result(),
    }


def test_capture_uses_canonical_handle_and_real_fields_with_unverified_daycycle():
    parser, players, _, _ = setup()
    collector = VisibilityCollector(parser, players)
    collector.on_tick_start(8)
    result = collector.result()
    frame = result["frames"][0]
    hero = frame["heroes"][0]
    assert (hero["x"], hero["y"]) == (230, 20)  # vector offsets can exceed 128
    assert (hero["entity_handle"], hero["entity_index"], hero["entity_serial"]) == (65601, 65, 2)
    assert hero["day_vision_range"] == 1800
    assert hero["night_vision_range"] == 800
    assert hero["current_vision_range"] is None
    assert hero["visibility"] == {"radiant": True, "dire": False}
    assert hero["vismask"] == 1
    assert hero["visibility_words"] == {"radiant": 2, "dire": 0}
    assert frame["missing_player_ids"] == list(range(1, 10))
    assert frame["time_of_day_raw"] == 16387
    assert frame["daycycle"] == {
        "phase": None,
        "status": "raw_encoding_unverified",
        "fixed_cycle_seconds_assumed": None,
    }
    assert result["field_schemas"][hero["class_name"]]["m_iCurrentVisionRange"] is False


def test_seconds_are_exact_clock_buckets_not_rounded_display_clock_and_no_future_frames():
    parser, players, _, _ = setup()
    collector = VisibilityCollector(parser, players)
    for tick in (0, 8, 30, 38, 60, 61):
        parser.tick = tick
        collector.on_tick_start(tick)
    result = collector.result()
    assert [frame["tick"] for frame in result["frames"]] == [0, 8, 38]
    assert [frame["t"] for frame in result["frames"]] == [-1, 0, 1]
    assert result["sampling"]["pre_game_frames"] == 1
    assert result["sampling"]["missing_game_seconds"] == []
    assert result["sampling"]["skipped"]["post_game_ticks"] == 1


def test_pause_does_not_add_duplicate_seconds_and_missing_seconds_stay_explicit():
    parser, players, _, _ = setup()
    parser.game_clock.game_time_at = lambda tick: 0.1 if tick < 45 else 3.1
    collector = VisibilityCollector(parser, players)
    for tick in (8, 30, 45, 60):
        parser.tick = tick
        collector.on_tick_start(tick)
    assert [frame["tick"] for frame in collector.result()["frames"]] == [8, 45]
    assert collector.result()["sampling"]["missing_game_seconds"] == [1, 2]


def test_open_pause_clock_then_closed_interval_cannot_reserve_future_game_seconds():
    parser, players, _, _ = setup()
    parser.post_game_tick = 300
    closed = False

    def time_at(tick):
        paused = min(max(tick - 60, 0), 120) if closed else 0
        return (tick - paused) / 30

    parser.game_clock.game_time_at = time_at
    collector = VisibilityCollector(parser, players)
    for tick in range(301):
        if tick == 180:
            closed = True
        parser.tick = tick
        collector.on_tick_start(tick)
    first = collector.result()
    assert [frame["t"] for frame in first["frames"]] == list(range(7))
    assert first["sampling"]["missing_game_seconds"] == []
    assert first["sampling"]["skipped"]["final_clock_bucket_changes"] > 0
    assert collector.result() == first


def test_pause_still_open_at_parse_end_is_regrouped_from_final_clock():
    parser, players, _, _ = setup()
    parser.post_game_tick = 180
    parser.game_clock.game_time_at = lambda tick: tick / 30
    collector = VisibilityCollector(parser, players)
    for tick in range(181):
        parser.tick = tick
        collector.on_tick_start(tick)
    parser.game_clock.game_time_at = lambda tick: min(tick, 60) / 30
    result = collector.result()
    assert [frame["t"] for frame in result["frames"]] == [0, 1, 2]
    assert result["sampling"]["missing_game_seconds"] == []


def test_final_partial_second_is_kept_even_before_next_periodic_candidate():
    parser, players, _, _ = setup()
    parser.post_game_tick = 61
    parser.game_clock.game_time_at = lambda tick: tick / 30 - 0.01
    collector = VisibilityCollector(parser, players)
    for tick in range(62):
        parser.tick = tick
        collector.on_tick_start(tick)
    result = collector.result()
    assert result["frames"][-1]["t"] == 2
    assert result["frames"][-1]["tick"] == 61
    assert result["sampling"]["missing_game_seconds"] == []


def test_unknown_live_clock_retains_raw_tick_candidates_for_final_pregame_alignment():
    parser, players, _, _ = setup()
    parser.game_clock.game_time_at = lambda _: None
    collector = VisibilityCollector(parser, players)
    for tick in range(61):
        parser.tick = tick
        collector.on_tick_start(tick)
    parser.game_clock.game_time_at = lambda tick: tick / 30 - 1
    result = collector.result()
    assert [frame["t"] for frame in result["frames"]] == [-1, 0, 1]
    assert result["sampling"]["skipped"]["initial_clock_unknown_candidates"] == 5


def test_end_marker_learned_after_sampling_still_excludes_future_rows():
    parser, players, _, _ = setup()
    parser.post_game_tick = None
    collector = VisibilityCollector(parser, players)
    for tick in (8, 68):
        parser.tick = tick
        collector.on_tick_start(tick)
    parser.post_game_tick = 60
    assert [frame["tick"] for frame in collector.result()["frames"]] == [8]


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf")])
def test_bad_coordinates_remain_missing_instead_of_default_origin(value):
    parser, players, hero, _ = setup()
    hero.fields["CBodyComponent.m_vecY"] = value
    collector = VisibilityCollector(parser, players)
    collector.on_tick_start(8)
    row = collector.result()["frames"][0]["heroes"][0]
    assert row["x"] is row["y"] is None
    assert row["missing_coordinate_fields"] == ["vec_y"]


def test_missing_team_word_is_unknown_not_hidden_and_tagged_field_is_not_substituted():
    parser, players, hero, entities = setup()
    entities.pop("CDOTA_DataDire")
    hero.fields["m_iTaggedAsVisibleByTeam"] = 0
    collector = VisibilityCollector(parser, players)
    collector.on_tick_start(8)
    row = collector.result()["frames"][0]["heroes"][0]
    assert row["visibility"] == {"radiant": True, "dire": None}
    assert row["vismask"] is None
    assert row["raw_fields"]["m_iTaggedAsVisibleByTeam"] == 0


@pytest.mark.parametrize("word", [True, -1, 2**64, "2", 2.0])
def test_invalid_visibility_word_is_reported_not_decoded(word):
    parser, players, _, entities = setup()
    entities["CDOTA_DataDire"].fields["m_bNPCVisibleState.0001"] = word
    collector = VisibilityCollector(parser, players)
    collector.on_tick_start(8)
    row = collector.result()["frames"][0]["heroes"][0]
    assert row["visibility"]["dire"] is None
    assert row["vismask"] is None
    assert row["invalid_visibility_words"] == ["dire"]


def test_missing_rules_clock_and_body_are_reported_without_creating_evidence():
    parser, players, _, entities = setup()
    entities.pop("CDOTAGamerulesProxy")
    players._canonical_hero_entity = lambda _: None
    collector = VisibilityCollector(parser, players)
    collector.on_tick_start(8)
    frame = collector.result()["frames"][0]
    assert frame["time_of_day_raw"] is frame["time_of_day_field_present"] is None
    assert frame["heroes"] == []
    assert frame["missing_player_ids"] == list(range(10))
    parser.game_clock.game_time_at = lambda _: None
    assert collector.result()["frames"] == []
    assert collector.result()["sampling"]["missing_game_seconds"] is None


def test_visibility_summary_validates_recorded_bits_but_returns_unknown_current_los():
    result = visibility_observations(document())
    assert result["observations"] == []
    assert result["unknowns"] == {"current_range_unknown": 1}
    assert result["summary"]["field_coverage"]["day_vision_range"] == {
        "known": 1,
        "missing": 0,
        "denominator": 1,
    }
    assert result["summary"]["field_coverage"]["current_vision_range"]["missing"] == 1
    assert result["summary"]["field_coverage"]["verified_time_phase"]["known"] == 0
    assert result["summary"]["missing_player_samples"] == 9
    assert result["actual_fog_of_war"] is result["accuracy_claimed"] is False


@pytest.mark.parametrize(
    "change,match",
    [
        ({"vismask": 0}, "vismask"),
        ({"vismask": True}, "vismask"),
        ({"visibility": {"radiant": False, "dire": False}}, "team word"),
        ({"visibility_bit_index": 2}, "index evidence"),
        ({"day_vision_range": -1}, "negative vision"),
    ],
)
def test_summary_rejects_forged_or_corrupt_visibility_fields(change, match):
    data = document()
    data["frames"][0]["heroes"][0].update(change)
    with pytest.raises(ValueError, match=match):
        visibility_observations(data)


@pytest.mark.parametrize("mutation", ["duplicate_frame", "duplicate_hero", "future", "phase"])
def test_summary_rejects_duplicate_future_or_invented_phase(mutation):
    data = document()
    if mutation == "duplicate_frame":
        data["frames"].append(deepcopy(data["frames"][0]))
    elif mutation == "duplicate_hero":
        data["frames"][0]["heroes"].append(deepcopy(data["frames"][0]["heroes"][0]))
    elif mutation == "future":
        data["frames"][0]["tick"] = 61
    else:
        data["frames"][0]["daycycle"]["phase"] = "day"
    with pytest.raises(ValueError):
        visibility_observations(data)


def test_summary_bounds_examples_and_excludes_pre_game_from_field_denominators():
    data = document()
    base = data["frames"][0]
    data["post_game_tick"] = 600
    data["frames"] = [
        {**deepcopy(base), "t": second, "tick": (second + 1) * 30, "game_time": second + 0.1}
        for second in range(-1, 10)
    ]
    result = visibility_observations(data)
    assert len(result["unknown_examples"]) == 8
    assert result["unknowns"] == {"current_range_unknown": 10}
    assert result["summary"]["mask_rows_checked"] == 11
    assert result["summary"]["field_coverage"]["vismask"]["denominator"] == 10


@pytest.mark.parametrize(
    "overrides",
    [
        {"match_id": 0},
        {"game_build": True},
        {"post_game_tick": None},
        {"parse_error": "bad"},
        {"truncated_at_tick": 12},
    ],
)
def test_capture_requires_complete_parse_identity_and_end(monkeypatch, overrides):
    class Parser:
        def __init__(self, _path):
            self.match_id, self.game_build, self.post_game_tick = 123, 6993, 60
            self.parse_error = self.truncated_at_tick = None
            self.__dict__.update(overrides)

        def on_tick_start(self, callback):
            self.callback = callback

        def parse(self):
            pass

    monkeypatch.setitem(sys.modules, "gem.parser", SimpleNamespace(ReplayParser=Parser))
    monkeypatch.setitem(
        sys.modules,
        "gem.extractors.players",
        SimpleNamespace(
            PlayerExtractor=lambda: SimpleNamespace(attach=lambda _: None),
        ),
    )
    with pytest.raises(ValueError):
        capture("test.dem")
