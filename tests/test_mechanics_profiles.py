"""MK-T5 hero profiles follow facts and rules and keep confirmation status visible."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_profiles as builder  # noqa: E402

from dota_items.data.mechanics_profiles import condition_label, confirmed  # noqa: E402


def _profile(tmp_path, hero_id=8):
    return builder.run([hero_id], tmp_path / "profiles")[0]


def test_juggernaut_profile_links_facts_and_rules(tmp_path):
    profile = _profile(tmp_path)
    abilities = {a["name_zh"]: a for a in profile["abilities"]}
    assert {m["id"] for m in abilities["剑刃风暴"]["mechanisms"]} >= {
        "aoe_damage",
        "debuff_immunity",
    }
    assert abilities["剑舞"]["mechanisms"][0]["id"] in {"break_sensitive", "critical"}
    assert abilities["治疗守卫"]["numeric_upgrades"][0]["kind"] == "治疗/回复"
    rules = {rule["rule"]: rule for rule in profile["countered_by"]}
    assert "白银之锋" in rules["R04"]["items"]
    assert abilities["无敌斩"]["pierces_debuff_immunity"] is True
    assert "R20" not in rules
    assert "剑刃风暴" in rules["R10"]["own_abilities"]


def test_output_never_overwrites_and_writes_markdown(tmp_path):
    builder.run([8], tmp_path / "out")
    assert "主宰" in (tmp_path / "out" / "hero-8.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "out" / "profiles.json").read_text())["profiles"]
    try:
        builder.run([8], tmp_path / "out")
    except ValueError as error:
        assert "exists" in str(error)
    else:
        raise AssertionError("overwrite allowed")


def test_labels_and_confirmation():
    assert confirmed("user:U40") and confirmed("user_spot_check")
    assert confirmed("field:IsBreakable")
    assert not confirmed("two_ai")
    assert condition_label({"context": "shard_upgrade"}) == "魔晶"
    assert condition_label({"context": "base", "requires_scepter": True}) == "A杖"
    assert condition_label({"context": "base"}) == ""
