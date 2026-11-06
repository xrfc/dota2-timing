"""MK-T6d version check: helpers and the stored report (U99, U113)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "knowledge/mechanics/reviews/patch-check-001"
sys.path.insert(0, str(ROOT / "scripts"))

import check_patch_knowledge as check  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_words_ignore_markup_numbers_and_placeholders():
    assert check._words("<h1>Active</h1> Restores %amount% mana 150") == {
        "active",
        "restores",
        "mana",
    }
    assert check._similarity(set(), set()) == 1.0
    assert check._similarity({"a"}, {"b"}) == 0.0


def test_quote_support_flags_missing_text_and_changed_numbers():
    valve = {
        "x": {
            "desc_loc": "Stuns the target.",
            "special_values": [
                {"name": "bonus_regen", "values_float": [4], "heading_loc": "+$hp_regen"}
            ],
        }
    }
    rows = [
        {"subject": "x", "mechanism": "stun", "basis": "two_ai", "quotes": ["Stuns the target."]},
        {
            "subject": "x",
            "mechanism": "healing",
            "basis": "two_ai",
            "quotes": ["+ 4 Health Regeneration"],
        },
        {
            "subject": "x",
            "mechanism": "healing",
            "basis": "two_ai",
            "quotes": ["+ 5 Health Regeneration"],
        },
        {
            "subject": "x",
            "mechanism": "silence",
            "basis": "two_ai",
            "quotes": ["Silences enemies."],
        },
    ]
    flagged = check.quote_support(rows, valve)
    assert [(f["mechanism"], f["flags"]) for f in flagged] == [
        ("healing", ["number_differs"]),
        ("silence", ["quote_not_found"]),
    ]


def test_stored_report_is_fully_reviewed():
    report = _load(CHECK / "report.json")
    review = _load(CHECK / "review.json")
    assert report["abilities"]["missing_from_current_valve_data"] == []
    flagged = {x["subject"] for x in report["items"]["flagged"]}
    flagged |= {x["subject"] for x in report["items"]["quotes_flagged"]}
    assert flagged == {x["subject"] for x in review["items"]}
    assert all(x["verdict"] == "false_alarm" for x in review["items"])


def test_game_scripts_did_not_change_since_the_pinned_mirror_commit():
    mirror = _load(CHECK / "mirror-check.json")
    assert mirror["game_scripts_changed"] == []
    assert mirror["official_patch_list"]["latest"] == "7.41f"


def test_hero_datafeed_matches_the_previous_snapshot():
    diff = _load(ROOT / "knowledge/hero-capabilities/snapshots/2026-11-06/diff-vs-2026-11-01.json")
    assert all(not lang["changes"] for lang in diff["languages"].values())
