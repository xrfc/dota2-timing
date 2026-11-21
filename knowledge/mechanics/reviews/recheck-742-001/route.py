"""Route every rechecked row to a lane, with Claude's call on rows where Codex did not say holds.

Run from this directory after `results/` is complete. Writes `claude-review.json`.
"""

import collections
import glob
import json

facts = {r["review_id"]: r for r in json.load(open("../../extractions/v26/facts-v26.json"))["rows"]}
FIELD = {
    "break_sensitive",
    "unit_target_spell",
    "effect_dispellability",
    "mana_cost",
    "magical_damage",
    "pure_damage",
    "physical_damage",
    "channeled",
}
rows = {
    x["review_id"]: (o, x)
    for f in sorted(glob.glob("batches/*.json"))
    for o in json.load(open(f))
    for x in o["rows"]
}
got = {
    x["review_id"]: x
    for f in glob.glob("results/*.json")
    for o in json.load(open(f))["objects"]
    for x in o["rows"]
}
AGREE_CHANGE = {
    ("abyssal_blade", "slow_resistance"),
    ("ancient_apparition_bone_chill", "slow"),
    ("chen_holy_persuasion", "haste"),
    ("death_prophet_witchcraft", "cooldown_reduction"),
    ("furion_teleportation", "damage_block"),
    ("heavens_halberd", "evasion"),
    ("lycan_wolf_bite", "healing"),
    ("lycan_wolf_bite", "lifesteal"),
    ("morphling_replicate", "illusions"),
    ("morphling_replicate", "self_mobility"),
    ("nevermore_requiem", "magic_resist_reduction"),
    ("revenants_brooch", "lifesteal"),
    ("tinker_warp_grenade", "root"),
}
DISAGREE = {
    (
        "clinkz_wind_walk",
        "damage_block",
    ): "小兵和幻象只打25%是7.42格子血量的统一规则，作用在骷髅弓手上，不是克林克兹自己减伤；归第7类",
    (
        "gyrocopter_flak_cannon",
        "attack_modifier",
    ): "高射火炮本身不给攻击附加效果，只是允许额外攻击触发别的攻击特效；建议保持reject",
    (
        "troll_warlord_battle_trance",
        "slow_resistance",
    ): "“攻击时无法被减速”是更强的减速抵抗（攻击期间100%），建议保持accept并加条件备注",
}
CONFLICT = {
    ("death_prophet_witchcraft", "haste"): "说明仍写获得移速，但基础移速字段从0.5变成0",
    (
        "sandking_epicenter",
        "aoe_damage",
    ): "A杖说明原样保留，但“有A杖升级”标记变成false、A杖数值字段被删",
    (
        "dazzle_innate_weave",
        "healing",
    ): "魔晶说明仍写治疗，但“有魔晶升级”标记变成false、治疗字段被删",
    (
        "pugna_life_drain",
        "channeled",
    ): "说明仍写CHANNELED，但持续施法时间字段从10变成0、改成10秒持续时间",
}
KEEP_USER = {
    "bane_brain_sap",
    "doom_bringer_devour",
    "lycan_summon_wolves",
    "sniper_assassinate",
    "shadow_shaman_fowl_play",
}
OLD_ERROR = {("muerta_spectral_slug", "displace_other"), ("meepo_petrify", "healing")}


def lane(o, r, g, basis):
    key, v = (o["subject"], r["mechanism"]), g["verdict"]
    if key in CONFLICT and v != "holds":
        return "user_cat8", CONFLICT[key]
    if r["mechanism"] in FIELD:
        return "field_rebuild", "由7.42游戏字段重建决定"
    if v == "holds":
        return "keep_two_ai", "同意：7.42变化不影响这一行"
    user = basis.startswith("user")
    if v in ("unclear", "missing") and not user and not o["category"].startswith("4"):
        return "keep_two_ai", "7.42变化没有碰到这个机制；Codex不确定是因为材料里没有当初的依据"
    if user and (o["subject"] in KEEP_USER or v == "unclear"):
        return "keep_user", "保留用户裁定：7.42没有改到它，Codex质疑的是旧判断本身"
    if key in DISAGREE:
        return "user_disagree", DISAGREE[key]
    if key in OLD_ERROR:
        return "user_old_error", "两版原文相同，Codex认为旧条件记错了；不是7.42变化"
    if key == ("enigma_malefice", "summons"):
        return "keep_two_ai", "仍需魔晶，只是触发条件变窄；加备注"
    if user:
        return "user_ruled_changed", "7.42真的改了用户裁定过的行，交用户确认"
    if o["category"].startswith("4"):
        return "user_cat4", "第4类由用户裁定；Claude同意Codex"
    if key in AGREE_CHANGE:
        return "change_two_ai", "同意Codex"
    return "UNROUTED", ""


out = []
for k, (o, r) in rows.items():
    g = got.get(k, {"verdict": "missing", "quote": "", "reason_zh": "Codex漏返回"})
    basis = facts[k]["basis"]
    name, claude = lane(o, r, g, basis)
    out.append(
        {
            "review_id": k,
            "subject": o["subject"],
            "subject_zh": o["name_zh"],
            "category": o["category"],
            "mechanism": r["mechanism"],
            "condition": r["condition"],
            "decision": r["decision"],
            "basis": basis,
            "codex": g["verdict"],
            "codex_quote": g["quote"],
            "codex_reason": g["reason_zh"],
            "lane": name,
            "claude": claude,
        }
    )
print(collections.Counter(x["lane"] for x in out))
print([(x["subject"], x["mechanism"]) for x in out if x["lane"] == "UNROUTED"])
json.dump(
    {"schema": "mechanics-recheck-742/1", "model": "gpt-6.2-astra, effort high", "rows": out},
    open("claude-review.json", "w"),
    ensure_ascii=False,
    indent=1,
)
