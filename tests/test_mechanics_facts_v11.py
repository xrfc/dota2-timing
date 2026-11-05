"""MK-T5 v11: full recall audit and U83 rulings reach facts; AI rows stay unconfirmed."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v11 import apply_adoptions
from dota_items.data.mechanics_profiles import confirmed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v11"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_facts_v11 as builder  # noqa: E402

ACCEPTED_BY_USER = [
    ("naga_siren_song_of_the_siren", "sleep"),
    ("naga_siren_song_of_the_siren", "healing"),
    ("rattletrap_power_cogs", "displace_other"),
    ("troll_warlord_battle_trance", "forced_action"),
    ("troll_warlord_battle_trance", "death_prevention"),
    ("bounty_hunter_track", "reveal"),
    ("broodmother_spin_web", "phased"),
    ("shadow_demon_disseminate", "damage_return"),
    ("invoker_ice_wall", "ground_zone"),
    ("ringmaster_whoopee_cushion", "ground_zone"),
    ("riki_smoke_screen", "ground_zone"),
]
REJECTED_BY_USER = [
    ("naga_siren_song_of_the_siren", "cyclone_banish"),
    ("rattletrap_power_cogs", "mobility_lock"),
    ("spirit_breaker_planar_pocket", "spell_block"),
    ("warlock_fatal_bonds", "damage_return"),
    ("monkey_king_wukongs_command", "summons"),
    ("tinker_deploy_turrets", "summons"),
]


def _doc():
    return json.loads((PACKAGE / "facts-v11.json").read_text(encoding="utf-8"))


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = json.loads((package / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_matches_manifest_and_replays(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, _ = builder.run(tmp_path / "v11")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)


@pytest.mark.parametrize("subject,mechanism", ACCEPTED_BY_USER)
def test_user_accepts(subject, mechanism):
    rows = _rows(_doc(), subject, mechanism)
    assert any(r["decision"] == "accept" and r["basis"] == "user:U83" for r in rows)


@pytest.mark.parametrize("subject,mechanism", REJECTED_BY_USER)
def test_user_rejects(subject, mechanism):
    rows = _rows(_doc(), subject, mechanism)
    assert rows and all(r["decision"] == "reject" and r["basis"] == "user:U83" for r in rows)


def test_no_objection_and_ai_rows_do_not_count_as_confirmed():
    doc = _doc()
    silent = [r for r in doc["rows"] if r["origin"] == "assistant_proposal"]
    assert len(silent) == 20
    assert not any(confirmed(r["basis"]) for r in silent)
    audit = [r for r in doc["rows"] if r["origin"].startswith("full_audit")]
    assert audit and {r["basis"] for r in audit} == {"two_ai"}


def test_withdrawn_and_previous_gaps():
    doc = _doc()
    assert not _rows(doc, "shivas_guard", "heal_reduction")
    assert any(r["decision"] == "accept" for r in _rows(doc, "lion_voodoo", "hex"))
    assert any(r["decision"] == "accept" for r in _rows(doc, "ring_of_health", "healing"))


def test_fixed_areas_are_zones_and_following_areas_are_auras():
    doc = _doc()
    for subject in ("riki_smoke_screen", "invoker_ice_wall", "ringmaster_whoopee_cushion"):
        assert not _rows(doc, subject, "aura")
    for subject in ("ember_spirit_immolation", "pudge_rot", "witch_doctor_voodoo_restoration"):
        assert any(r["decision"] == "accept" for r in _rows(doc, subject, "aura"))
        assert not _rows(doc, subject, "ground_zone")


def test_audit_row_cannot_overwrite_existing_row():
    base = {"context": "base", "requires_scepter": False, "requires_shard": False}
    doc = {
        "rows": [
            {
                "subject": "a",
                "mechanism": "m",
                "condition": base,
                "review_id": "1",
                "decision": "reject",
                "basis": "two_ai",
                "notes_zh": [],
            }
        ],
        "skill_notes": [],
        "counts": {},
    }
    entry = {
        "kind": "row",
        "subject": "a",
        "mechanism": "m",
        "condition": "base",
        "decision": "accept",
        "basis": "two_ai",
        "origin": "full_audit_both",
        "note_zh": "n",
        "quote": "q",
    }
    with pytest.raises(ValueError):
        apply_adoptions(doc, [entry], {}, {})
    ruled = apply_adoptions(doc, [{**entry, "basis": "user:U83"}], {}, {})
    assert ruled["rows"][0]["decision"] == "accept"
    assert doc["rows"][0]["decision"] == "reject"
