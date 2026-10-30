"""Build selection, paired diagnostics and prediction-time information boundaries."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from dota_items.data.decision_mana import compare_captures, current_resource
from dota_items.sources.decision_mana import build_first_parser, server_build


class BaseParser:
    def __init__(self):
        self.game_build = 0
        self._pending_server_info = None
        self.entity_manager = None
        self.build_used_by_decoder = None

    def _on_server_info(self, message):
        if self.entity_manager is None:
            self._pending_server_info = message
        else:
            self.game_build = server_build(message)

    def _on_send_tables(self, data):
        self.build_used_by_decoder = self.game_build
        self.entity_manager = object()
        self._on_server_info(self._pending_server_info)
        self._pending_server_info = None


def test_build_set_before_schema_without_mutating_base():
    fixed = build_first_parser(BaseParser)()
    original = BaseParser()
    info = SimpleNamespace(game_dir="/game/dota_v6965/dota")
    fixed._on_server_info(info)
    original._on_server_info(info)
    fixed._on_send_tables(b"schema")
    original._on_send_tables(b"schema")
    assert fixed.build_used_by_decoder == fixed.schema_game_build == 6965
    assert original.build_used_by_decoder == 0


@pytest.mark.parametrize("directory", ["", "/dota/", "/dota_v0/", "/dota_v6965/x/dota_v6965/"])
def test_ambiguous_or_unknown_build_refused(directory):
    with pytest.raises(ValueError, match="Missing or ambiguous"):
        server_build(SimpleNamespace(game_dir=directory))


@pytest.mark.parametrize("build", [954, 955, 990, 6966])
def test_unaudited_build_refused_not_silently_reinterpreted(build):
    with pytest.raises(ValueError, match="Unaudited"):
        build_first_parser(BaseParser)()._on_server_info(
            SimpleNamespace(game_dir=f"/game/dota_v{build}/dota")
        )


def test_schema_first_or_second_schema_refused():
    fixed = build_first_parser(BaseParser)()
    with pytest.raises(ValueError, match="pending ServerInfo"):
        fixed._on_send_tables(b"schema")
    fixed._on_server_info(SimpleNamespace(game_dir="/dota_v6965/"))
    fixed._on_send_tables(b"schema")
    with pytest.raises(ValueError, match="pending ServerInfo"):
        fixed._on_send_tables(b"schema")


def capture_pair():
    def row(tick):
        return {
            "schema": "decision-live-probe/1",
            "tick": tick,
            "player_id": 4,
            "parser_game_time_s": tick / 30,
            "hero": {
                "entity_index": 1489,
                "entity_serial": 687,
                "values": {"m_iHealth": 1000, "m_flMana": 40.0, "m_flMaxMana": 70.0},
                "field_metadata": [
                    {
                        "var_name": name,
                        "var_type": "float32",
                        "bit_count": 20,
                        "high_value": 8192.0,
                        "low_value": None,
                        "encode_flags": None,
                    }
                    for name in ("m_flMana", "m_flMaxMana")
                ],
            },
            "abilities": [{"name": "juggernaut_omni_slash", "cooldown": 30.0}],
            "items": [{"name": "item_tpscroll", "charges": 2}],
        }

    old = {
        "match_id": 9056008987,
        "build": 6965,
        "demo_sha256": "frozen-demo",
        "decision_tick": 90,
        "rows": [row(t) for t in (60, 90, 120)],
    }
    new = copy.deepcopy(old)
    new["rows"].insert(0, row(30))
    for r in new["rows"]:
        for name in ("m_flMana", "m_flMaxMana"):
            r["hero"]["values"][name] *= 8
        for field in r["hero"]["field_metadata"]:
            field["high_value"] = 65536.0
    return old, new


def test_pairs_non_mana_integrity_and_nonmutation():
    old, new = capture_pair()
    before = copy.deepcopy((old, new))
    result = compare_captures(old, new)
    assert len(result["paired_samples"]) == 3
    assert result["non_mana_observations_unchanged"] is True
    assert result["training_allowed"] is False
    assert result["independent_gameplay_units_certified"] is False
    assert result["can_cast"] is None
    assert (old, new) == before
    assert current_resource(result)["mana"] == 320


@pytest.mark.parametrize("mutation", ["health", "cooldown", "item", "identity", "clock"])
def test_changed_non_mana_field_refused(mutation):
    old, new = capture_pair()
    row = new["rows"][2]
    if mutation == "health":
        row["hero"]["values"]["m_iHealth"] += 1
    elif mutation == "cooldown":
        row["abilities"][0]["cooldown"] = 0
    elif mutation == "item":
        row["items"][0]["charges"] = 1
    elif mutation == "identity":
        row["hero"]["entity_serial"] += 1
    else:
        row["parser_game_time_s"] += 1
    with pytest.raises(ValueError, match="Non-mana"):
        compare_captures(old, new)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "order", "match", "metadata", "ratio"]
)
def test_conflicting_or_unexpected_capture_refused(mutation):
    old, new = capture_pair()
    if mutation == "duplicate":
        new["rows"].append(copy.deepcopy(new["rows"][-1]))
    elif mutation == "missing":
        new["rows"].pop()
    elif mutation == "order":
        new["rows"].reverse()
    elif mutation == "match":
        new["match_id"] += 1
    elif mutation == "metadata":
        new["rows"][0]["hero"]["field_metadata"][0]["high_value"] = 8192.0
    else:
        new["rows"][1]["hero"]["values"]["m_flMana"] += 1
    with pytest.raises(ValueError):
        compare_captures(old, new)


@pytest.mark.parametrize("invalid", [None, True, float("nan"), float("inf"), -1])
def test_invalid_resource_is_not_zero(invalid):
    old, new = capture_pair()
    new["rows"][1]["hero"]["values"]["m_flMana"] = invalid
    with pytest.raises(ValueError):
        compare_captures(old, new)


def test_future_diagnostics_excluded_with_current_positive_control():
    old, new = capture_pair()
    result = compare_captures(old, new)
    baseline = current_resource(result)
    changed = copy.deepcopy(result)
    changed["series"][-1]["mana"] = 1
    changed["changes"] = [{"future": "not a current feature"}]
    assert current_resource(changed) == baseline
    changed["series"][2]["mana"] = 123
    assert current_resource(changed) != baseline
    changed["series"].append(copy.deepcopy(changed["series"][2]))
    with pytest.raises(ValueError, match="duplicate current"):
        current_resource(changed)


def test_cli_refuses_output_overwrite(tmp_path):
    path = Path(__file__).parents[1] / "scripts/repair_decision_mana.py"
    spec = importlib.util.spec_from_file_location("repair_decision_mana", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="Plan output exists"):
        module.prepare_plan(tmp_path)
    with pytest.raises(ValueError, match="Requires new output"):
        module.run(tmp_path / "missing", 9056008987, tmp_path)


def test_real_gem_schema_build_and_quantizer_round_trip():
    # Exercise actual Gem protobuf, serializer and bit decoder, not only the
    # ordering fake. Run isolated so importing Gem cannot leak into other tests.
    program = """
