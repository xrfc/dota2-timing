"""New completed-packet capture preserves raw fields, clocks and identities."""

from enum import IntFlag
from types import SimpleNamespace

import pytest

from dota_items.sources.map_vision_evidence import (
    STATE_COLUMNS,
    VisionEvidenceCollector,
    _table,
    _walk,
)


class Op(IntFlag):
    CREATED = 1
    UPDATED = 2
    DELETED = 4
    ENTERED = 8
    LEFT = 16

    def has(self, other):
        return bool(self & other)


def field(name, *, model=0, children=None, count=None):
    return SimpleNamespace(
        var_name=name,
        var_type="uint64" if "State" in name else "int32",
        encoder=None,
        encode_flags=0,
        bit_count=None,
        low_value=None,
        high_value=None,
        model=model,
        field_type=SimpleNamespace(count=count),
        serializer=None if children is None else SimpleNamespace(fields=children),
    )


class Entity:
    def __init__(self, name, index, serial=2, *, values=None, fields=None):
        self.name, self.index, self.serial = name, index, serial
        self.active = True
        self.values = {} if values is None else values
        self.cls = SimpleNamespace(serializer=SimpleNamespace(fields=fields or []))

    def get_class_name(self):
        return self.name

    def get_index(self):
        return self.index

    def get_serial(self):
        return self.serial

    def get(self, name):
        return self.values.get(name)

    get_uint32 = get
    get_int32 = get
    get_float32 = get


def setup():
    hero = Entity(
        "CDOTA_Unit_Hero_Test",
        65,
        values={
            "m_iDayTimeVisionRange": 1800,
            "m_iNightTimeVisionRange": 800,
            "m_iHealth": 400,
            "m_iTeamNum": 2,
            "m_lifeState": 0,
            "m_bIsWaitingToSpawn": False,
            "m_iUnitNameStringTableIndex": 3,
            "CBodyComponent.m_cellX": 128,
            "CBodyComponent.m_cellY": 128,
            "CBodyComponent.m_vecX": 230.0,
            "CBodyComponent.m_vecY": 20.0,
        },
        fields=[field("m_iDayTimeVisionRange"), field("m_iNightTimeVisionRange")],
    )
    teams = [
        Entity(
            cls,
            index,
            values={
                "m_bNPCVisibleState.0001": word,
                "m_bWorldTreeState.0000": tree,
                "m_bWorldTreeState.0001": None,
            },
            fields=[
                field("m_bNPCVisibleState", model=1, count=256),
                field("m_bWorldTreeState", model=1, count=2),
            ],
        )
        for cls, index, word, tree in (
            ("CDOTA_DataRadiant", 2, 2, 5),
            ("CDOTA_DataDire", 3, 0, 7),
            ("CDOTA_DataSpectator", 4, 2, 9),
        )
    ]
    rules = Entity(
        "CDOTAGamerulesProxy",
        5,
        values={
            "m_pGameRules.m_iNetTimeOfDay": 16387,
            "m_pGameRules.m_flDaytimeStart": 0.25,
            "m_pGameRules.m_flNighttimeStart": 0.75,
        },
        fields=[
            field(
                "m_pGameRules",
                model=2,
                children=[
                    field("m_iNetTimeOfDay"),
                    field("m_flDaytimeStart"),
                    field("m_flNighttimeStart"),
                ],
            )
        ],
    )
    names = SimpleNamespace(items={3: ("npc_dota_hero_test", None)})
    parser = SimpleNamespace(
        tick=0,
        post_game_tick=60,
        entity_manager=SimpleNamespace(find_by_class_name=lambda cls: rules),
        game_clock=SimpleNamespace(game_time_at=lambda tick: tick / 30),
        string_tables=SimpleNamespace(
            get_by_name=lambda name: names if name == "UnitNames" else None
        ),
    )
    players = SimpleNamespace(
        _canonical_hero_entity=lambda pid: hero if pid == 0 else None,
        _hero_handle_for_player=lambda pid: (hero.serial << 14) | hero.index,
    )
    collector = VisionEvidenceCollector(parser, players, Op)
    for entity in (hero, *teams):
        collector.on_entity(entity, Op.CREATED)
    return collector, parser, hero, teams, names


def test_completed_packet_capture_preserves_fields_and_observer_channels():
    collector, parser, hero, teams, _ = setup()
    collector.on_packet_end(0)
    # Updates in the completed packet are read together, not a previous-tick snapshot.
    parser.tick = 30
    hero.values["m_iHealth"] = 390
    teams[0].values["m_bNPCVisibleState.0001"] = 0
    collector.on_packet_end(30)
    result = collector.result()
    assert result["state_columns"] == STATE_COLUMNS
    assert result["states"][0][1:4] == [230.0, 20.0, True]
    assert result["states"][0][8:11] == [1800, 800, None]
    frames = result["frames"]
    assert [frame["t"] for frame in frames] == [0, 1]
    assert frames[0]["canonical_heroes"] == [[0, 0, 32833]]
    assert frames[0]["rules_raw"]["m_pGameRules.m_iNetTimeOfDay"] == 16387
    assert frames[0]["rules_raw"]["m_pGameRules.m_flNighttimeStart"] == 0.75
    words = result["team_word_snapshots"]
    assert words[frames[0]["team_word_refs"]["radiant"]["snapshot_id"]] == [[1, 2]]
    assert words[frames[1]["team_word_refs"]["radiant"]["snapshot_id"]] == [[1, 0]]
    assert "spectator" not in frames[0]["team_word_refs"]
    assert set(frames[0]["tree_word_refs"]) == {"radiant", "dire", "spectator"}
    assert result["sampling"]["boundary"] == "completed_packet"


