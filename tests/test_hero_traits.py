"""U23 hero traits: rule candidates, label validation against the registry, and the real file."""

import json
from pathlib import Path

import pytest

from dota_items.data import hero_traits as ht

ROOT = Path(__file__).resolve().parents[1]


def ability(name, behavior=0, team=0, damage=0, kind=0, values=(), text="", **kw):
    return {
        "name_zh": name,
        "description_en": text,
        "notes_en": [],
        "special_values": [{"name": n, "values_float": v} for n, v in values],
        "raw_mechanics": {
            "behavior": str(behavior),
            "target_team": team,
            "damage": damage,
            "type": kind,
        },
        "granted_by_scepter": kw.get("scepter", False),
        "granted_by_shard": False,
    }


HERO = {
    "hero_id": 1,
    "name_zh": "甲",
    "abilities": [
        ability("指向一", 8, 2, 2, values=[("damage", [100, 400])]),
        ability("被动", 2 | 8, 2, 2, values=[("damage", [900])]),  # passive: ignored
        ability("友方", 8, 1),
        ability("大招", 8, 2, 4, kind=1, values=[("damage", [500]), ("damage_pct", [99])]),
        ability("A杖", 8, 2, 2, values=[("damage", [999])], scepter=True),
        ability("闪避", 4, text="Gains evasion."),
    ],
}


def test_rule_candidates_use_raw_enums_base_kit_and_damage_names():
    assert ht.targeted(HERO["abilities"]) == [("指向一", False), ("大招", True)]
    assert ht.burst(HERO["abilities"]) == [("指向一", 400.0), ("大招", 500.0)]
    c = ht.candidates(HERO)
    assert c["targeted_spells"]["candidate"] and c["magic_burst"]["candidate"]
    assert c["evasion"]["evidence"] == ["闪避"]


def doc(labels):
    return {"traits": dict.fromkeys(ht.TRAITS, {}), "labels": labels}


def test_load_traits_validates_hero_ability_and_duplicates():
    entry = {"hero": "甲", "abilities": ["闪避"], "confidence": "high"}
    traits = ht.load_traits(doc({"evasion": [entry]}), [HERO])
    assert traits["evasion"] == {1: entry}
    assert traits["targeted_spells"][1]["confidence"] == "rule"
    for labels, message in (
        ({"evasion": [{**entry, "hero": "乙"}]}, "Unknown hero"),
        ({"evasion": [{**entry, "abilities": ["没有"]}]}, "Bad evidence"),
        ({"evasion": [{**entry, "confidence": "sure"}]}, "Bad evidence"),
        ({"evasion": [entry, entry]}, "Duplicate"),
        ({"targeted_spells": [entry]}, "Unexpected"),
    ):
        with pytest.raises(ValueError, match=message):
            ht.load_traits(doc(labels), [HERO])


def test_real_label_file_matches_the_registry():
    registry = json.loads((ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text())
    labels = json.loads((ROOT / "knowledge/hero-traits/hero-traits-v1.json").read_text())
    traits = ht.load_traits(labels, registry["heroes"])
    assert 44 in traits["evasion"] and traits["evasion"][44]["subtype"] == "self_evasion"
    assert 26 in traits["targeted_spells"]  # Lion: rule-based


def test_text_candidates_ignore_engine_fields_and_substring_hits():
    plain = ability(
        "普通",
        values=[("AbilityManaCost", [100]), ("AbilityCharges", [2])],
        text="Moves towards the target and pushes it forward. Stores 2 charges.",
    )
    c = ht.candidates({"hero_id": 2, "name_zh": "乙", "abilities": [plain]})
    for trait in ("mana_dependent", "illusions_summons", "mobility"):
        assert not c[trait]["candidate"], trait
    hits = [
        ability("冲", text="Charges at an enemy."),
        ability("眼", text="Places an observer ward."),
        ability("法", text="Deals damage based on current mana."),
    ]
    c = ht.candidates({"hero_id": 3, "name_zh": "丙", "abilities": hits})
    assert c["mobility"]["evidence"] == ["冲"]
    assert c["illusions_summons"]["evidence"] == ["眼"]
    assert c["mana_dependent"]["evidence"] == ["法"]


def test_mana_dependent_also_flags_high_total_mana_cost():
    costly = [ability(f"技{i}", values=[("AbilityManaCost", [100, 250])]) for i in range(3)]
    c = ht.candidates({"hero_id": 4, "name_zh": "丁", "abilities": costly})
    assert c["mana_dependent"]["candidate"]
    assert c["mana_dependent"]["evidence"] == ["技0 250", "技1 250", "技2 250"]
    assert "total 750" in c["mana_dependent"]["rule"]
