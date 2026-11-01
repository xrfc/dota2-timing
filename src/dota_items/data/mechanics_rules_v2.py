"""MK-T3 lexical candidates, version 2 (U33-U35 and Claude round-1 findings).

Builds on v1 patterns (mechanics_rules) without changing them, so the frozen v1
inventory still replays. Hits stay candidates that need semantic review.

Changes, each traced to round-1 review evidence:
- The subject hero's own names are removed before matching ("魅惑魔女" -> 魅惑,
  "Lifestealer" -> lifesteal).
- Sentences that only describe being affected ("while stunned", "interrupted if
  ... hexed", "dodge stuns") are skipped for control mechanisms.
- Interaction notes ("hits invisible units", "works on spell immune units",
  "reveals invisibility") are skipped for invisibility/immunity mechanisms.
- Look-alike phrases are subtracted before matching (slow resistance, slow heal,
  "leaps between targets", "considered reflected damage", attack-modifier lists).
- Missed wordings are added: "lower ... movement", "prevents ... from attacking",
  counter-attacks (U33), taking control as summons (U35), delayed damage (U33/U35).
"""

import re

from dota_items.data.mechanics_rules import NEGATIVE
from dota_items.data.mechanics_rules import PATTERNS as V1_PATTERNS

OVERRIDES = {
    "slow": V1_PATTERNS["slow"]
    + r"|\blower\w* (?:enemy |the |their )?(?:movement|attack speed)"
    + r"|\breduc\w* (?:the )?(?:movement|attack) speed of"
    + r"|\bhave (?:their )?(?:reduced|lowered) (?:movement|attack) speed",
    "heal_reduction": (
        r"降低.{0,20}(?:治疗|恢复)|恢复.{0,6}降低|治疗削减|"
        r"(?:reduc|lower)\w* .{0,40}(?:\bheal(?:ing|s)?\b|\bregen\w*|restoration)|"
        r"(?:regen\w*|restoration|healing) (?:is |are )?reduced|"
        r"prevent\w* .{0,20}(?:regenerating|healing)(?![^.]{0,20}\bmana\b)"
    ),
    "disarm": V1_PATTERNS["disarm"]
    + r"|prevents? (?:a |the )?(?:target|unit|enemy) from attacking",
    "forced_action": V1_PATTERNS["forced_action"]
    + r"|will attack (?:the )?(?:selected|chosen) target|会攻击[^，。]{0,10}选定的目标",
    "lifesteal": V1_PATTERNS["lifesteal"]
    + r"|regain health for a percentage of (?:the )?damage"
    + r"|heal for a percentage of (?:his |her |the )?target's max(?:imum)? health",
    "summons": (
        r"召唤.{0,20}(?:守卫|单位|狼|熊|蛇|骷髅|树人|魔像|小鬼|猛禽|佣兽|勇士|弓箭手|墓碑|米波)|"
        r"\bsummon\w* .{0,40}\b(?:wards?|units?|wolf|wolves|bear|serpent|skeletons?|golem|"
        r"imps?|familiars?|eidolons?|fragments?|hawks?|treants?|warriors?|archers?|boar|"
        r"zombies?|tombstone|forged spirits?)\b|\bsummons another\b|"
        r"\bconjur\w* .{0,30}familiars?\b|"
        r"\b(?:imps?|wards?|skeletons?|zombies?|units?) (?:is|are) summoned\b|"
        r"\bsplits?\s+(?:\w+\s+)?into elements\b|分裂成元素|"
        r"\btakes? control\b|\bcontrol creeps\b|\bdominat\w*|夺取.{0,6}控制"
    ),
    "damage_return": V1_PATTERNS["damage_return"]
    + r"|counter[\s-]?attack\w*|\bcounters all attacks\b|damage back to the attacker"
    + r"|damages .{0,40}any enemy that damages it|作出反击|进行反击",
    "damage_block": V1_PATTERNS["damage_block"]
    + r"|\bdelay\w* any .{0,20}damage|\bdelayed reaction to\b|延迟[^，。]{0,6}(?:受到|承受)的伤害",
}
PATTERNS = {**V1_PATTERNS, **OVERRIDES}
RULES = {key: re.compile(value, re.IGNORECASE) for key, value in PATTERNS.items()}

