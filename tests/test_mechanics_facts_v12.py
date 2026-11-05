"""MK-T5 v12: recheck rulings and the control split reach facts; AI rows stay unconfirmed."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v12 import apply_rulings, condition_label

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v12"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v2"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived as derived_v1  # noqa: E402
import build_mechanics_derived_v2 as derived_v2  # noqa: E402
import build_mechanics_facts_v12 as builder  # noqa: E402

ACCEPTED = [
    ("storm_spirit_ball_lightning", "aoe_damage"),
    ("storm_spirit_ball_lightning", "invulnerable_untargetable"),
    ("viper_nose_dive", "self_mobility"),
    ("winter_wyvern_winters_curse", "taunt"),
    ("enchantress_little_friends", "taunt"),
    ("troll_warlord_battle_trance", "taunt"),
    ("bane_nightmare", "sleep"),
    ("bane_nightmare", "hypnotize"),
    ("bane_nightmare", "channeled"),
    ("void_spirit_aether_remnant", "hypnotize"),
    ("life_stealer_infest", "applies_basic_dispel"),
    ("faceless_void_time_lock", "stun"),
    ("helm_of_the_dominator", "economy"),
    ("tidehunter_dead_in_the_water", "leash"),
    ("puck_dream_coil", "leash"),
    ("naga_siren_ensnare", "root"),
    ("furion_sprout", "terrain"),
    ("earthshaker_fissure", "terrain"),
    ("rattletrap_power_cogs", "terrain"),
    ("death_prophet_exorcism", "aoe_damage"),
    ("monkey_king_wukongs_command", "aoe_damage"),
]
REJECTED = [
    ("winter_wyvern_winters_curse", "applies_basic_dispel"),
    ("tidehunter_dead_in_the_water", "root"),
    ("kunkka_tidebringer", "attack_modifier"),
    ("magic_stick", "charges"),
    ("drow_ranger_wave_of_silence", "true_sight"),
    ("dust", "true_sight"),
]
NOT_WRITTEN = [
    ("branches", "terrain"),
    ("hoodwink_acorn_shot", "terrain"),
    ("weaver_threads_of_fate", "leash"),
    ("enigma_black_hole", "bind"),
    ("shadow_shaman_shackles", "bind"),
    ("spectre_desolate", "taunt"),
]


def _doc():
    return json.loads((PACKAGE / "facts-v12.json").read_text(encoding="utf-8"))


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = json.loads((package / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_matches_manifest_and_replays(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, _ = builder.run(tmp_path / "v12")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)


def test_derived_v2_replays_without_touching_v1_builder(tmp_path):
    _verify_receipt(DERIVED)
    before = derived_v1.FACTS, derived_v1.RULES, derived_v1.MAPPING
    derived_v2.run(tmp_path / "derived")
    assert (derived_v1.FACTS, derived_v1.RULES, derived_v1.MAPPING) == before
    fresh = (tmp_path / "derived/counter-graph.json").read_text(encoding="utf-8")
    assert fresh == (DERIVED / "counter-graph.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("subject,mechanism", ACCEPTED)
def test_user_accepts(subject, mechanism):
    rows = _rows(_doc(), subject, mechanism)
    assert any(r["decision"] == "accept" and r["basis"].startswith("user:") for r in rows)


@pytest.mark.parametrize("subject,mechanism", REJECTED)
def test_user_rejects(subject, mechanism):
    rows = _rows(_doc(), subject, mechanism)
    assert rows and all(r["decision"] == "reject" and r["basis"].startswith("user:") for r in rows)


@pytest.mark.parametrize("subject,mechanism", NOT_WRITTEN)
def test_declined_candidates_are_not_rows(subject, mechanism):
    assert not _rows(_doc(), subject, mechanism)


def test_retired_terms_left_the_rows_and_vocabulary():
    doc = _doc()
    vocabulary = json.loads((ROOT / doc["vocabulary"]).read_text(encoding="utf-8"))
    terms = {m["id"] for m in vocabulary["mechanisms"]}
    assert {r["mechanism"] for r in doc["rows"]} <= terms
    assert not terms & {"forced_action", "mobility_lock"}
    assert {r["mechanism"] for r in doc["retired_term_rows"]} == {"forced_action", "mobility_lock"}


def test_bind_rows_also_count_as_disarm():
    doc = _doc()
    bound = [r for r in doc["rows"] if r["mechanism"] == "bind" and r["decision"] == "accept"]
    assert len(bound) == 5
    for row in bound:
        assert any(r["decision"] == "accept" for r in _rows(doc, row["subject"], "disarm"))
        assert not any(r["decision"] == "accept" for r in _rows(doc, row["subject"], "root"))


def test_glacier_stays_ai_only():
    rows = _rows(_doc(), "drow_ranger_glacier", "terrain")
    assert [r["basis"] for r in rows] == ["two_ai"]


def _row(subject, mechanism, decision="accept", basis="two_ai"):
    condition = {"context": "base", "requires_scepter": False, "requires_shard": False}
    return {
        "review_id": subject,
        "subject": subject,
        "mechanism": mechanism,
        "condition": condition,
        "decision": decision,
        "basis": basis,
        "notes_zh": [],
    }


def test_unmapped_accepted_row_under_retired_term_fails():
    doc = {"rows": [_row("a", "forced_action")], "counts": {}}
    with pytest.raises(ValueError):
        apply_rulings(doc, [], {}, {})


def test_ai_operation_cannot_change_an_existing_row():
    doc = {"rows": [_row("a", "stun", "reject")], "counts": {}}
    entry = {
        "op": "set",
        "subject": "a",
        "mechanism": "stun",
        "decision": "accept",
        "basis": "two_ai",
        "note_zh": "n",
    }
    with pytest.raises(ValueError):
        apply_rulings(doc, [entry], {}, {})
    ruled = apply_rulings(doc, [{**entry, "basis": "user:U89"}], {}, {})
    assert ruled["rows"][0]["decision"] == "accept"
    assert doc["rows"][0]["decision"] == "reject"


def test_condition_label():
    assert condition_label({"context": "item"}) == "item"
    assert condition_label({"context": "base", "requires_shard": True}) == "shard"
