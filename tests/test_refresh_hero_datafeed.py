"""U36 refresh tool: diff is offline and finds text/flag changes; fetch never overwrites."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import refresh_hero_datafeed as refresh  # noqa: E402

OLD = ROOT / "knowledge/hero-capabilities/sources"


def write(directory, hero):
    for language in refresh.LANGUAGES:
        payload = {"result": {"data": {"heroes": [hero]}}}
        (directory / f"hero-{hero['id']}-{language}.json").write_text(json.dumps(payload))


def test_identical_snapshot_has_no_changes():
    report = refresh.diff(OLD, OLD)
    for part in report["languages"].values():
        assert part["old_heroes"] == part["new_heroes"] == 127
        assert part["changes"] == []


def test_detects_text_flag_and_ability_changes(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    ability = {"name": "x_orb", "desc_loc": "old", "ability_has_scepter": True}
    write(old, {"id": 1, "name": "x", "abilities": [ability, {"name": "x_gone"}]})
    changed = {**ability, "desc_loc": "new", "ability_has_scepter": False}
    write(new, {"id": 1, "name": "x", "abilities": [changed, {"name": "x_new"}]})
    rows = refresh.diff(old, new)["languages"]["english"]["changes"]
    by = {(r["ability"], r["change"]): r for r in rows}
    orb = by[("x_orb", "ability_changed")]
    assert orb["text_fields"] == ["desc_loc"] and orb["other_fields"] == ["ability_has_scepter"]
    assert orb["before"]["desc_loc"] == "old" and orb["after"]["desc_loc"] == "new"
    assert ("x_gone", "ability_removed") in by and ("x_new", "ability_added") in by


def test_fetch_refuses_existing_output(tmp_path):
    with pytest.raises(SystemExit):
        refresh.fetch(tmp_path)


SNAPSHOT = ROOT / "knowledge/hero-capabilities/snapshots/2026-11-01"


def test_checked_in_2026_11_01_snapshot_and_diff():
    import hashlib

    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    assert manifest["patch_verified"] is False and manifest["heroes"] == 127
    for record in manifest["records"]:
        payload = (SNAPSHOT / record["file"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == record["sha256"]
    stored = json.loads((SNAPSHOT / "diff-vs-2026-10-09.json").read_text())
    assert stored == refresh.diff(OLD, SNAPSHOT / "sources")
    assert stored["languages"]["english"]["changes"] == []
    check = json.loads((SNAPSHOT / "patch-check.json").read_text())
    raw = (SNAPSHOT / check["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == check["sha256"]
    assert check["latest_patch"] == "7.41f" and check["patch_verified"] is False
