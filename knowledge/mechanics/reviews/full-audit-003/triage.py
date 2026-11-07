"""Sort the recheck differences into action groups. Run from repo root. Writes triage.json."""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
# Codex said accept, but under another condition, and that row already exists.
KEEP_EVIDENCE = {
    ("broodmother_spin_web", "charges"): "字段AbilityCharges=3/5/7/9，盲审材料没有数值",
    ("phantom_assassin_phantom_strike", "charges"): "字段AbilityCharges=2，盲审材料没有数值",
    ("mars_gods_rebuke", "slow"): "字段knockback_slow标签KNOCKBACK SLOW，40%",
    ("elder_titan_echo_stomp", "sleep"): "U51：没有眩晕，睡眠另记；字段标签SLEEP DURATION",
    ("lone_druid_spirit_bear", "root"): "用户2026-11-01答4.3：缠绕之爪会定身",
    ("keeper_of_the_light_spirit_form", "healing"): "U45后续裁定：基础组保留",
    ("zuus_lightning_hands", "aoe_damage"): "弧形闪电说明写跳跃穿越附近敌人，盲审只给了本技能文字",
    ("tusk_tag_team", "incoming_damage_amp"): "定义是受到更多物理伤害，没有要求倍率",
    ("puck_illusory_orb", "self_mobility"): "灵动之翼是法球的子技能，没有单独对象",
    ("ember_spirit_sleight_of_fist", "attack_modifier"): "施放型技能打出的攻击，按U83筛选口径不算",
    ("ringmaster_the_box", "mute"): "施加给被保护的友军，是代价不是控制",
    ("ringmaster_the_box", "silence"): "施加给被保护的友军，是代价不是控制",
    ("furion_sprout", "aoe_damage"): "Codex只是不确定，文字只写单个目标",
}
ASK = {
    ("drow_ranger_wave_of_silence", "true_sight"): "真视",
    ("dust", "true_sight"): "真视",
    ("ringmaster_spotlight", "true_sight"): "真视",
    ("magic_stick", "charges"): "充能",
    ("magic_wand", "charges"): "充能",
    ("skeleton_king_bone_guard", "charges"): "充能",
    ("storm_spirit_overload", "charges"): "充能",
    ("kez_shodo_sai", "critical"): "数值升级",
    ("kez_shodo_sai", "stun"): "数值升级",
    ("slardar_seaborn_sentinel", "healing"): "数值升级",
    ("visage_summon_familiars", "stun"): "召唤物自带",
    ("visage_summon_familiars", "invulnerable_untargetable"): "召唤物自带",
    ("brewmaster_primal_split", "phased"): "召唤物自带",
    ("life_stealer_infest", "applies_basic_dispel"): "误读",
    ("kunkka_tidebringer", "attack_modifier"): "攻击特效",
    ("slark_saltwater_shiv", "attack_modifier"): "攻击特效",
    ("doom_bringer_infernal_blade", "attack_modifier"): "攻击特效",
    ("helm_of_the_dominator", "economy"): "赏金",
    ("helm_of_the_overlord", "economy"): "赏金",
    ("puck_dream_coil", "mobility_lock"): "限制位移",
    ("tidehunter_dead_in_the_water", "mobility_lock"): "限制位移",
}


def main():
    data = json.loads((OUT / "comparison.json").read_text(encoding="utf-8"))
    groups = {"other_condition": [], "redundant_upgrade": [], "keep": [], "ask": []}
    for row in data["differences"]:
        key = (row["subject"], row["mechanism"])
        if row["new"] == "accept" and not row["condition_correct"]:
            group = "other_condition" if row["old"] == "reject" else "redundant_upgrade"
            groups[group].append(row)
        elif key in KEEP_EVIDENCE:
            groups["keep"].append({**row, "why_zh": KEEP_EVIDENCE[key]})
        else:
            groups["ask"].append({**row, "topic_zh": ASK[key]})
    print({name: len(rows) for name, rows in groups.items()})
    (OUT / "triage.json").write_text(
        json.dumps(groups, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
