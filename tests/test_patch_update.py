"""MK-T6e patch update flow: status, diffs and impact (offline)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import patch_update as flow  # noqa: E402


def test_status_says_when_a_newer_patch_exists():
    patches = {"patches": [{"patch_number": "7.41f", "patch_timestamp": 1}]}
    assert flow.status(patches, {"name": "7.41f"})["update_needed"] is False
    patches["patches"].append({"patch_number": "7.42", "patch_timestamp": 2})
    result = flow.status(patches, {"name": "7.41f"})
    assert result["update_needed"] is True and result["latest"] == "7.42"


def test_item_diff_lists_added_removed_and_changed_fields():
    old = {"a": {"desc_loc": "x"}, "b": {"desc_loc": "y"}}
    new = {"a": {"desc_loc": "x2"}, "c": {"desc_loc": "z"}}
    changes = flow.item_diff(old, new)["changes"]
    assert changes == [
        {"subject": "a", "change": "item_changed", "fields": ["desc_loc"]},
        {"subject": "b", "change": "item_removed"},
        {"subject": "c", "change": "item_added"},
    ]


def _snapshot(path, text):
    target = path / "sources/scripts/npc/npc_abilities.txt"
    target.parent.mkdir(parents=True)
    target.write_text(text, encoding="utf-8")
    return path


def test_game_diff_compares_blocks_not_files(tmp_path):
    old = _snapshot(
        tmp_path / "old",
        '"DOTAAbilities" { "x_stun" { "AbilityCooldown" "10" } "x_gone" { "A" "1" } }',
    )
    new = _snapshot(
        tmp_path / "new",
        '"DOTAAbilities" { "x_stun" { "AbilityCooldown" "8" } "item_new" { "A" "1" } }',
    )
    changes = flow.game_diff(old, new)["changes"]
    assert changes == [
        {"block": "item_new", "change": "added"},
        {"block": "x_gone", "change": "removed"},
        {"block": "x_stun", "change": "changed", "keys": ["AbilityCooldown"]},
    ]


def test_impact_maps_changes_to_facts_rules_and_edges():
    hero_diff = {
        "languages": {
            "english": {
                "changes": [
                    {
                        "hero": "npc_dota_hero_tidehunter",
                        "ability": "tidehunter_gush",
                        "change": "ability_changed",
                        "text_fields": ["scepter_loc"],
                        "other_fields": [],
                    }
                ]
            }
        }
    }
    items = {"changes": [{"subject": "sphere", "change": "item_changed", "fields": ["desc_loc"]}]}
    result = flow.impact(hero_diff, items)
    subjects = {row["subject"] for row in result["fact_rows_to_recheck"]}
    assert {"tidehunter_gush", "sphere"} <= subjects
    assert {"R13", "R23"} <= set(result["rules_touched"])
    assert result["item_edges_touched"] > 0


def test_no_changes_means_nothing_to_recheck():
    empty = {"languages": {"english": {"changes": []}}}
    result = flow.impact(empty, {"changes": []}, {"changes": []})
    assert result["fact_rows_to_recheck"] == [] and result["rules_touched"] == []


def test_outputs_are_never_overwritten(tmp_path):
    target = tmp_path / "x.json"
    flow._write_new(target, {})
    with pytest.raises(SystemExit):
        flow._write_new(target, {})
