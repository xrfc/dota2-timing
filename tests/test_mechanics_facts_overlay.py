"""The shared overlay builder (U177) reproduces the frozen v21-v26 facts from their inputs."""

import json
import sys
from pathlib import Path

import pytest

from dota_items.data import mechanics_facts_v21 as v21
from dota_items.data.mechanics_facts_overlay import CONDITIONS, SCHEMA, build_reviewed

ROOT = Path(__file__).resolve().parents[1]
MECH = ROOT / "knowledge/mechanics"
BASE_CONDITION = CONDITIONS[0]


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _facts(version):
    return _load(MECH / f"extractions/v{version}/facts-v{version}.json")


def convert(version, old):
    """Old per-version inputs as one overlay file, in the order each old module applied them."""
    ops = []
    for change in old.get("decision_changes", []):
        ops.append({"op": "decision_change", **change})
    for update in old.get("basis_updates", []):
        ops.append({"op": "basis_update", **update, "note_zh": v21.NOTE})
    for spec in old.get("added_rows", []):
        row = {"op": "add_row", "condition": BASE_CONDITION, **spec}
        if version == 25:
            row.update(origin="haste_review", claude="accept", codex="accept")
        row.pop("grants", None)
        ops.append(row)
    if version == 26:
        ops.append({"op": "reword_notes", "old": "穿透减益免疫", "new": "无视减益免疫"})
    return {"schema": SCHEMA, "version": version, "operations": ops}


@pytest.mark.parametrize("version", [21, 22, 23, 24, 25, 26])
def test_reproduces_frozen_facts(version):
    expected = _facts(version)
    old = _load(MECH / f"reviews/v{version}-inputs-001.json")
    terms = {row["mechanism"] for row in expected["rows"]}
    built = build_reviewed(
        _facts(version - 1),
        convert(version, old),
        version=version,
        vocabulary=expected["vocabulary"],
        terms=terms,
        known_subjects={row["subject"] for row in expected["rows"]},
    )
    assert built == expected


def _doc():
    base = _facts(26)
    return base, {row["mechanism"] for row in base["rows"]}


def _overlay(*ops):
    return {"schema": SCHEMA, "version": 27, "operations": list(ops)}


def test_rejects_wrong_old_state():
    base, terms = _doc()
    row = next(r for r in base["rows"] if r["decision"] == "accept")
    change = {
        "op": "decision_change",
        "review_id": row["review_id"],
        "from": "reject",
        "to": "accept",
        "basis": "user:U0",
        "note_zh": "x",
    }
    with pytest.raises(ValueError, match="does not match"):
        build_reviewed(base, _overlay(change), version=27, vocabulary="v", terms=terms)


def test_two_ai_row_needs_both_ais():
    base, terms = _doc()
    row = base["rows"][0]
    spec = {
        "op": "add_row",
        "review_id": "new-1",
        "subject": row["subject"],
        "subject_zh": "x",
        "mechanism": row["mechanism"],
        "condition": CONDITIONS[2],
        "decision": "accept",
        "basis": "two_ai",
        "notes_zh": [],
        "quotes": [],
        "claude": "accept",
        "codex": None,
    }
    with pytest.raises(ValueError, match="two_ai"):
        build_reviewed(base, _overlay(spec), version=27, vocabulary="v", terms=terms)


def test_retire_moves_rows_and_counts():
    base, terms = _doc()
    row = base["rows"][0]
    retire = {
        "op": "retire",
        "review_ids": [row["review_id"]],
        "item_status": "removed_in_patch",
        "note_zh": "7.42删除",
    }
    built = build_reviewed(base, _overlay(retire), version=27, vocabulary="v", terms=terms)
    assert built["counts"]["rows"] == len(base["rows"]) - 1
    assert built["counts"]["retired_rows"] == len(base["retired_rows"]) + 1
    assert built["retired_rows"][-1]["item_status"] == "removed_in_patch"
    assert built["schema"] == "mechanics-facts/27"


def test_unknown_op_and_wrong_version():
    base, terms = _doc()
    with pytest.raises(ValueError, match="unknown op"):
        build_reviewed(base, _overlay({"op": "drop"}), version=27, vocabulary="v", terms=terms)
    with pytest.raises(ValueError, match="version"):
        build_reviewed(base, _overlay(), version=28, vocabulary="v", terms=terms)


def test_full_build_matches_frozen_v26(tmp_path):
    """Same inputs as the v26 script, through the shared script: identical output files."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_mechanics_facts_overlay as script

    overlay = tmp_path / "v26-overlay.json"
    overlay.write_text(json.dumps(convert(26, _load(MECH / "reviews/v26-inputs-001.json"))))
    spec = {
        "schema": script.SPEC_SCHEMA,
        "version": 26,
        "base": "knowledge/mechanics/extractions/v25/facts-v25.json",
        "inputs": str(overlay),
        "vocabulary": "knowledge/mechanics/vocabulary-v15.json",
        "rules": "knowledge/mechanics/rules-v13.json",
        "enums": "knowledge/mechanics/enums-v2.json",
        "registry": "knowledge/hero-capabilities/hero-registry.json",
        "game_npc": "knowledge/game-files/snapshots/2026-11-02/sources/scripts/npc",
        "items_txt": "knowledge/game-files/snapshots/2026-11-03-items/sources/scripts/npc/"
        "items.txt",
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    script.run(str(spec_path), tmp_path / "out")
    for name in ("facts-v26.json", "rules-evaluation.json", "rules-expanded.json"):
        assert (tmp_path / "out" / name).read_bytes() == (
            MECH / "extractions/v26" / name
        ).read_bytes(), name
