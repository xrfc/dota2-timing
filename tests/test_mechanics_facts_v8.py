"""MK-T3 v8 and MK-T4 rules v2: area damage drives the illusion and summon rule."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics import load_enums, load_vocabulary
from dota_items.data.mechanics_interactions import load_rules

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v8"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_facts_v8 as builder  # noqa: E402


@pytest.fixture(scope="module")
def doc():
    return json.loads((PACKAGE / "facts-v8.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rule20():
    data = json.loads((PACKAGE / "rules-evaluation.json").read_text(encoding="utf-8"))
    return next(rule for rule in data["rules"] if rule["id"] == "R20")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def test_package_matches_manifest():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected


def test_package_replays_from_current_inputs(tmp_path, doc):
    fresh, _ = builder.run(tmp_path / "v8")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(doc, sort_keys=True)


def test_rules_v2_load_against_vocabulary_v8():
    registry = json.loads((ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text())
    enums = load_enums(
        json.loads((ROOT / "knowledge/mechanics/enums-v1.json").read_text()), registry["heroes"]
    )
    terms = load_vocabulary(
        json.loads((ROOT / "knowledge/mechanics/vocabulary-v8.json").read_text()), enums
    )
    rules = load_rules(json.loads((ROOT / "knowledge/mechanics/rules-v2.json").read_text()), terms)
    assert len(terms) == 76
    assert len(rules) == 20


def test_aoe_rulings_are_applied(doc, rule20):
    assert doc["open_ai_conflicts"] == []
    assert not [r for r in doc["rows"] if r["decision"] == "uncertain"]
    assert any(
        r["condition"]["context"] == "base" and r["decision"] == "accept"
        for r in _rows(doc, "enigma_black_hole", "aoe_damage")
    )
    assert _rows(doc, "shadow_shaman_mass_serpent_ward", "aoe_damage")[0]["decision"] == "reject"
    assert _rows(doc, "marci_companion_run", "displace_other")[0]["decision"] == "accept"
    sources = set(rule20["sources"])
    assert {"radiance", "earthshaker_echo_slam", "enigma_black_hole"} <= sources
    assert "arcane_boots" not in sources
    assert "pudge_meat_hook" not in sources
