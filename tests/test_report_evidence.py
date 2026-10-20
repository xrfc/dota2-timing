"""The standalone facts CLI must bind claims to actual evidence bytes."""

import hashlib
import json

import pytest

from dota_items.cli import main
from dota_items.normalize import load_timeline


def match():
    return {
        "match_id": 100,
        "duration": 120,
        "players": [
            {"player_slot": 0, "hero_id": 8, "purchase_log": [{"time": 30, "key": "boots"}]}
        ],
    }


@pytest.mark.parametrize("damage", ["missing", "mismatch", "traversal", "symlink", "unpaired"])
def test_report_rejects_unverified_external_evidence(tmp_path, damage):
    raw = match()
    evidence = tmp_path / "raw.json"
    evidence.write_text('{"synthetic":true}', encoding="utf-8")
    raw.update(
        evidence_source="raw.json",
        evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
    )
    if damage == "missing":
        evidence.unlink()
    elif damage == "mismatch":
        evidence.write_text("changed", encoding="utf-8")
    elif damage == "traversal":
        raw["evidence_source"] = "../raw.json"
    elif damage == "symlink":
        link = tmp_path / "link.json"
        try:
            link.symlink_to(evidence)
        except OSError:
            pytest.skip("Symlinks unavailable for this user")
        raw["evidence_source"] = "link.json"
    else:
        del raw["evidence_source"]
    source, config = tmp_path / "input.json", tmp_path / "config.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    config.write_text('{"candidate_items":["boots"]}', encoding="utf-8")
    output = tmp_path / "report"
    assert (
        main(
            [
                "report",
                str(source),
                "--player-slot",
                "0",
                "--config",
                str(config),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert not output.exists()


def test_plain_source_and_valid_external_evidence_have_actual_fingerprints(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(match()), encoding="utf-8")
    assert (
        load_timeline(source, 0).source_fingerprint
        == "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    )
    evidence = tmp_path / "raw.json"
    evidence.write_text('{"synthetic":true}', encoding="utf-8")
    expected = hashlib.sha256(evidence.read_bytes()).hexdigest()
    raw = {**match(), "evidence_source": evidence.name, "evidence_sha256": expected}
    source.write_text(json.dumps(raw), encoding="utf-8")
    timeline = load_timeline(source, 0)
    assert timeline.source == "raw.json"
    assert timeline.source_fingerprint == "sha256:" + expected
