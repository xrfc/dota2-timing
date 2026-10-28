"""Direct sampling provenance regressions (not independent game truth)."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from dota_items.data.replay_identity import compare_positions, native_position
from dota_items.sources.replay_identity import instrument_players, sample_evidence


def fixture():
    row = dict(
        tick=30,
        x=128.5,
        y=257.5,
        entity_index=7,
        entity_serial=3,
        cell_x=1,
        cell_y=2,
        vec_x=0.5,
        vec_y=1.5,
        canonical_for_slot=True,
        hero_name="hero",
    )
    raw = {
        "match_id": 42,
        "players": [
            {"player_id": p, "hero_name": "hero", "position_log": [[30, 128.5, 257.5]]}
            for p in range(10)
        ],
    }
    captured = {
        "match_id": 42,
        "game_build": 1,
        "positions": [{**row, "player_id": p} for p in range(10)],
        "landmarks": [{"cell_x": 1, "cell_y": 2, "vec_x": None, "vec_y": 0}],
    }
    return raw, captured


def test_exact_links_unknown_landmark_no_mutation():
    raw, captured = fixture()
    before = deepcopy((raw, captured))
    result = compare_positions(raw, captured)
    assert result["positions_compared"] == 10
    assert result["links"][0] == {
        "raw_ref": "players[0].position_log[0]",
        "capture_ref": "positions[0]",
    }
    assert result["landmarks"][0]["native_xy"] is None
    assert not result["training_admission"]
    assert not result["map_transform_verified"]
    assert (raw, captured) == before


@pytest.mark.parametrize(
    "field,value",
    [("x", 0), ("tick", 31), ("vec_x", 1), ("hero_name", "illusion"), ("player_id", 12)],
)
def test_corruption_rejected(field, value):
    raw, captured = fixture()
    captured["positions"][0][field] = value
    with pytest.raises(ValueError):
        compare_positions(raw, captured)


def test_duplicate_ticks_preserve_order_and_entity_reuse():
    raw, captured = fixture()
    raw["players"][0]["position_log"].append([30, 128.5, 257.5])
    captured["positions"].insert(
        1, {**captured["positions"][0], "entity_serial": 4, "canonical_for_slot": False}
    )
    result = compare_positions(raw, captured)
    assert result["players"][0]["identities"] == [[7, 3], [7, 4]]
    assert result["players"][0]["noncanonical_samples"] == 1
    captured["positions"].pop(1)
    with pytest.raises(ValueError, match="count mismatch"):
        compare_positions(raw, captured)


def test_match_identity_rejected():
    raw, captured = fixture()
    captured["match_id"] = 43
    with pytest.raises(ValueError, match="identity"):
        compare_positions(raw, captured)


def test_direct_entity_not_canonical_substitution():
    def entity(index, serial):
        return SimpleNamespace(
            get_index=lambda: index,
            get_serial=lambda: serial,
            get_class_name=lambda: "hero",
            get_int32=lambda _: None,
            get_uint32=lambda _: 0,
            get_float32=lambda _: 0,
        )

    selected = entity(5, 2)
    extractor = SimpleNamespace(_canonical_hero_entity=lambda _: entity(5, 3))
    row = sample_evidence(extractor, selected, 0)
    assert row["entity_serial"] == 2
    assert row["canonical_identity"] == [5, 3]
    assert not row["canonical_for_slot"]
    assert row["life_state"] is None
    extractor._canonical_hero_entity = lambda _: None
    assert sample_evidence(extractor, selected, 0)["canonical_identity"] is None


def test_patch_refuses_unknown_or_already_instrumented_source():
    with pytest.raises(ValueError):
        instrument_players("something else")
    anchor = "            snap = _build_hero_snapshot(entity, tick, player_id)\n"
    with pytest.raises(ValueError):
        instrument_players(anchor * 2)
    with pytest.raises(ValueError):
        instrument_players(instrument_players(anchor))


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True])
def test_unknown_or_nonfinite_coordinate_is_not_zero(value):
    assert native_position(dict(cell_x=value, cell_y=1, vec_x=0, vec_y=0)) is None


def test_cli_refuses_overwrite_and_archive_tamper(tmp_path, monkeypatch):
    import importlib.util
    import json
    import sys
    from pathlib import Path

    monkeypatch.delitem(sys.modules, "gem", raising=False)

    spec = importlib.util.spec_from_file_location(
        "identity_cli", Path(__file__).parents[1] / "scripts/audit_replay_identity.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    compat = tmp_path / "compat"
    prep = tmp_path / "prep"
    compat.mkdir()
    prep.mkdir()
    (compat / "manifest.json").write_text("{}")
    (prep / "manifest.json").write_text("{}")
    archive = tmp_path / "test.dem"
    archive.write_bytes(b"changed")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"archive_sha256": "0" * 64}))
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(ValueError, match="Output already exists"):
        module.run(archive, receipt, prep, compat, output)
    with pytest.raises(ValueError, match="Archive hash mismatch"):
        module.run(archive, receipt, prep, compat, tmp_path / "new")
    assert not (tmp_path / "new").exists()
