"""Turn U85-U89 into ordered operations for facts v12. Run from repo root.

`set` changes or adds a row; `move` puts a row under a new mechanism. Order matters: rulings
on old terms come first, then moves, then rows under new terms.
"""

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
TARGET = ROOT / "knowledge/mechanics/reviews/recheck-rulings-001.jsonl"


def s(subject, mechanism, decision, ref, note, condition=None, quote=""):
    entry = {"op": "set", "subject": subject, "mechanism": mechanism, "decision": decision}
    entry |= {"basis": f"user:{ref}", "note_zh": note, "condition": condition, "quote": quote}
    return entry


def move(subject, old, new, condition=None):
    return {"op": "move", "subject": subject, "mechanism": old, "new": new, "condition": condition}


U5 = "第5题确认"
ACCEPT_U87 = [
    ("arc_warden_tempest_double", "summons", None),
    ("crystal_maiden_freezing_field", "root", "scepter"),
    ("faceless_void_chronosphere", "stun", "base"),
    ("medusa_cold_blooded", "stun", "shard"),
    ("tusk_walrus_punch", "stun", "base"),
    ("winter_wyvern_winters_curse", "stun", "base"),
    ("necrolyte_sadist", "healing", "base"),
    ("travel_boots", "self_mobility", None),
]
ACCEPT_U86 = [
    ("storm_spirit_ball_lightning", "aoe_damage", "球状闪电算范围伤害"),
    ("storm_spirit_ball_lightning", "invulnerable_untargetable", "球状闪电算无敌"),
    ("storm_spirit_ball_lightning", "self_mobility", "球状闪电算位移"),
    ("viper_nose_dive", "aoe_damage", "极恶俯冲算范围伤害"),
    ("viper_nose_dive", "self_mobility", "极恶俯冲算位移"),
    ("life_stealer_infest", "healing", "感染还有回复"),
    (
        "void_spirit_dissimilate",
        "invulnerable_untargetable",
        "异化：用户说“还有位移”，助手理解为原记录也对",
    ),
    ("void_spirit_dissimilate", "self_mobility", "异化还有位移"),
    ("faceless_void_time_lock", "bash", "时间锁定：用户说“还有眩晕”，助手理解为原记录也对"),
    (
        "life_stealer_infest",
        "invulnerable_untargetable",
        "感染：用户说“还有回复”，助手理解为原记录也对",
    ),
    ("visage_summon_familiars", "stun", "召唤物自带的能力算"),
    ("visage_summon_familiars", "invulnerable_untargetable", "召唤物自带的能力算"),
    ("brewmaster_primal_split", "phased", "召唤物自带的能力算"),
    ("slark_saltwater_shiv", "attack_modifier", "用户确认是普攻附带"),
    ("doom_bringer_infernal_blade", "attack_modifier", "用户确认是普攻附带"),
    ("helm_of_the_dominator", "economy", "多数情况是为了经济经验才出的"),
    ("helm_of_the_overlord", "economy", "多数情况是为了经济经验才出的"),
]
REJECT_U86 = [
    ("winter_wyvern_winters_curse", "applies_basic_dispel", None, "寒冬诅咒没有驱散"),
    ("furion_sprout", "mobility_lock", None, "发芽不限制位移，只是创造地形"),
    ("magic_stick", "charges", None, "充能：不是用一次消耗一点"),
    ("magic_wand", "charges", None, "充能：不是用一次消耗一点"),
    ("skeleton_king_bone_guard", "charges", None, "充能：一次消耗全部能量"),
    ("storm_spirit_overload", "charges", "shard", "充能：是攻击消耗的次数"),
    ("kez_shodo_sai", "critical", "shard", "只加数值的升级"),
    ("kez_shodo_sai", "stun", "shard", "只加数值的升级"),
    ("slardar_seaborn_sentinel", "healing", "scepter", "只加数值的升级"),
    ("ember_spirit_fire_remnant", "charges", "shard", "基础已有，升级不重复记"),
    ("mirana_leap", "charges", "shard", "基础已有，升级不重复记"),
    ("mirana_leap", "self_mobility", "shard", "基础已有，升级不重复记"),
    ("pudge_meat_hook", "displace_other", "shard", "基础已有，升级不重复记"),
    ("rubick_telekinesis", "displace_other", "shard", "基础已有，升级不重复记"),
    ("muerta_dead_shot", "forced_action", "scepter", "基础已有，升级不重复记"),
    ("bane_brain_sap", "healing", "shard", "基础已有，升级不重复记"),
    ("viper_corrosive_skin", "slow", "scepter", "基础已有，升级不重复记"),
    ("rubick_spell_steal", "spell_steal", "shard", "基础已有，升级不重复记"),
    ("sniper_assassinate", "stun", "scepter", "基础已有，升级不重复记"),
]
TAUNT = [
    "axe_berserkers_call",
    "enchantress_little_friends",
    "huskar_life_break",
    "legion_commander_duel",
    "troll_warlord_battle_trance",
    "winter_wyvern_winters_curse",
]
FEAR = [
    "dark_willow_terrorize",
    "death_prophet_spirit_siphon",
    "lone_druid_savage_roar",
    "muerta_dead_shot",
    "nevermore_requiem",
    "ringmaster_tame_the_beasts",
    "spectre_haunt",
    "terrorblade_terror_wave",
]
HYPNOTIZE = [
    "bane_nightmare",
    "keeper_of_the_light_will_o_wisp",
    "lich_sinister_gaze",
    "ringmaster_wheel",
]
BIND = [
    "crystal_maiden_frostbite",
    "crystal_maiden_crystal_clone",
    "crystal_maiden_freezing_field",
    "treant_leech_seed",
    "treant_overgrowth",
]
LEASH = ["grimstroke_soul_chain", "puck_dream_coil", "slark_pounce", "tidehunter_dead_in_the_water"]
TERRAIN_MOVED = [
    "disruptor_kinetic_field",
    "disruptor_kinetic_fence",
    "furion_sprout",
    "mars_arena_of_blood",
    "tusk_ice_shards",
]


