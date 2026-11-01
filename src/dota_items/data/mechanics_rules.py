"""MK-T3 lexical candidates, not gameplay assertions or interaction rules.

Only prose is searched. Word boundaries avoid towards/forward/AbilityCharges;
structured engine names and special-value keys are never fed to these patterns.
Every text hit requires semantic review (actor, polarity, condition, version).
"""

import re

PATTERNS = {
    "stun": r"眩晕|击晕|晕眩|\bstun(?:s|ned|ning)?\b",
    "hex": r"变成.{0,12}(?:动物|青蛙|小猪|羊)|\bhex(?:es|ed)?\b|harmless critter",
    "silence": r"沉默|\bsilenc(?:e|es|ed|ing)\b",
    "mute": r"禁用物品|无法使用物品|\bmut(?:e|ed|es)\b|cannot use items",
    "disarm": r"缴械|\bdisarm(?:s|ed)?\b",
    "root": r"缠绕|定身|\broot(?:s|ed|ing)?\b",
    "forced_action": r"嘲讽|恐惧|魅惑|\b(?:taunt\w*|fear|hypnotiz\w*)\b",
    "sleep": r"睡眠|沉睡|\b(?:sleep|asleep|slumber)\b",
    "cyclone_banish": r"吹起|吹风|放逐|\b(?:cyclone|banish\w*)\b",
    "slow": r"减速|降低.{0,12}(?:移动|攻击)速度|\bslow(?:s|ed|ing)?\b",
    "evasion": r"闪避|\bevasion\b|\bevade\w*\b",
    "blind": r"致盲|\bblind(?:s|ed|ing)?\b|\bmiss chance\b",
    "debuff_immunity": r"减益免疫|技能免疫|\b(?:debuff|spell) immun(?:ity|e)\b",
    "pierces_debuff_immunity": r"穿透减益免疫|\bpierces? debuff immunity\b",
    "invulnerable_untargetable": r"无敌|不可被选取|无法被选中|\b(?:invulnerab\w*|untargetable)\b",
    "damage_block": (
        r"护盾|吸收.{0,15}伤害|伤害降低|伤害减免|\b(?:barrier|"
        r"damage block)\b|reduces? .{0,20}damage"
    ),
    "death_prevention": (
        r"不会死亡|免于死亡|无法死亡|\bcannot die\b|"
        r"\bprevent\w* .{0,30}(?:dying|death)\b"
    ),
    "status_resistance": r"状态抗性|\bstatus resistance\b",
    "slow_resistance": r"减速抗性|\bslow resistance\b",
    "applies_basic_dispel": r"弱驱散|\bbasic dispel\b",
    "applies_strong_dispel": r"强驱散|\bstrong dispel\b",
    "applies_break": (
        r"施加破坏|造成破坏|破坏效果|禁用.{0,12}被动|\bbreaks? (?:the )?(?:enemy|target|"
        r"passive)|disabl\w* .{0,25}passive abilit"
    ),
    "break_sensitive": (
        r"破坏(?!性|树木).{0,25}(?:被动|失效|禁用)|"
        r"\bbreak\b.{0,50}(?:disable|passive)|passive.{0,50}\bbreak\b"
    ),
    "invisibility": r"隐身|\binvisib\w*\b",
    "true_sight": r"真实视域|真视|\btrue sight\b|reveal\w* .{0,25}invisib",
    "healing": (
        r"治疗|生命恢复|恢复.{0,15}生命|"
        + r"\bheal(?:s|ing)?\b|health regen|restore\w* .{0,20}health"
    ),
    "lifesteal": r"吸血|\blife\s?steal\w*\b",
    "heal_reduction": r"降低.{0,20}(?:治疗|恢复)|治疗削减|reduc\w* .{0,40}(?:heal|regen)",
    "mana_burn": (
        r"(?:损毁|燃烧|削减|吸取).{0,20}(?:魔法|法力)|" + r"\b(?:burn\w*|drain\w*) .{0,30}mana\b"
    ),
    "mana_gain": (
        r"(?:回复|恢复|获得|汲取|吸取)[^。；，]{0,20}(?:魔法|法力)(?!抗性|伤害|消耗)|\b(?:restor\w*|gain\w*|drain\w*|"
        r"regenerat\w*) .{0,45}mana\b|mana regeneration"
    ),
    "illusions": (
        r"(?:制造|产生|创造|创建|召唤).{0,20}幻象|\b(?:creat\w*|"
        r"summon\w*|conjur\w*) .{0,40}illusion"
    ),
    "summons": r"召唤.{0,20}(?:守卫|单位|狼|熊|蛇|骷髅|树人)|\bsummon\w*\b",
    "self_mobility": r"闪烁|冲刺|跳跃|传送|\b(?:blink\w*|teleport\w*|leaps?|dash\w*)\b",
    "displace_other": (
        r"拉回|推开|击退|投掷|交换.{0,10}位置|\b(?:knockback|"
        r"knocks? back|pull\w*|push\w*|swap\w*)\b"
    ),
    "damage_return": r"反弹.{0,15}伤害|反伤|\b(?:return\w*|reflect\w*) .{0,25}damage\b",
    "bash": r"重击|\bbash(?:es)?\b",
    "pierce_evasion": (
        r"克敌击先|必中|穿透闪避|无视闪避|pierce through evasion|"
        r"\btrue strike\b|cannot miss"
    ),
    "critical": r"致命一击|暴击|\bcritical\b",
    "channeled": r"持续施法|持续吟唱|\bchannel(?:ed|ing|led|ling)?\b",
}
RULES = {key: re.compile(value, re.IGNORECASE) for key, value in PATTERNS.items()}
# These indicate a non-assertive mention. We retain no positive candidate from it.
NEGATIVE = re.compile(
    r"(?:does not|doesn't|cannot|can't|will not|without|immune to|unaffected by)\b|"
    r"不会|无法|不能|不提供|不造成|不再|不受|不具有|不产生",
    re.IGNORECASE,
)


def text_hits(text):
    """Yield (mechanism, exact sentence). Hits remain candidates, never auto facts."""
    for match in re.finditer(r"[^。！？.!?\n]+(?:[。！？.!?]|$)", text):
        quote = match.group().strip()
        if not quote:
            continue
        for mid, pattern in RULES.items():
            checked = quote
            if mid == "death_prevention":
                checked = re.sub(r"cannot die|不会死亡|无法死亡", "", checked, flags=re.I)
            elif mid == "pierce_evasion":
                checked = re.sub(r"cannot miss", "", checked, flags=re.I)
            if NEGATIVE.search(checked):
                continue
            if not pattern.search(quote):
                continue
            # Distinguish bypassing a defense from possessing it.
            if mid == "evasion" and re.search(r"pierc|穿透|无视", quote, re.I):
                continue
            if mid == "debuff_immunity" and re.search(r"pierc|穿透", quote, re.I):
                continue
            # Applying break is distinct from being disabled by break.
            if mid == "applies_break" and re.search(r"破坏会|break disables", quote, re.I):
                continue
            yield mid, quote
