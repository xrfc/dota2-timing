"""Regression coverage for isolated fixed8 backport and incomplete-parse rejection."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from dota_items.sources.gem_capture import require_complete_parse


def test_incomplete_parse_rejected():
    with pytest.raises(ValueError, match="Incomplete Gem parse at tick 3722"):
        require_complete_parse(
            SimpleNamespace(parse_error=EOFError("bad stream"), truncated_at_tick=3722)
        )
    require_complete_parse(SimpleNamespace(parse_error=None, truncated_at_tick=None))


def test_isolated_backport_preserves_following_fields(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "compat"
    subprocess.run(
        [sys.executable, str(root / "scripts/build_replay_compat.py"), "--output", str(output)],
        check=True,
    )
    manifest = json.loads((output / "manifest.json").read_text())
    changed = {p for p in manifest["original"] if manifest["original"][p] != manifest["patched"][p]}
    assert changed == set(manifest["changed"])
    program = """
from types import SimpleNamespace
from gem.binary.reader import BitReader
from gem.schema.field_decoder.type_resolver import find_decoder, find_decoder_by_base_type
from gem.schema.field_decoder.scalar_codecs import unsigned_decoder
from gem.state.entities import Entity
for base, expected in [('uint8',255),('int8',-1),('MoveType_t',255)]:
    field=SimpleNamespace(encoder='fixed8',field_type=SimpleNamespace(base_type=base))
    reader=BitReader(bytes([255,7]))
    assert find_decoder(field)(reader)==expected
    assert unsigned_decoder(reader)==7
reader=BitReader(bytes([255,7]))
assert find_decoder_by_base_type('uint8','fixed8')(reader)==255
assert unsigned_decoder(reader)==7
reader=BitReader(bytes([255,1,7]))
assert find_decoder_by_base_type('uint8')(reader)==255
assert unsigned_decoder(reader)==7
"""
    subprocess.run(
        [sys.executable, "-c", program], check=True, env={**os.environ, "PYTHONPATH": str(output)}
    )


def test_failed_backport_does_not_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "evidence.txt"
    marker.write_text("keep")
    result = subprocess.run(
        [sys.executable, str(root / "scripts/build_replay_compat.py"), "--output", str(output)],
        capture_output=True,
    )
    assert result.returncode != 0
    assert marker.read_text() == "keep"


@pytest.mark.parametrize("wrong", ["match", "hero", "duplicate"])
def test_track_export_rejects_identity_mismatch(tmp_path, monkeypatch, wrong):
    from dota_items.workflow import replay_audit as module

    folder = tmp_path / "prepared" / "fake"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{}")
    players = [dict(player_slot=i if i < 5 else i + 123, hero_id=i + 1) for i in range(10)]
    metadata = dict(match_id=1, players=players)
    match = json.loads(json.dumps(metadata))
    if wrong == "match":
        match["match_id"] = 2
    elif wrong == "hero":
        match["players"][0]["hero_id"] = 99
    else:
        match["players"][-1] = match["players"][0]
    (folder / "cleaned.json").write_text(json.dumps(match))
    monkeypatch.setattr(module.Workspace, "preparation", lambda self, pid: ({}, folder))
    with pytest.raises(ValueError, match="identity mismatch"):
        module.audit(tmp_path, 1, metadata, tmp_path / "export")
    assert not (tmp_path / "export").exists()