def codex_quotes():
    quotes = {}
    for path in sorted(glob.glob(str(OUT / "results/batch-*.json"))):
        for obj in json.loads(Path(path).read_text(encoding="utf-8"))["objects"]:
            for found in obj["mechanisms"]:
                quotes[(obj["subject"], found["mechanism"])] = found["quote"]
    return quotes


def main():
    quotes = codex_quotes()
    ops = []
    for subject, mechanism, condition in ACCEPT_U87:
        ops.append(s(subject, mechanism, "accept", "U87", U5, condition))
    for subject, mechanism, note in ACCEPT_U86:
        ops.append(s(subject, mechanism, "accept", "U86", note))
    for subject, mechanism, condition, note in REJECT_U86:
        ops.append(s(subject, mechanism, "reject", "U86", note, condition))
    ops += [
        s(
            "winter_wyvern_winters_curse",
            "invulnerable_untargetable",
            "accept",
            "U86",
            "目标可以选取；目标以外的敌方单位获得无敌",
        ),
        s(
            "faceless_void_time_lock",
            "stun",
            "accept",
            "U86",
            "时间锁定还有眩晕",
            "base",
            "攻击有一定概率将一个敌方目标锁定在时间中",
        ),
        s("life_stealer_infest", "applies_basic_dispel", "accept", "U86", "弱驱散自身"),
        s("puck_dream_coil", "mobility_lock", "accept", "U86", "闪烁和TP会被禁用"),
        s(
            "monkey_king_wukongs_command",
            "aoe_damage",
            "accept",
            "U87",
            "有固定范围，范围内敌人基本都受伤害",
        ),
        s(
            "death_prophet_exorcism",
            "aoe_damage",
            "accept",
            "U87",
            "有固定范围，范围内敌人基本都受伤害",
        ),
        s("kunkka_tidebringer", "attack_modifier", "reject", "U87", "潮汐使者只算分裂"),
        s("tidehunter_dead_in_the_water", "root", "reject", "U88", "按束缚处理"),
        s("tidehunter_dead_in_the_water", "mobility_lock", "accept", "U88", "按束缚处理"),
        s("winter_wyvern_winters_curse", "forced_action", "accept", "U88", "寒冬诅咒算嘲讽"),
        s("enchantress_little_friends", "forced_action", "accept", "U88", "密友算嘲讽"),
        s(
            "troll_warlord_battle_trance",
            "forced_action",
            "accept",
            "U88",
            "嘲讽自身，取代U83的强制行为",
        ),
        s("bane_nightmare", "forced_action", "accept", "U88", "噩梦算蛊惑"),
        s("bane_nightmare", "sleep", "accept", "U88", "噩梦算睡眠"),
        s("naga_siren_ensnare", "root", "accept", "U88", "诱捕游戏里写的是缠绕"),
    ]
    for subject in ("drow_ranger_wave_of_silence", "dust", "ringmaster_spotlight"):
        ops.append(s(subject, "true_sight", "reject", "U87", "说明只写显形，只留显形"))
    for subject in TERRAIN_MOVED:
        ops.append(s(subject, "mobility_lock", "accept", "U89", "算创造地形"))
    ops += [move(subject, "forced_action", "taunt") for subject in TAUNT]
    ops += [move(subject, "forced_action", "fear") for subject in FEAR]
    ops += [move(subject, "forced_action", "hypnotize") for subject in HYPNOTIZE]
    ops += [move(subject, "root", "bind") for subject in BIND]
    ops += [move(subject, "mobility_lock", "leash") for subject in LEASH]
    ops += [move(subject, "mobility_lock", "terrain") for subject in TERRAIN_MOVED]
    for subject, condition in (("earthshaker_fissure", "base"), ("rattletrap_power_cogs", "base")):
        ops.append(
            s(
                subject,
                "terrain",
                "accept",
                "U89",
                "算创造地形",
                condition,
                quotes[(subject, "terrain")],
            )
        )
    ops += [
        {
            "op": "set",
            "subject": "drow_ranger_glacier",
            "mechanism": "terrain",
            "decision": "accept",
            "basis": "two_ai",
            "note_zh": "Codex提出，用户交给助手判断（U89）；只算AI一致",
            "condition": "shard",
            "quote": quotes[("drow_ranger_glacier", "terrain")],
        },
        s(
            "void_spirit_aether_remnant",
            "hypnotize",
            "accept",
            "U89",
            "残阴是蛊惑",
            "base",
            quotes[("void_spirit_aether_remnant", "hypnotize")],
        ),
        s(
            "bane_nightmare",
            "channeled",
            "accept",
            "U88",
            "这个状态算作bane持续给他作用的",
            "base",
            "让目标敌方或友方英雄进入沉睡",
        ),
        s(
            "crystal_maiden_freezing_field",
            "disarm",
            "accept",
            "U89",
            "捆缚的技能继续记缴械",
            "scepter",
            "都会施加冰封禁制",
        ),
    ]
    TARGET.write_text(
        "".join(json.dumps(op, ensure_ascii=False) + "\n" for op in ops), encoding="utf-8"
    )
    print(len(ops), "operations")


if __name__ == "__main__":
    main()
