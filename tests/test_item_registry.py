"""Item registry: join rules, id agreement, display fallback, and the stored snapshot."""

import json
from pathlib import Path

import pytest

from dota_items.data.item_registry import build_registry, display_name, load_registry

ROOT = Path(__file__).resolve().parents[1]


def valve(*items):
    return {"result": {"data": {"itemabilities": list(items)}}}


def v(item_id, key, zh, en, tier=-1):
    return {
        "id": item_id,
        "name": f"item_{key}",
        "name_loc": zh,
        "name_english_loc": en,
        "neutral_item_tier": tier,
    }


def test_join_marks_completed_items_and_keeps_official_names():
    registry = build_registry(
        valve(v(1, "blink", "闪烁匕首", "Blink Dagger"), v(3, "broadsword", "大剑", "Broadsword")),
        {
            "blink": {"id": 1, "cost": 2250, "components": None, "created": False},
            "bfury": {
                "id": 145,
                "dname": "Battle Fury",
                "components": ["broadsword"],
                "created": True,
            },
        },
    )["items"]
    assert registry["blink"]["name_zh"] == "闪烁匕首" and not registry["blink"]["completed"]
    assert registry["bfury"]["completed"] and registry["bfury"]["components"] == ["broadsword"]
    assert registry["bfury"]["name_zh"] is None and registry["bfury"]["sources"] == [
        "dotaconstants"
    ]
    assert display_name(registry, "bfury") == "Battle Fury"
    assert display_name(registry, "unknown_item") == "unknown_item"


def test_id_conflict_rejected():
    with pytest.raises(ValueError, match="conflicts"):
        build_registry(valve(v(1, "blink", "闪烁匕首", "Blink")), {"blink": {"id": 2}})


def test_stored_registry_matches_sources_and_known_items():
    path = ROOT / "knowledge/items/item-registry.json"
    items = load_registry(path)
    stored = json.loads(path.read_text())
    sources = ROOT / "knowledge/items/sources"
    rebuilt = build_registry(
        json.loads((sources / "itemlist-schinese.json").read_text()),
        json.loads((sources / "dotaconstants-items.json").read_text()),
    )
    assert rebuilt["items"] == stored["items"]
    essence = items["essence_distiller"]
    assert essence["name_zh"] == "精之灵器" and essence["completed"]
    assert sorted(essence["components"]) == ["chainmail", "urn_of_shadows", "wizard_hat"]
    assert items["bfury"]["name_zh"] == "狂战斧" and not items["broadsword"]["completed"]
