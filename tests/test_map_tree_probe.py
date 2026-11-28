"""Raw tree probe boundaries, unknowns and exact wire evidence remain explicit."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from copy import deepcopy
from enum import IntFlag
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

import pytest

from dota_items.sources.map_tree_probe import (
    TreeProbeCollector,
    _encode_storage_field,
    _field_changes,
    _schema,
    _selected,
    _value,
    capture,
    install_raw_combat_hook,
    install_sendtables_hook,
)


class Op(IntFlag):
    CREATED = 1
    UPDATED = 2
    DELETED = 4
    ENTERED = 8
    LEFT = 16

    def has(self, value):
        return bool(self & value)


def field(name, *, kind="uint32", model=0, children=None, count=None):
    return SimpleNamespace(
        var_name=name,
        var_type=kind,
        model=model,
        encoder="fixed64" if "uint64" in kind else "",
        encode_flags=None,
        bit_count=None,
        low_value=None,
        high_value=None,
        serializer=None if children is None else SimpleNamespace(fields=children),
        field_type=SimpleNamespace(count=count),
    )


class Entity:
    def __init__(self, name, index=1, serial=2, *, fields=(), values=None):
        self.name, self.index, self.serial = name, index, serial
        self.active = True
        self.cls = SimpleNamespace(serializer=SimpleNamespace(fields=list(fields)))
        self.values = values or {}

    def get_class_name(self):
        return self.name

    def get_index(self):
        return self.index

    def get_serial(self):
        return self.serial

    def get(self, name):
        return self.values.get(name)


def setup():
    parser = SimpleNamespace(
        tick=0,
        post_game_tick=None,
        game_clock=SimpleNamespace(game_time_at=lambda tick: tick / 30),
        string_tables=SimpleNamespace(get_by_name=lambda name: None),
    )
    players = SimpleNamespace(
        _canonical_hero_entity=lambda pid: None,
        _hero_handle_for_player=lambda pid: None,
    )
    return TreeProbeCollector(parser, players, Op), parser, players


def finish(collector, parser, tick):
    parser.tick = parser.post_game_tick = tick
    collector.on_packet_end(tick)
    return collector.result()


def team(index=2, serial=3, word=None):
    return Entity(
        "CDOTA_DataRadiant",
        index,
        serial,
        fields=[field("m_bWorldTreeState", kind="uint64[2]", model=1, count=2)],
        values={"m_bWorldTreeState.0000": word, "m_bWorldTreeState.0001": 2**63},
    )


def test_same_tick_packets_keep_order_and_terminal_packet_blocks_later_same_tick():
    collector, parser, _ = setup()
    entity = team(word=3)
    collector.on_entity(entity, Op.CREATED)
    collector.on_packet_end(0)
    entity.values["m_bWorldTreeState.0000"] = 4
    collector.on_entity(entity, Op.UPDATED)
    collector.on_packet_end(0)
    result = finish(collector, parser, 0)
    entity.values["m_bWorldTreeState.0000"] = 999
    collector.on_entity(entity, Op.UPDATED)
    collector.raw_combat(Entry({"type": 35, "value": 999}), "direct_hltv")
    collector.on_packet_end(0)
    result = collector.result()
    assert [p["packet_ordinal"] for p in result["packets"]] == [1, 2, 3]
    assert [p["terminal_packet"] for p in result["packets"]] == [False, False, True]
    assert [r["words"] for r in result["tree_word_changes"]] == [
        [[0, 3], [1, 2**63]],
        [[0, 4]],
    ]
    assert result["raw_tree_cut_events"] == []
    assert result["sampling"]["terminal_packet_ordinal"] == 3
    assert result["sampling"]["counts"]["post_game_packet_callbacks"] == 1


def test_initial_missing_word_is_distinct_from_zero_and_identity_serial_reuse():
    collector, parser, _ = setup()
    first = team(word=None)
    collector.on_entity(first, Op.CREATED)
    collector.on_packet_end(0)
    parser.tick = 1
    first.values["m_bWorldTreeState.0000"] = 0
    collector.on_entity(first, Op.UPDATED)
    collector.on_packet_end(1)
    parser.tick = 2
    replacement = team(serial=4, word=0)
    collector.on_entity(replacement, Op.CREATED)
    result = finish(collector, parser, 2)
    a, b, c = result["tree_word_changes"]
    assert a["initial"] is True and a["words"][0] == [0, None]
    assert b["initial"] is False and b["words"] == [[0, 0]]
    assert c["initial"] is True and c["entity_serial"] == 4


@pytest.mark.parametrize("bad", [-1, 2**64, True, 1.0, "1"])
def test_malformed_tree_word_is_not_coerced(bad):
    collector, _, _ = setup()
    collector.on_entity(team(word=bad), Op.CREATED)
    with pytest.raises(ValueError, match="uint64"):
        collector.on_packet_end(0)


def test_final_pause_clock_is_applied_without_flooring_or_deduplication():
    collector, parser, _ = setup()
    for tick in (0, 30, 60, 90):
        parser.tick = tick
        collector.on_packet_end(tick)
    parser.post_game_tick = 90
    parser.game_clock.game_time_at = lambda tick: min(tick, 30) / 30
    result = collector.result()
    assert [p["game_time"] for p in result["packets"]] == [0, 1, 1, 1]
    assert len(result["packets"]) == 4


def test_uncompleted_packet_events_remain_separate_non_consumable_and_result_is_idempotent():
    collector, parser, _ = setup()
    collector.on_packet_end(0)
    parser.tick = 5
    collector.on_entity(Entity("CDOTA_TempTree"), Op.CREATED)
    collector.raw_combat(Entry({"type": 35, "value": 7}), "wrapped_bulk")
    parser.post_game_tick = 10
    result = collector.result()
    assert result["raw_tree_cut_events"] == result["entity_events"] == []
    assert len(result["unresolved_packet_records"]) == 2
    assert all(r["consumer_use_allowed"] is False for r in result["unresolved_packet_records"])
    assert all(r["completed_packet_known"] is False for r in result["unresolved_packet_records"])
    assert collector.result() == result


def test_unknown_game_clock_is_not_imputed_as_zero():
    collector, parser, _ = setup()
    parser.game_clock.game_time_at = lambda tick: None
    assert finish(collector, parser, 0)["packets"][0]["game_time"] is None


def test_full_schema_keeps_unselected_fields_and_empty_vector_children():
    collector, parser, _ = setup()
    vector = field("m_vecWorldTreeModelReplacements", model=4, children=[field("m_nTreeID")])
    entity = Entity(
        "CMapTree",
        fields=[field("m_unrelated"), field("m_szTreeFile", kind="char*"), vector],
        values={"m_szTreeFile": "maps/test.trees", "m_vecWorldTreeModelReplacements": 0},
    )
    collector.on_entity(entity, Op.CREATED)
    result = finish(collector, parser, 0)
    fields = result["class_schemas"]["CMapTree"]["fields"]
    assert fields[0]["var_name"] == "m_unrelated"
    assert fields[2]["children"]["fields"][0]["var_name"] == "m_nTreeID"
    row = result["entity_changes"][0]
    assert row["fields_raw"]["m_vecWorldTreeModelReplacements"] == {"length_raw": 0, "values": []}
    assert row["fields_raw"]["m_szTreeFile"] == "maps/test.trees"


def test_nested_hero_id_type_is_selected_without_assuming_unsigned_decoding():
    hero = field("m_identity", kind="HeroID_t")
    array = field("m_choices", kind="HeroID_t[2]", model=1, count=2)
    top = field("m_nested", model=2, children=[hero, array])
    serializer = SimpleNamespace(fields=[top])
    selected = dict(_selected(serializer))
    assert set(selected) == {"m_nested.m_identity", "m_nested.m_choices"}
    entity = Entity(
        "CDOTAPlayerResource",
        values={
            "m_nested.m_identity": 106,
            "m_nested.m_choices.0000": 106,
            "m_nested.m_choices.0001": None,
        },
    )
    assert _value(entity, hero, "m_nested.m_identity") == 106
    assert _value(entity, array, "m_nested.m_choices") == {"length_raw": 2, "values": [106, None]}


def test_missing_vector_length_is_not_empty_and_nested_values_keep_raw_fields():
    vector = field("m_treeRows", model=4, children=[field("m_id")])
    entity = Entity("CMapTree")
    value = _value(entity, vector, "m_treeRows")
    assert value["values"] is None and value["length_raw"] is None
    entity.values.update({"m_treeRows": 1, "m_treeRows.0000.m_id": 9})
    assert _value(entity, vector, "m_treeRows") == {"length_raw": 1, "values": [{"m_id": 9}]}


def test_recursive_schema_is_marked_unknown_instead_of_recursing_forever():
    item = field("m_tree")
    serializer = SimpleNamespace(fields=[item])
    item.serializer = serializer
    assert _schema(serializer)["fields"][0]["children"]["unknown"]


def test_monkey_fields_and_xyz_are_raw_and_movement_only_is_not_full_trajectory():
    collector, parser, players = setup()
    hero = Entity(
        "CDOTA_Unit_Hero_MonkeyKing",
        index=70,
        fields=[field("m_nPerchedTree")],
        values={
            "m_nPerchedTree": 4294967295,
            "CBodyComponent.m_cellX": 128,
            "CBodyComponent.m_cellY": 128,
            "CBodyComponent.m_cellZ": 128,
            "CBodyComponent.m_vecX": 12.5,
            "CBodyComponent.m_vecY": 20.0,
            "CBodyComponent.m_vecZ": 256.0,
        },
    )
    players._canonical_hero_entity = lambda pid: hero if pid == 3 else None
    players._hero_handle_for_player = lambda pid: (hero.serial << 14) | hero.index
    collector.on_entity(hero, Op.CREATED)
    collector.on_packet_end(0)
    parser.tick = 1
    hero.values["CBodyComponent.m_vecX"] = 13.0
    collector.on_entity(hero, Op.UPDATED)
    collector.on_packet_end(1)
    parser.tick = 2
    hero.values["m_nPerchedTree"] = 0
    collector.on_entity(hero, Op.UPDATED)
    result = finish(collector, parser, 2)
    rows = result["entity_changes"]
    assert len(rows) == 2
    assert rows[0]["fields_raw"]["m_nPerchedTree"] == 4294967295
    assert rows[1]["fields_raw"]["m_nPerchedTree"] == 0
    assert rows[0]["position"]["world"] == {"x": 12.5, "y": 20.0, "z": 256.0}
    assert rows[1]["position"]["world"]["x"] == 13.0
    assert rows[1]["canonical_player_bindings"] == [{"player_id": 3, "hero_handle": 32838}]


def test_stationary_focus_is_resampled_on_canonical_change_and_raw_cut_packet():
    collector, parser, players = setup()
    hero = Entity(
        "CDOTA_Unit_Hero_MonkeyKing",
        fields=[field("m_nPerchedTree")],
        values={"m_nPerchedTree": 20},
    )
    collector.on_entity(hero, Op.CREATED)
    collector.on_packet_end(0)
    players._canonical_hero_entity = lambda pid: hero if pid == 3 else None
    players._hero_handle_for_player = lambda pid: (hero.serial << 14) | hero.index
    parser.tick = 1
    collector.on_packet_end(1)
    parser.tick = 2
    collector.raw_combat(Entry({"type": 35, "value": 20}), "wrapped_bulk")
    result = finish(collector, parser, 2)
    rows = result["entity_changes"]
    assert [row["tick"] for row in rows] == [0, 1, 2]
    assert rows[0]["canonical_player_bindings"] == []
    assert rows[1]["canonical_player_bindings"] == [{"player_id": 3, "hero_handle": 32769}]


def test_perched_raw_index_keeps_same_position_samples_without_claiming_landing():
    collector, parser, players = setup()
    hero = Entity(
        "CDOTA_Unit_Hero_MonkeyKing",
        fields=[field("m_nPerchedTree")],
        values={"m_nPerchedTree": 20},
    )
    players._canonical_hero_entity = lambda pid: hero if pid == 3 else None
    players._hero_handle_for_player = lambda pid: 32769
    collector.on_entity(hero, Op.CREATED)
    collector.on_packet_end(0)
    collector.on_packet_end(0)
    parser.tick = 1
    collector.on_packet_end(1)
    result = finish(collector, parser, 2)
    rows = result["entity_changes"]
    assert [row["tick"] for row in rows] == [0, 1, 2]
    assert all(row["raw_perched_index_trajectory_sample"] is True for row in rows)
    assert rows[1]["fields_raw"] == {}
    assert rows[1]["previous_packet_ordinal"] == 1
    assert rows[2]["previous_packet_ordinal"] == 3
    assert rows[1]["position"]["world"] == {"x": None, "y": None, "z": None}


def test_delta_fields_reconstruct_exact_raw_values_and_explicit_missing():
    collector, parser, _ = setup()
    entity = Entity(
        "CDOTA_BaseNPC",
        fields=[field("m_iDayTimeVisionRange"), field("m_fRevealRadius")],
        values={"m_iDayTimeVisionRange": 1800, "m_fRevealRadius": 300},
    )
    collector.on_entity(entity, Op.CREATED)
    collector.on_packet_end(0)
    parser.tick = 1
    entity.values["m_fRevealRadius"] = None
    collector.on_entity(entity, Op.UPDATED)
    result = finish(collector, parser, 1)
    first, second = result["entity_changes"]
    assert first["initial"] is True and first["fields_are_delta"] is False
    assert second["initial"] is False and second["fields_are_delta"] is True
    assert second["fields_raw"] == {"m_fRevealRadius": None}
    reconstructed = dict(first["fields_raw"])
    reconstructed.update(second["fields_raw"])
    assert reconstructed == {"m_iDayTimeVisionRange": 1800, "m_fRevealRadius": None}


def test_hero_id_nested_variable_table_preserves_count_indices_without_unrelated_fields():
    collector, parser, _ = setup()
    children = [field("m_nSelectedHeroID", kind="HeroID_t"), field("m_nGold")]
    vector = field(
        "m_vecPlayerTeamData",
        kind="CUtlVectorEmbeddedNetworkVar<PlayerTeamData_t>",
        model=4,
        children=children,
    )
    entity = Entity(
        "CDOTA_PlayerResource",
        fields=[vector],
        values={
            "m_vecPlayerTeamData": 2,
            "m_vecPlayerTeamData.0000.m_nSelectedHeroID": 106,
            "m_vecPlayerTeamData.0000.m_nGold": 1000,
        },
    )
    collector.on_entity(entity, Op.CREATED)
    result = finish(collector, parser, 0)
    value = result["entity_changes"][0]["fields_raw"]["m_vecPlayerTeamData"]
    assert value == {
        "length_raw": 2,
        "values": [{"m_nSelectedHeroID": 106}, {"m_nSelectedHeroID": None}],
        "fields_selection": "candidate_descendants_only",
    }


def test_vision_viewer_container_and_reveal_alias_keep_full_raw_units():
    collector, parser, _ = setup()
    viewer_fields = [field("m_nGridX"), field("m_nRadius"), field("m_bValid", kind="bool")]
    viewers = Entity(
        "CDOTAFogOfWarTempViewers",
        fields=[
            field(
                "m_viewers",
                kind="CUtlVectorEmbeddedNetworkVar<TempViewerInfo_t>",
                model=4,
                children=viewer_fields,
            ),
            field("m_non_alias_counter"),
        ],
        values={
            "m_viewers": 1,
            "m_viewers.0000.m_nGridX": 10,
            "m_viewers.0000.m_nRadius": 5,
            "m_viewers.0000.m_bValid": True,
            "m_non_alias_counter": 1,
        },
    )
    hero = Entity(
        "CDOTA_BaseNPC",
        index=2,
        fields=[field("m_fRevealRadius", kind="float32")],
        values={"m_fRevealRadius": 120.5},
    )
    collector.on_entity(viewers, Op.CREATED)
    collector.on_entity(hero, Op.CREATED)
    result = finish(collector, parser, 0)
    rows = {row["class_name"]: row for row in result["entity_changes"]}
    value = rows[viewers.name]["fields_raw"]
    assert value["m_non_alias_counter"] == 1
    assert value["m_viewers"]["values"] == [{"m_nGridX": 10, "m_nRadius": 5, "m_bValid": True}]
    assert rows[hero.name]["fields_raw"]["m_fRevealRadius"] == 120.5


class Entry:
    def __init__(self, values=None):
        self.values = values or {}
        self.payload = json.dumps(self.values).encode()

    def ParseFromString(self, payload):
        self.payload = payload
        self.values = json.loads(payload)

    def SerializeToString(self):
        return self.payload

    def ListFields(self):
        return [
            (SimpleNamespace(name=k, is_repeated=False), v)
            for k, v in self.values.items()
            if not k.startswith("unknown_")
        ]


class Wrapper:
    def ParseFromString(self, payload):
        value = json.loads(payload)
        self.msg_type, self.msg_data = value["msg_type"], value["msg_data"].encode()


class Bulk:
    def ParseFromString(self, payload):
        self.combat_entries = [Entry(value) for value in json.loads(payload)]


def test_raw_direct_and_bulk_preserve_uint32_presence_unknown_bytes_without_name_table():
    collector, parser, _ = setup()
    calls = []
    parser._dispatch_inner = lambda kind, payload: calls.append((kind, payload))
    wire = SimpleNamespace(
        _DOTA_UM_COMBAT_LOG_HLTV=1,
        _SVC_USER_MESSAGE=2,
        _DOTA_UM_COMBAT_LOG_DATA=3,
        _DOTA_UM_COMBAT_LOG_BULK_DATA=4,
        CMsgDOTACombatLogEntry=Entry,
        CSVCMsg_UserMessage=Wrapper,
        CDOTAUserMsg_CombatLogBulkData=Bulk,
    )
    install_raw_combat_hook(parser, collector, wire)
    value = {"type": 35, "value": 4294967295, "unknown_extension": 99}
    direct = json.dumps(value).encode()
    parser._dispatch_inner(1, direct)
    parser._dispatch_inner(
        2, json.dumps({"msg_type": 4, "msg_data": json.dumps([{"type": 35}])}).encode()
    )
    result = finish(collector, parser, 0)
    first, second = result["raw_tree_cut_events"]
    assert first["fields_present"] == {"type": 35, "value": 4294967295}
    assert bytes.fromhex(first["protobuf_bytes_hex"]) == direct
    assert first["protobuf_sha256"] == hashlib.sha256(direct).hexdigest()
    assert first["protobuf_bytes_origin"] == "original_direct_message_payload"
    assert second["protobuf_bytes_origin"] == "reserialized_nested_message_including_unknown_fields"
    assert "value" not in second["fields_present"]
    assert first["combat_log_names_table_present"] is False
    assert first["packet_ordinal"] == second["packet_ordinal"] == 1
    assert [first["dispatch_index"], second["dispatch_index"]] == [1, 2]
    assert len(calls) == 2


def test_sendtables_original_outer_payload_survives_unknown_proto_fields():
    collector, parser, _ = setup()
    calls = []
    parser._on_send_tables = lambda data: calls.append(data)
    original = install_sendtables_hook(parser, collector)
    payload = b"\x0a\x03\x68\x01\x00"
    parser._on_send_tables(payload)
    row = collector.send_tables[0]
    assert base64.b64decode(row["payload_base64"]) == payload
    assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    assert row["byte_length"] == len(payload) and calls == [payload]
    assert callable(original)


def storage(rows, *, capacity=16):
    return {
        "storage_kind": "Gem.FieldState",
        "length_raw": None,
        "logical_length_known": False,
        "values": None,
        "allocated_storage_slots": capacity,
        "stored_slots_may_be_stale": True,
        "current_membership_known": False,
        "observed_storage_rows": deepcopy(rows),
    }


def reconstruct_storage(encoded, prior, *, prior_field_packet):
    """Independent test consumer: protocol replacement, not encoder comparison logic."""
    if not isinstance(encoded, dict) or encoded.get("storage_kind") != "Gem.FieldState":
        return deepcopy(encoded)
    value = deepcopy(encoded)
    mode = value.pop("storage_rows_encoding")
    base = value.pop("base_field_packet_ordinal")
    if mode == "full":
        assert base is None
        return value
    assert mode == "delta" and prior is not None
    assert base == prior_field_packet
    rows = {r["index"]: deepcopy(r) for r in prior["observed_storage_rows"]}
    for index in value.pop("removed_storage_indices"):
        del rows[index]
    for row in value.pop("changed_rows"):
        rows[row["index"]] = row
    value["observed_storage_rows"] = [rows[i] for i in sorted(rows)]
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def test_storage_index_delta_lossless_deletion_null_capacity_and_empty_states():
    first = storage(
        [
            {"index": 2, "fields_raw": {"m_bValid": True, "m_nRadius": 5}},
            {"index": 9, "fields_raw": {"m_bValid": False, "m_nRadius": 7}},
        ]
    )
    second = storage(
        [
            {"index": 2, "fields_raw": {"m_bValid": None, "m_nRadius": 5}},
            {"index": 12, "fields_raw": {"m_bValid": True, "m_nRadius": 8}},
        ],
        capacity=32,
    )
    third = storage([], capacity=8)
    previous = restored = None
    for ordinal, full in enumerate((first, second, third), 1):
        encoded = _encode_storage_field(full, previous, base_field_packet_ordinal=ordinal - 1)
        restored = reconstruct_storage(encoded, restored, prior_field_packet=ordinal - 1)
        assert canonical(restored) == canonical(full)
        assert restored["logical_length_known"] is False
        assert restored["current_membership_known"] is False
        if ordinal == 2:
            assert encoded["removed_storage_indices"] == [9]
            assert [row["index"] for row in encoded["changed_rows"]] == [2, 12]
            assert encoded["changed_rows"][0]["fields_raw"]["m_bValid"] is None
        if ordinal == 3:
            assert encoded["changed_rows"] == []
            assert encoded["removed_storage_indices"] == [2, 12]
        previous = full


@pytest.mark.parametrize("old,new", [(False, 0), (True, 1), (1, 1.0), (0, None)])
def test_storage_delta_preserves_json_type_changes(old, new):
    before = storage([{"index": 2, "fields_raw": {"value": old}}])
    after = storage([{"index": 2, "fields_raw": {"value": new}}])
    encoded = _field_changes({"vector": after}, {"vector": before}, {"vector": 7})["vector"]
    assert len(encoded["changed_rows"]) == 1
    assert canonical(reconstruct_storage(encoded, before, prior_field_packet=7)) == canonical(after)


def test_storage_metadata_only_change_keeps_rows_and_uses_field_not_entity_base():
    before = storage([{"index": 0, "value_raw": 1}], capacity=8)
    after = storage([{"index": 0, "value_raw": 1}], capacity=16)
    encoded = _field_changes(
        {"vector": after, "other": 9},
        {"vector": before, "other": 8},
        {"vector": 3, "other": 7},
    )["vector"]
    assert encoded["base_field_packet_ordinal"] == 3
    assert encoded["changed_rows"] == encoded["removed_storage_indices"] == []
    assert reconstruct_storage(encoded, before, prior_field_packet=3) == after


@pytest.mark.parametrize("reset", [None, {"unknown": "missing"}, {"length_raw": 0, "values": []}])
def test_container_reset_requires_new_full_value_and_omitted_field_is_unchanged(reset):
    value = storage([{"index": 3, "value_raw": 106}])
    assert _field_changes({"vector": value}, {"vector": value}, {"vector": 1}) == {}
    replacement = _encode_storage_field(reset, value, base_field_packet_ordinal=1)
    assert canonical(replacement) == canonical(reset)
    fresh = _encode_storage_field(value, reset, base_field_packet_ordinal=2)
    assert fresh["storage_rows_encoding"] == "full"
    assert fresh["base_field_packet_ordinal"] is None
    assert reconstruct_storage(fresh, reset, prior_field_packet=2) == value


def test_nested_container_and_child_to_scalar_slot_are_whole_row_replacements():
    nested = storage([{"index": 1, "value_raw": 10}])
    before = storage(
        [{"index": 2, "stored_value_kind": "FieldState", "fields_raw": {"nested": nested}}]
    )
    after = storage([{"index": 2, "stored_value_kind": "int", "fields_raw": {"nested": None}}])
    encoded = _encode_storage_field(after, before, base_field_packet_ordinal=1)
    assert encoded["changed_rows"] == after["observed_storage_rows"]
    assert reconstruct_storage(encoded, before, prior_field_packet=1) == after
    encoded["changed_rows"][0]["fields_raw"]["nested"] = "changed by caller"
    assert after["observed_storage_rows"][0]["fields_raw"]["nested"] is None
    assert before["observed_storage_rows"][0]["fields_raw"]["nested"] == nested


@pytest.mark.parametrize("base", [None, True, 0, -1, 1.0])
def test_storage_delta_requires_known_typed_base_and_duplicate_indices_fail(base):
    value = storage([{"index": 1, "value_raw": 10}])
    with pytest.raises(ValueError, match="preceding"):
        _encode_storage_field(value, value, base_field_packet_ordinal=base)
    with pytest.raises(ValueError, match="duplicate"):
        _encode_storage_field(
            storage([{"index": 1}, {"index": 1}]), None, base_field_packet_ordinal=None
        )


def test_selected_top_level_field_cannot_silently_disappear():
    with pytest.raises(ValueError, match="disappeared"):
        _field_changes({}, {"field": 1}, {"field": 1})


def test_real_gem_fieldstate_sparse_slots_are_not_capacity_or_current_length():
    # A subprocess uses the installed dependency without contaminating fresh-Gem
    # CLI tests in this pytest process. No ignored data/ checkout is required.
    if find_spec("gem") is None:
        pytest.skip("Optional replay dependency Gem is not installed")
    code = textwrap.dedent("""
        from types import SimpleNamespace
        from gem.schema.field_state import FieldState
        from copy import deepcopy
        import json
        from dota_items.sources.map_tree_probe import _value, _encode_storage_field

        def field(name, kind='uint32', model=0, children=None):
            return SimpleNamespace(var_name=name, var_type=kind, model=model,
                field_type=SimpleNamespace(count=None),
                serializer=None if children is None else SimpleNamespace(fields=children))

        root = FieldState()
        root._set_compact((0,), 10)
        assert root._get_compact((0,)) == 10
        root._set_compact((0, 2, 0), 125)
        root._set_compact((0, 2, 1), True)
        root._set_compact((0, 9, 0), 250)
        container = root._get_compact((0,))
        assert isinstance(container, FieldState)
        assert len(container._state) == 16

        class Entity:
            def get(self, path):
                parts = path.split('.')
                if len(parts) == 1: return root._get_compact((0,))
                return root._get_compact((0, int(parts[1]),
                    {'m_nRadius': 0, 'm_bValid': 1}[parts[2]]))
        vector = field('m_viewers', model=4,
            children=[field('m_nRadius'), field('m_bValid', 'bool')])
        before = _value(Entity(), vector, 'm_viewers')
        assert before['length_raw'] is None
        assert before['logical_length_known'] is False
        assert before['current_membership_known'] is False
        assert before['stored_slots_may_be_stale'] is True
        assert before['allocated_storage_slots'] == 16
        assert before['values'] is None
        rows = before['observed_storage_rows']
        assert [r['index'] for r in rows] == [2, 9]
        assert rows[0]['fields_raw'] == {'m_nRadius': 125, 'm_bValid': True}
        assert rows[1]['fields_raw'] == {'m_nRadius': 250, 'm_bValid': None}

        # Gem ignores this scalar length write after children exist: old slots
        # survive, so neither capacity nor observed indices prove membership.
        root._set_compact((0,), 0)
        assert _value(Entity(), vector, 'm_viewers') == before

        primitive = FieldState()
        primitive._set_compact((0,), 4)
        primitive._set_compact((0, 3), 106)
        class PrimitiveEntity:
            def get(self, path):
                parts = path.split('.')
                if len(parts) == 1:
                    return primitive._get_compact((0,))
                return primitive._get_compact((0, int(parts[1])))
        raw = _value(PrimitiveEntity(), field('m_choices', 'HeroID_t', 3), 'm_choices')
        assert raw['observed_storage_rows'] == [{'index': 3, 'value_raw': 106}]
        assert raw['length_raw'] is None
        assert raw['allocated_storage_slots'] == 8

        empty = SimpleNamespace(get=lambda path: FieldState())
        raw_empty = _value(empty, vector, 'm_viewers')
        assert raw_empty['observed_storage_rows'] == []
        assert raw_empty['logical_length_known'] is False
        assert raw_empty['length_raw'] is None

        # A real storage tree with 128 rows: one changed child should emit one
        # full changed row, not 128 repeated rows or a capacity-sized snapshot.
        for index in range(128):
            root._set_compact((0, index, 0), 500 + index)
            root._set_compact((0, index, 1), True)
        full_before = _value(Entity(), vector, 'm_viewers')
        root._set_compact((0, 42, 0), 999)
        full_after = _value(Entity(), vector, 'm_viewers')
        encoded = _encode_storage_field(full_after, full_before, base_field_packet_ordinal=8)
        assert [row['index'] for row in encoded['changed_rows']] == [42]
        assert encoded['removed_storage_indices'] == []
        assert len(json.dumps(encoded)) < len(json.dumps(full_after)) / 10
        reconstructed = deepcopy(full_before)
        for row in encoded['changed_rows']:
            reconstructed['observed_storage_rows'][row['index']] = row
        assert reconstructed == full_after
    """)
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(root / "src"))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "match,build", [(True, 6993), (0, 6993), (9103395615, None), (9103395615, "6993")]
)
def test_capture_requires_explicit_positive_integer_identity_before_importing_gem(match, build):
    with pytest.raises(ValueError, match="positive"):
        capture("unused.dem", expected_match_id=match, expected_game_build=build)


@pytest.mark.parametrize(
    "failure", [None, "match", "build", "float_match", "float_build", "truncated", "post_game"]
)
def test_capture_identity_completion_and_instrumentation_restoration(monkeypatch, failure):
    instances = []

    class Parser:
        def __init__(self, path):
            self.tick = 0
            self.post_game_tick = None
            self.match_id, self.game_build = 9103395615, 6993
            self.parse_error = self.truncated_at_tick = None
            self.game_clock = SimpleNamespace(game_time_at=lambda tick: 0)
            self.string_tables = SimpleNamespace(get_by_name=lambda name: None)
            instances.append(self)

        def on_entity(self, callback):
            self.entity_callback = callback

        def _on_packet_end(self, callback):
            self.packet_callback = callback

        def _dispatch_inner(self, kind, data):
            pass

        def _on_send_tables(self, data):
            pass

        def parse(self):
            self.post_game_tick = 0
            self.packet_callback(0)
            if failure == "match":
                self.match_id = 1
            if failure == "build":
                self.game_build = 1
            if failure == "float_match":
                self.match_id = float(self.match_id)
            if failure == "float_build":
                self.game_build = float(self.game_build)
            if failure == "truncated":
                self.truncated_at_tick = 0
            if failure == "post_game":
                self.post_game_tick = None

    class Players:
        def attach(self, parser):
            pass

        def _canonical_hero_entity(self, pid):
            return None

    wire = SimpleNamespace(ReplayParser=Parser)
    monkeypatch.setitem(sys.modules, "gem", SimpleNamespace(parser=wire))
    monkeypatch.setitem(sys.modules, "gem.parser", wire)
    monkeypatch.setitem(
        sys.modules, "gem.extractors.players", SimpleNamespace(PlayerExtractor=Players)
    )
    monkeypatch.setitem(sys.modules, "gem.state.entities", SimpleNamespace(EntityOp=Op))
    if failure:
        with pytest.raises(ValueError):
            capture("test.dem", expected_match_id=9103395615, expected_game_build=6993)
    else:
        result = capture("test.dem", expected_match_id=9103395615, expected_game_build=6993)
        assert result["schema"] == "map-tree-probe/1"
        assert result["sampling"]["terminal_packet_ordinal"] == 1
        assert result["training_allowed"] is result["action_review_allowed"] is False
    assert instances[0]._dispatch_inner.__func__ is Parser._dispatch_inner
    assert instances[0]._on_send_tables.__func__ is Parser._on_send_tables