def test_state_interning_and_first_seen_identity_do_not_backfill_future_names():
    collector, parser, hero, _, names = setup()
    collector.on_packet_end(0)
    names.items[3] = ("future_name", None)
    parser.tick = 30
    collector.on_packet_end(30)
    result = collector.result()
    assert len(result["states"]) == 1
    assert result["frames"][0]["entity_state_ids"] == result["frames"][1]["entity_state_ids"]
    assert result["entity_catalog"][0]["npc_name_first_seen"] == "npc_dota_hero_test"
    assert hero.index == result["entity_catalog"][0]["entity_index"]


def test_final_pause_clock_regroups_candidates_and_prunes_unused_future_state():
    collector, parser, hero, _, _ = setup()
    parser.post_game_tick = 210
    closed = False

    def time_at(tick):
        # Open pause initially has no end; final clock subtracts the complete interval.
        return (tick - (min(max(tick - 30, 0), 120) if closed else 0)) / 30

    parser.game_clock.game_time_at = time_at
    for tick in range(211):
        parser.tick = tick
        hero.values["m_iHealth"] = 999 if 31 <= tick < 150 else 400
        collector.on_packet_end(tick)
    parser.tick = 211
    hero.values["m_iHealth"] = 777
    collector.on_packet_end(211)
    closed = True
    result = collector.result()
    assert [frame["t"] for frame in result["frames"]] == [0, 1, 2, 3]
    assert [frame["tick"] for frame in result["frames"]] == [0, 30, 180, 210]
    assert result["sampling"]["missing_game_seconds"] == []
    assert len(result["states"]) == 1
    assert result["states"][0][6] == 400
    assert result["sampling"]["skipped"]["post_game_packets"] == 1


def test_unknown_clock_is_not_zero_and_empty_final_capture_is_explicit():
    collector, parser, _, _, _ = setup()
    parser.game_clock.game_time_at = lambda tick: None
    collector.on_packet_end(0)
    result = collector.result()
    assert result["frames"] == result["states"] == result["entity_catalog"] == []
    assert result["sampling"]["missing_game_seconds"] is None


def test_temporary_tree_lifecycle_missing_position_and_reused_index_keep_serial():
    collector, parser, hero, _, _ = setup()
    tree = Entity("CDOTA_TempTree", 65, serial=3)
    parser.tick = 5
    collector.on_entity(tree, Op.CREATED)
    parser.tick = 6
    tree.active = False
    collector.on_entity(tree, Op.DELETED)
    parser.tick = 30
    collector.on_packet_end(30)
    result = collector.result()
    assert len(result["temporary_tree_events"]) == 2
    first, last = result["temporary_tree_events"]
    assert first["entity_id"] == last["entity_id"]
    assert result["entity_catalog"][first["entity_id"]]["entity_serial"] == 3
    assert result["states"][first["state_id"]][1:4] == [None, None, True]
    assert result["states"][last["state_id"]][1:4] == [None, None, False]
    assert all(
        result["states"][sid][0] != first["entity_id"]
        for sid in result["frames"][0]["entity_state_ids"]
    )
    assert hero.serial == 2


@pytest.mark.parametrize("x", [None, float("nan"), True, "bad"])
def test_bad_coordinate_does_not_turn_into_origin(x):
    collector, _, hero, _, _ = setup()
    hero.values["CBodyComponent.m_vecX"] = x
    collector.on_packet_end(0)
    assert collector.result()["states"][0][1:3] == [None, None]


def test_vector_table_preserves_raw_count_children_and_rejects_unbounded_count():
    nested = field("regions", model=4, children=[field("m_vCenter"), field("m_flRadius")])
    entity = Entity(
        "test",
        1,
        values={
            "regions": 1,
            "regions.0000.m_vCenter": [1.0, 2.0, 3.0],
            "regions.0000.m_flRadius": 100.0,
        },
    )
    assert _table(entity, "regions", nested) == {
        "length": 1,
        "rows": [{"m_vCenter": [1.0, 2.0, 3.0], "m_flRadius": 100.0}],
    }
    assert list(_walk(SimpleNamespace(fields=[nested]))) == [("regions", nested)]
    entity.values["regions"] = None
    assert _table(entity, "regions", nested) == {"length": None, "rows": None}
    entity.values["regions"] = 4097
    with pytest.raises(ValueError, match="bound"):
        _table(entity, "regions", nested)