from google.protobuf.internal.encoder import _VarintBytes
from gem.binary.reader import BitReader
from gem.parser import ReplayParser
from gem.proto.demo_pb2 import CDemoSendTables
from gem.proto.netmessages_pb2 import CSVCMsg_FlattenedSerializer, CSVCMsg_ServerInfo
from dota_items.sources.decision_mana import build_first_parser

message = CSVCMsg_FlattenedSerializer()
message.symbols.extend(["CDOTA_BaseNPC", "m_flMana", "float32", "m_flMaxMana"])
serializer = message.serializers.add(serializer_name_sym=0, serializer_version=0)
for index in (1, 3):
    serializer.fields_index.append(len(message.fields))
    message.fields.add(var_name_sym=index, var_type_sym=2, bit_count=20, high_value=65536)
inner = message.SerializeToString()
payload = CDemoSendTables(data=_VarintBytes(len(inner)) + inner).SerializeToString()
server = CSVCMsg_ServerInfo(game_dir="/game/dota_v6965/dota", max_classes=512)
old, new = ReplayParser(b""), build_first_parser(ReplayParser)(b"")
for parser in (old, new):
    parser._on_server_info(server)
    parser._on_send_tables(payload)
    assert parser.game_build == 6965
for a, b in zip(old.entity_manager.serializers["CDOTA_BaseNPC"].fields,
                new.entity_manager.serializers["CDOTA_BaseNPC"].fields):
    assert a.high_value == 8192 and b.high_value == 65536
    # Fixed 20-bit wire words, including real zero and the largest code.
    for word in (0, 1, 9072, (1 << 20) - 1):
        data = word.to_bytes(3, "little")
        x, y = a.decoder(BitReader(data)), b.decoder(BitReader(data))
        assert abs(y - x * 8) < 1e-9
        assert abs(y - 65536 * word / ((1 << 20) - 1)) < 1e-9
"""
    subprocess.run([sys.executable, "-c", program], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("mutation", ["source_subset", "ticks", "training"])
def test_edited_plan_refused_before_importing_parser(tmp_path, monkeypatch, mutation):
    path = Path(__file__).parents[1] / "scripts/repair_decision_mana.py"
    spec = importlib.util.spec_from_file_location("repair_decision_mana", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = {"sources": {"a": "hash-a", "b": "hash-b"}, "ticks": [1, 2, 3], "training": False}
    changed = copy.deepcopy(plan)
    if mutation == "source_subset":
        changed["sources"].pop("b")
    elif mutation == "ticks":
        changed["ticks"].append(4)
    else:
        changed["training"] = True
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(module, "assemble_plan", lambda: plan)
    monkeypatch.setattr(module, "sys", SimpleNamespace(modules={}))
    with pytest.raises(ValueError, match="Plan differs"):
        module.run(plan_path, 9056008987, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_source_drift_detected(tmp_path):
    from dota_items.storage import file_hash

    path = Path(__file__).parents[1] / "scripts/repair_decision_mana.py"
    spec = importlib.util.spec_from_file_location("repair_decision_mana", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "raw.json"
    source.write_text("old", encoding="utf-8")
    frozen = {str(source): file_hash(source)}
    module.verify_sources(frozen)
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen source drift"):
        module.verify_sources(frozen)
