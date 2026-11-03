"""MK-T3 v5: vocabulary v5, Codex rounds 5-6 and later rulings."""

import hashlib
import json
from pathlib import Path

import pytest

from dota_items.data.mechanics import load_enums, load_vocabulary
from dota_items.data.mechanics_facts_v4 import DEFERRED, RETIRED

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v5"


@pytest.fixture(scope="module")
def doc():
    return json.loads((PACKAGE / "facts-v5.json").read_text(encoding="utf-8"))


def _row(doc, subject, mechanism):
    rows = [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]
    assert len(rows) == 1
    return rows[0]


def test_package_matches_manifest():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected


def test_vocabulary_v5_adds_ethereal():
    registry = json.loads((ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text())
    enums_doc = json.loads((ROOT / "knowledge/mechanics/enums-v1.json").read_text())
    enums = load_enums(enums_doc, registry["heroes"])
    vocabulary = json.loads((ROOT / "knowledge/mechanics/vocabulary-v5.json").read_text())
    terms = load_vocabulary(vocabulary, enums)
    assert terms["ethereal"]["zh"] == "虚无"
    assert "ethereal" in terms["cyclone_banish"]["note"]


def test_rulings_and_reviews_are_applied(doc):
    assert doc["open_ai_conflicts"] == []
    assert not [r for r in doc["rows"] if r["basis"] == "ai_conflict"]
    assert _row(doc, "pugna_decrepify", "cyclone_banish")["decision"] == "reject"
    assert _row(doc, "pugna_decrepify", "ethereal")["decision"] == "accept"
    assert _row(doc, "muerta_spectral_slug", "ethereal")["condition"]["requires_shard"] is True
    assert _row(doc, "nyx_assassin_burrow", "stun")["decision"] == "reject"
    assert _row(doc, "arc_warden_tempest_double", "invisibility")["condition"]["requires_shard"]
    assert sum(1 for r in doc["rows"] if r["mechanism"] == "ethereal") == 8


def test_retired_and_deferred_items_stay_out(doc):
    assert all(r["item_status"] not in RETIRED | DEFERRED for r in doc["rows"])
    assert all(r["item_status"] in DEFERRED for r in doc["deferred_rows"])
