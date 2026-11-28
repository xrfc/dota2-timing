"""Lifecycle evidence must distinguish precreation, activation, death and disappearance."""

import sys
from enum import IntFlag
from types import SimpleNamespace

import pytest

from dota_items.sources.map_runtime_capture import RuntimeCollector, capture


class Op(IntFlag):
    CREATED = 1
    UPDATED = 2
    DELETED = 4
    LEFT = 16

    def has(self, value):
        return bool(self & value)


class Entity:
    def __init__(self, cls="CDOTA_BaseNPC_Creep_Neutral", index=4, serial=2, **fields):
        self.index, self.serial, self.class_name, self.active = index, serial, cls, True
        self.fields = {
            "m_iUnitNameStringTableIndex": 1,
            "m_pEntity.m_nameStringTableIndex": 2,
            "m_lifeState": 0,
            "m_iTeamNum": 4,
            "m_iHealth": 500,
            "m_hNeutralSpawner": 123,
            "m_bIsWaitingToSpawn": True,
            "CBodyComponent.m_cellX": 128,
            "CBodyComponent.m_cellY": 128,
            "CBodyComponent.m_vecX": 230.0,
            "CBodyComponent.m_vecY": 20.0,
            **fields,
        }
        self.cls = SimpleNamespace(
            serializer=SimpleNamespace(
                _resolve_field=lambda name: SimpleNamespace(
                    path=(0,) if name in self.fields else None
                )
            )
        )

    def get_class_name(self):
        return self.class_name

    def get_index(self):
        return self.index

    def get_serial(self):
        return self.serial

    def get(self, name):
        return self.fields.get(name)

    get_int32 = get
    get_uint32 = get
    get_float32 = get


def parser():
    spawner = Entity("CDOTA_NeutralSpawner", index=5)
    return SimpleNamespace(
        tick=0,
        post_game_tick=300,
        string_tables=SimpleNamespace(
            get_by_name=lambda name: SimpleNamespace(
                items=(
                    {1: ("npc_dota_neutral_radigull", None)}
                    if name == "UnitNames"
                    else {1: ("courier_autodeliver", None), 2: ("npc_dota_creep_neutral", None)}
                )
            )
        ),
        entity_manager=SimpleNamespace(
            find_by_handle=lambda handle: spawner if handle == 123 else None
        ),
        game_clock=SimpleNamespace(
            game_time_at=lambda tick: tick / 30 - 0.25,
            game_start_time_s=0.25,
            net_tick_offset=0,
        ),
    )


def test_precreated_waiting_and_death_preserved_without_every_position_update():
    p, unit = parser(), Entity()
    collector = RuntimeCollector(p, Op)
    collector.on_entity(unit, Op.CREATED)
    p.tick = 30
    unit.fields["CBodyComponent.m_vecX"] = 240
    collector.on_entity(unit, Op.UPDATED)
    p.tick = 60
    unit.fields["m_bIsWaitingToSpawn"] = False
    collector.on_entity(unit, Op.UPDATED)
    p.tick = 90
    unit.fields["m_lifeState"] = 1
    collector.on_entity(unit, Op.UPDATED)
    p.tick = 120
    collector.on_entity(unit, Op.DELETED)
    result = collector.result()
    rows = result["neutral_units"][0]["observations"]
    assert [row["tick"] for row in rows] == [0, 60, 90, 120]
    assert rows[0]["game_time"] == -0.25
    assert rows[0]["npc_name"] == "npc_dota_neutral_radigull"
    assert rows[0]["npc_name_table"] == "UnitNames"
    assert rows[0]["entity_name"] == "npc_dota_creep_neutral"
    assert rows[1]["x"] == 240
    assert rows[0]["spawner_identity"] == [5, 2]
    assert result["field_schemas"][unit.class_name]["m_iCampType"] is False
    assert result["field_coverage"]["neutral_unit"]["missing_fraction"]["m_iCampType"] == 1
    assert result["neutral_units"][0]["deleted_ticks"] == [120]


def test_absent_unit_names_never_falls_back_to_unrelated_entity_name_table():
    p = parser()
    original = p.string_tables.get_by_name
    p.string_tables.get_by_name = lambda name: None if name == "UnitNames" else original(name)
    collector = RuntimeCollector(p, Op)
    collector.on_entity(Entity(), Op.CREATED)
    row = collector.result()["neutral_units"][0]["observations"][0]
    assert row["npc_name"] is None
    assert row["entity_name"] == "npc_dota_creep_neutral"


def test_objective_empty_frames_non_alive_states_and_serial_reuse_are_preserved():
    p = parser()
    collector = RuntimeCollector(p, Op)
    collector.on_tick_start(0)
    p.tick = 30
    unit = Entity("CDOTA_Unit_Miniboss", **{"m_bIsWaitingToSpawn": False})
    collector.on_entity(unit, Op.CREATED)
    collector.on_tick_start(30)
    p.tick = 60
    unit.fields["m_lifeState"] = 1
    collector.on_entity(unit, Op.UPDATED)
    collector.on_tick_start(60)
    p.tick = 90
    collector.on_entity(unit, Op.LEFT)
    collector.on_tick_start(90)
    collector.on_entity(Entity("CDOTA_Unit_Miniboss", serial=3), Op.CREATED)
    result = collector.result()
    assert len(result["objectives"]) == 2
    frames = result["objective_frames"]
    assert frames[0]["tormentor"] == frames[3]["tormentor"] == []
    assert frames[2]["tormentor"][0]["life_state"] == 1


@pytest.mark.parametrize("value", [None, True, float("inf"), float("nan")])
def test_invalid_coordinates_remain_unknown(value):
    collector = RuntimeCollector(parser(), Op)
    collector.on_entity(Entity(**{"CBodyComponent.m_vecX": value}), Op.CREATED)
    row = collector.result()["neutral_units"][0]["observations"][0]
    assert row["x"] is row["y"] is None
    assert "vec_x" in row["missing_coordinate_fields"]


def test_missing_clock_stays_unknown_and_post_game_updates_are_excluded():
    p = parser()
    p.game_clock.game_time_at = lambda _: None
    collector = RuntimeCollector(p, Op)
    collector.on_entity(Entity(), Op.CREATED)
    p.tick = 301
    collector.on_entity(Entity(serial=3), Op.CREATED)
    collector.on_tick_start(301)
    result = collector.result()
    assert len(result["neutral_units"]) == 1
    assert result["neutral_units"][0]["observations"][0]["game_time"] is None
    assert result["objective_frames"] == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"match_id": 0},
        {"game_build": False},
        {"post_game_tick": None},
        {"parse_error": "failed"},
        {"truncated_at_tick": 120},
    ],
)
def test_capture_requires_real_identity_complete_parse_and_end(monkeypatch, overrides):
    class Parser:
        def __init__(self, _path):
            self.match_id, self.game_build, self.post_game_tick = 1, 6993, 300
            self.parse_error = self.truncated_at_tick = None
            self.__dict__.update(overrides)

        def on_entity(self, _callback):
            pass

        def on_tick_start(self, _callback):
            pass

        def parse(self):
            pass

    monkeypatch.setitem(sys.modules, "gem.parser", SimpleNamespace(ReplayParser=Parser))
    monkeypatch.setitem(sys.modules, "gem.state.entities", SimpleNamespace(EntityOp=Op))
    with pytest.raises(ValueError):
        capture("unused.dem")