CONTROL = {
    "stun",
    "hex",
    "silence",
    "mute",
    "disarm",
    "root",
    "sleep",
    "cyclone_banish",
}
STATE = re.compile(
    r"\b(?:while|when|if|whenever)\b[^,.;]{0,40}\b(?:stunned|hexed|silenced|muted|disarmed|"
    r"rooted|slept|banished|cycloned|disabled)\b|\b(?:interrupted|canceled|cancelled) if\b|"
    r"\bdodge\w*\b|(?:受到|被)(?:眩晕|沉默|妖术|飓风|睡眠|放逐|控制)[^，。]{0,8}"
    r"(?:时|作用时|状态下|会|将)|在(?:眩晕|沉默)状态下|躲避",
    re.IGNORECASE,
)
INTERACTION = re.compile(
    r"\b(?:hits?|affects?|works on|can (?:be cast on|target|hit|heal|shock|travel)|"
    r"triggered by|can see|seek)\b[^.]{0,30}\b(?:invisible|invulnerable|spell immune|"
    r"debuff immune|magic immune)|\breveal\w*\b|对(?:隐身|无敌|减益免疫|技能免疫)[^，。]{0,6}"
    r"(?:单位|有效|无效)|可以(?:对|治疗)[^，。]{0,10}(?:无敌|技能免疫|减益免疫)|揭示|显形",
    re.IGNORECASE,
)
INTERACTION_TERMS = {"invisibility", "debuff_immunity", "invulnerable_untargetable"}
CHANNEL_MENTION = re.compile(
    r"interrupt\w* (?:\w+ )?channel|while channel|cast while channel|"
    r"打断[^，。]{0,6}持续施法|可以在持续施法",
    re.IGNORECASE,
)
SUBTRACT = {
    "slow": r"slow resist\w*|减速抗性|slow heal|slow-moving|\bslowly\b|slows the unicycle",
    "self_mobility": (
        r"\b(?:leaps?|jumps?|bounces?|arcs?) (?:between|to nearby|through|from target)\w*|"
        r"(?:在|于)[^，。]{0,8}之间(?:跳跃|弹跳)|跳跃至[^，。]{0,6}(?:敌|单位|目标|队友)|"
        r"teleporting or blinking will break"
    ),
    "displace_other": r"pulling points|swaps from",
    "damage_return": (
        r"considered reflected damage|immun\w* to reflected[^.]*|cannot be reflected|"
        r"reflected back to (?:her|him)"
    ),
    "critical": r"attack (?:modifier|bonus)\w*[^.]*|攻击特效",
    "bash": r"attack (?:modifier|effect)\w*[^.]*|攻击特效",
    "forced_action": r"strikes fear",
    "summons": r"summon\w* (?:her|his|its) courier",
}
SUBTRACT_RULES = {key: re.compile(value, re.IGNORECASE) for key, value in SUBTRACT.items()}


def strip_names(text, names):
    for name in sorted({n for n in names if n and len(n) > 1}, key=len, reverse=True):
        text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    return text


def text_hits(text, names=()):
    """Yield (mechanism, exact sentence) candidates; matching ignores the given names."""
    for match in re.finditer(r"[^。！？.!?\n]+(?:[。！？.!?]|$)", text):
        quote = match.group().strip()
        if not quote:
            continue
        cleaned = strip_names(quote, names)
        for mid, pattern in RULES.items():
            checked = cleaned
            if mid in SUBTRACT_RULES:
                checked = SUBTRACT_RULES[mid].sub(" ", checked)
            negation = checked
            if mid == "death_prevention":
                negation = re.sub(r"cannot die|不会死亡|无法死亡", "", negation, flags=re.I)
            elif mid == "pierce_evasion":
                negation = re.sub(r"cannot miss", "", negation, flags=re.I)
            if NEGATIVE.search(negation) or not pattern.search(checked):
                continue
            if mid in CONTROL and STATE.search(checked):
                continue
            if mid in INTERACTION_TERMS and INTERACTION.search(checked):
                continue
            if mid == "channeled" and CHANNEL_MENTION.search(checked):
                continue
            if mid == "evasion" and re.search(r"pierc|穿透|无视", checked, re.I):
                continue
            if mid == "debuff_immunity" and re.search(r"pierc|穿透", checked, re.I):
                continue
            if mid == "applies_break" and re.search(r"破坏会|break disables", checked, re.I):
                continue
            yield mid, quote
