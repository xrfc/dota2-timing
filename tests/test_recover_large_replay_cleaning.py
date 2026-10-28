"""Safety boundaries of the explicit clean-only large-file recovery entry point."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "recovery", Path(__file__).resolve().parents[1] / "scripts/recover_large_replay_cleaning.py"
)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def test_explicit_read_limit(monkeypatch):
    calls = []
    monkeypatch.setattr(
        recovery,
        "read_source_bytes",
        lambda p, *, max_bytes: calls.append(max_bytes) or b"{}",
    )
    assert recovery.read(Path("unused")) == {}
    assert calls == [512 * 1024**2]


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("immutable")
    with pytest.raises(ValueError, match="Output exists"):
        recovery.run(tmp_path, 1, output)
    assert marker.read_text() == "immutable"


@pytest.mark.parametrize("fault", ["archive", "source_hash", "match_id", "normalized", "raw"])
def test_invalid_evidence_rejected_before_output_creation(tmp_path, fault):
    archive = tmp_path / "1.dem.bz2"
    archive.write_bytes(b"archived evidence")
    digest = recovery.file_hash(archive)
    (tmp_path / "1.receipt.json").write_text(json.dumps({"archive_sha256": digest}))
    cache = tmp_path / "workspaces/1/cache/matches" / digest
    cache.mkdir(parents=True)
    for name in ["normalized.json", "raw-gem.json"]:
        (cache / name).write_text("{}")
    manifest = {
        "source_sha256": digest,
        "match_id": 1,
        "normalized_json_sha256": recovery.file_hash(cache / "normalized.json"),
        "raw_json_sha256": recovery.file_hash(cache / "raw-gem.json"),
    }
    if fault == "archive":
        archive.write_bytes(b"changed")
    elif fault == "source_hash":
        manifest["source_sha256"] = "bad"
    elif fault == "match_id":
        manifest["match_id"] = 2
    else:
        (cache / ("normalized.json" if fault == "normalized" else "raw-gem.json")).write_text("[]")
    (cache / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="mismatch"):
        recovery.run(tmp_path, 1, output)
    assert not output.exists()
