"""MK-T3 v6: vocabulary additions, Codex round 7 and the upgrade-number rule."""

import hashlib
import json
from pathlib import Path

import pytest

from dota_items.data.mechanics import load_enums, load_vocabulary
from dota_items.data.mechanics_facts_v4 import DEFERRED, RETIRED

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v6"


@pytest.fixture(scope="module")
def doc():
    return json.loads((PACKAGE / "facts-v6.json").read_text(encoding="utf-8"))


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def test_package_matches_manifest():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected


def test_vocabulary_v6_loads_with_additions():
    registry = json.loads((ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text())
    enums = load_enums(
        json.loads((ROOT / "knowledge/mechanics/enums-v1.json").read_text()), registry["heroes"]
    )
    terms = load_vocabulary(
        json.loads((ROOT / "knowledge/mechanics/vocabulary-v6.json").read_text()), enums
    )
    assert len(terms) == 75
    assert terms["spell_block"]["zh"] == "格挡指向技能"


def test_upgrade_numbers_are_not_mechanisms(doc):
    healing = _rows(doc, "chen_hand_of_god", "healing")
    assert {r["condition"]["context"]: r["decision"] for r in healing} == {"base": "accept"}
    assert not any(
        r["mechanism"] == "cooldown_reduction"
        and r["condition"]["context"] in ("scepter_upgrade", "shard_upgrade")
        for r in doc["rows"]
    )
    assert len(doc["numeric_upgrades"]) == 50
    moved = {(r["subject"], r["kind"]) for r in doc["numeric_upgrades"]}
    assert ("spirit_breaker_nether_strike", "displace_other") in moved
    assert ("keeper_of_the_light_spirit_form", "healing") in moved
    dispersion = _rows(doc, "spectre_dispersion", "damage_block")
    assert [(r["condition"]["context"], r["decision"]) for r in dispersion] == [("base", "accept")]
    assert sum(1 for r in doc["numeric_upgrades"] if r["field_values"]) == 27
    assert _rows(doc, "death_prophet_witchcraft", "cooldown_reduction")[0]["decision"] == "accept"


def test_round_seven_rulings_are_applied(doc):
    assert doc["open_ai_conflicts"] == []
    assert not [r for r in doc["rows"] if r["decision"] == "uncertain"]
    assert _rows(doc, "lotus_orb", "spell_reflect")[0]["decision"] == "accept"
    assert _rows(doc, "veil_of_discord", "magic_resist_reduction")[0]["decision"] == "accept"
    assert _rows(doc, "enchantress_untouchable", "aura") == []
    assert _rows(doc, "chaos_knight_phantasm", "projectile_dodge")[0]["decision"] == "reject"


def test_retired_and_deferred_items_stay_out(doc):
    assert all(r["item_status"] not in RETIRED | DEFERRED for r in doc["rows"])
