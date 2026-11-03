"""MK-T3 v4: reviewed facts overlay decisions on frozen v3 evidence."""

import json
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics import load_enums, load_vocabulary
from dota_items.data.mechanics_facts_v4 import DEFERRED, RETIRED, build_reviewed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v4"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_facts_v4 as builder  # noqa: E402


@pytest.fixture(scope="module")
def doc():
    return json.loads((PACKAGE / "facts-v4.json").read_text(encoding="utf-8"))


def _row(doc, subject, mechanism):
    rows = [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]
    assert len(rows) == 1
    return rows[0]


def test_package_replays_exactly(tmp_path, doc):
    fresh = builder.run(tmp_path / "v4")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(doc, sort_keys=True)


def test_vocabulary_v4_loads_and_records_user_definitions():
    registry = json.loads((ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text())
    enums_doc = json.loads((ROOT / "knowledge/mechanics/enums-v1.json").read_text())
    enums = load_enums(enums_doc, registry["heroes"])
    vocabulary = json.loads((ROOT / "knowledge/mechanics/vocabulary-v4.json").read_text())
    terms = load_vocabulary(vocabulary, enums)
    assert terms["pierce_evasion"]["zh"] == "克敌机先"
    assert terms["break_sensitive"]["game_file_evidence"] == ["IsBreakable"]


def test_break_rows_match_game_files_and_cover_every_tag(doc):
    tags = builder.load_break_tags(ROOT)
    rows = [r for r in doc["rows"] if r["mechanism"] == "break_sensitive"]
    for row in rows:
        assert (row["decision"] == "accept") == (tags.get(row["subject"]) == "1"), row["subject"]
    accepted = {r["subject"] for r in rows if r["decision"] == "accept"}
    abilities = {
        ability["name"]
        for hero in json.loads(
            (ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text()
        )["heroes"]
        for ability in hero["abilities"]
    }
    assert accepted == {name for name in abilities if tags.get(name) == "1"}


def test_user_rulings_override_ai_and_retired_items_stay_out(doc):
    assert _row(doc, "mars_bulwark", "break_sensitive")["break_conditions_en"]
    assert _row(doc, "shadow_shaman_shackles", "stun")["decision"] == "accept"
    assert _row(doc, "shadow_shaman_fowl_play", "invulnerable_untargetable")["basis"] == "user:U52"
    assert _row(doc, "nullifier", "mute")["decision"] == "reject"
    assert _row(doc, "abyssal_underlord_dark_portal", "channeled")["decision"] == "reject"
    assert _row(doc, "greater_crit", "critical")["decision"] == "accept"
    assert all(row["item_status"] not in RETIRED for row in doc["rows"])
    assert all(row["item_status"] in RETIRED for row in doc["retired_rows"])
    assert all(row["item_status"] not in DEFERRED for row in doc["rows"])
    assert all(row["item_status"] in DEFERRED for row in doc["deferred_rows"])
    assert doc["deferred_rows"]
    assert doc["open_ai_conflicts"] == []
    keys = [
        (row["subject"], row["mechanism"], json.dumps(row["condition"], sort_keys=True))
        for row in doc["rows"]
    ]
    assert len(keys) == len(set(keys))


def test_break_mismatch_without_ruling_fails_loudly():
    sources = {
        "item_status": {},
        "rulings": {},
        "break_conditions": {},
        "codex": {},
        "verdicts": {},
        "audit": [],
        "user_added": [],
        "field_observations": [],
        "break_tags": {},
        "claude": {"a": {"decision": "accept"}},
        "review_rows": [
            {
                "review_id": "a",
                "subject": "x",
                "mechanism": "break_sensitive",
                "hero_zh": "",
                "name_zh": "x",
                "condition": {},
                "quotes": [],
            }
        ],
    }
    with pytest.raises(ValueError, match="IsBreakable"):
        build_reviewed(sources)
