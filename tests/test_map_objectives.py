import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_objectives_have_a_basis_and_evidence():
    doc = json.loads((ROOT / "knowledge/map/objectives-v1.json").read_text(encoding="utf-8"))
    ids = [o["id"] for o in doc["objectives"]]
    assert len(ids) == len(set(ids))
    for item in doc["objectives"]:
        assert item["basis"] in doc["basis_values"], item["id"]
        assert item["name_zh"] and item["value"] and item["evidence"], item["id"]


def test_hero_mobility_lists_abilities_with_numbers():
    doc = json.loads((ROOT / "knowledge/awareness/hero-mobility-v1.json").read_text("utf-8"))
    assert doc["heroes"]["npc_dota_hero_antimage"]["abilities"][0]["ability"] == "antimage_blink"
    for hero in doc["heroes"].values():
        for ability in hero["abilities"]:
            assert ability["cooldowns"] and ability["mechanism_basis"]
    assert {"blink", "force_staff"} <= {i["item"] for i in doc["items"]}
