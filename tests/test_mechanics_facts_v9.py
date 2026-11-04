"""MK-T5 v9: corrections from reading profiles reach the facts and rules."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v9 import apply_corrections

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v9"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_facts_v9 as builder  # noqa: E402


@pytest.fixture(scope="module")
def doc():
    return json.loads((PACKAGE / "facts-v9.json").read_text(encoding="utf-8"))


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def test_package_matches_manifest_and_replays(tmp_path, doc):
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    fresh, _ = builder.run(tmp_path / "v9")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(doc, sort_keys=True)


def test_corrections_are_applied(doc):
    for subject in ("antimage_mana_void", "sven_warcry", "primal_beast_trample"):
        assert _rows(doc, subject, "break_sensitive")[0]["decision"] == "reject"
    for subject in ("juggernaut_healing_ward", "witch_doctor_death_ward", "clinkz_burning_army"):
        assert all(r["decision"] == "reject" for r in _rows(doc, subject, "summons"))
    assert _rows(doc, "juggernaut_omni_slash", "pierces_debuff_immunity")[0]["decision"] == "accept"
    assert _rows(doc, "witch_doctor_death_ward", "invulnerable_untargetable")[0]["decision"] == (
        "reject"
    )
    assert _rows(doc, "witch_doctor_voodoo_switcheroo", "invulnerable_untargetable")[0][
        "condition"
    ]["requires_shard"]
    assert not [
        fact
        for fact in doc["field_observations"]
        if fact["subject"] == "witch_doctor_voodoo_restoration"
        and fact["evidence_kind"] == "enum:damage"
    ]


def test_rule_twenty_targets_only_illusions():
    data = json.loads((PACKAGE / "rules-evaluation.json").read_text(encoding="utf-8"))
    rule = next(item for item in data["rules"] if item["id"] == "R20")
    assert "juggernaut_healing_ward" not in rule["targets"]
    assert "terrorblade_conjure_image" in rule["targets"]


def test_correction_without_a_row_fails_loudly():
    doc = {"rows": [], "field_observations": [], "skill_notes": [], "counts": {}}
    bad = {
        "kind": "reject",
        "subject": "x",
        "mechanism": "stun",
        "note_zh": "n",
        "decision_ref": "U1",
    }
    with pytest.raises(ValueError, match="No row"):
        apply_corrections(doc, [bad], {})
