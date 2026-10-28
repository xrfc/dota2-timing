"""Raw-only export preserves timing evidence without admitting cleaned data."""

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "export_raw_replay_channels",
    Path(__file__).resolve().parents[1] / "scripts/export_raw_replay_channels.py",
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def write(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v))


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    archive = root / "42.dem.bz2"
    archive.write_bytes(b"BZh_fake_test_archive")
    archive_hash = m.sha(archive)
    cache = root / "workspaces/42/cache/matches" / archive_hash
    raw = {
        "match_id": 42,
        "duration": 10,
        "game_clock": {"game_start_tick": 0, "pauses": []},
        "players": [
            {"player_id": i, "hero_id": i + 1, "position_log": [[30, 1, 2], [31, 3, 4]]}
            for i in range(10)
        ],
        "hero_visibility_events": [
            {"tick": 30, "player_id": 0, "radiant_state": "visible", "dire_state": "unknown"}
        ],
    }
    write(cache / "raw-gem.json", raw)
    write(
        cache / "manifest.json",
        {
            "match_id": 42,
            "source_sha256": archive_hash,
            "raw_json_sha256": m.sha(cache / "raw-gem.json"),
        },
    )
    metadata = root / "metadata.json"
    write(
        metadata,
        {
            "match_id": 42,
            "players": [
                {"player_slot": i if i < 5 else i + 123, "hero_id": i + 1} for i in range(10)
            ],
        },
    )
    compat = root / "compat"
    write(
        compat / "manifest.json",
        {"patched": {"state/game_clock.py": m.sha(Path(inspect.getfile(m.GameClock)))}},
    )
    write(
        root / "plan.json",
        {
            "candidates": [
                {"match_id": 42, "metadata_path": str(metadata), "metadata_sha256": m.sha(metadata)}
            ],
            "compat": str(compat),
            "compat_manifest_sha256": m.sha(compat / "manifest.json"),
        },
    )
    write(root / "42.receipt.json", {"archive_sha256": archive_hash})
    return root, raw, cache


def test_preserve_duplicate_seconds_and_unknown(prepared, tmp_path):
    root, raw, cache = prepared
    out = tmp_path / "output"
    result = m.export(root, 42, out)
    rows = [json.loads(s) for s in (out / "positions.raw.jsonl").read_text().splitlines()]
    assert len(rows) == 20
    assert rows[0]["time"] == rows[1]["time"]
    assert rows[0]["source_tick"] != rows[1]["source_tick"]
    vis = json.loads((out / "visibility.raw.jsonl").read_text())
    assert vis["payload"]["dire_state"] == "unknown"
    assert result["training_admission"] is False
    assert result["stage"] == "raw_not_cleaned_or_aligned"
    assert result["outputs"]["positions.raw.jsonl"] == m.sha(out / "positions.raw.jsonl")
    with pytest.raises(ValueError, match="exists"):
        m.export(root, 42, out)


def test_raw_hash_failure(prepared, tmp_path):
    root, raw, cache = prepared
    raw["duration"] = 11
    write(cache / "raw-gem.json", raw)
    with pytest.raises(ValueError, match="hash mismatch"):
        m.export(root, 42, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("issue", ["match", "duplicate", "hero", "visibility"])
def test_identity_failures(prepared, issue):
    root, raw, cache = prepared
    metadata = m.load(root / "metadata.json")
    if issue == "match":
        raw["match_id"] = 43
    elif issue == "duplicate":
        raw["players"][1]["player_id"] = 0
    elif issue == "hero":
        raw["players"][0]["hero_id"] = 100
    else:
        raw["hero_visibility_events"] = []
    with pytest.raises(ValueError):
        m.validate_identity(raw, metadata)


def test_invalid_coordinates(prepared):
    _, raw, _ = prepared
    raw["players"][0]["position_log"][0][1] = float("nan")
    with pytest.raises(ValueError, match="Invalid"):
        list(m.positions(raw))


def test_zero_id_alias_is_evidenced_not_metadata_override(prepared, tmp_path):
    root, raw, cache = prepared
    raw["players"][0].update(hero_id=0, hero_name="npc_dota_hero_anti_mage")
    metadata = m.load(root / "metadata.json")
    m.validate_identity(raw, metadata)
    row = next(m.positions(raw))
    assert row["hero_id"] == 1
    assert row["hero_identity"] == {
        "method": "gem_catalog_alias",
        "reported_hero_id": 0,
        "source_name": "npc_dota_hero_anti_mage",
        "canonical_name": "npc_dota_hero_antimage",
    }
    assert raw["players"][0]["hero_id"] == 0
    raw["players"][0]["hero_name"] = "npc_dota_hero_does_not_exist"
    with pytest.raises(ValueError, match="Unresolved"):
        m.validate_identity(raw, metadata)
    raw["players"][0].update(hero_id=2, hero_name="npc_dota_hero_anti_mage")
    with pytest.raises(ValueError, match="mismatch"):
        m.validate_identity(raw, metadata)
