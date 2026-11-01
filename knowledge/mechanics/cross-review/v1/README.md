# Claude复核包

包ID：`26dff7e706583c96ff4aced460fad135c32620c840be5f4745c99851b56d18cf`

交接：[Claude](../../../../docs/handoff/mk-claude-cross-review.md)。

共1551组候选、2006条字段观测；Codex人工复核24组，其余未审。

先读 vocabulary.json、cases.jsonl 和 subjects.jsonl。独立填写 claude-template.jsonl 的副本，再参考 codex-prior.json 与 known-user-feedback.json 对照。双方相同标签仍需检查条件。

index.csv 可按英雄、技能或机制检索。coverage.json保留未命中/无说明清单，field-observations.jsonl完整列出结构化字段观测，不把未命中当作无机制。

| 机制 | 候选组数 |
|---|---|
| [眩晕](mechanisms/stun.md) | 100 |
| [妖术](mechanisms/hex.md) | 5 |
| [沉默](mechanisms/silence.md) | 30 |
| [禁用物品](mechanisms/mute.md) | 3 |
| [缴械](mechanisms/disarm.md) | 12 |
| [定身](mechanisms/root.md) | 23 |
| [强制行为](mechanisms/forced_action.md) | 20 |
| [睡眠](mechanisms/sleep.md) | 2 |
| [吹风/放逐](mechanisms/cyclone_banish.md) | 12 |
| [减速](mechanisms/slow.md) | 192 |
| [闪避](mechanisms/evasion.md) | 10 |
| [致盲](mechanisms/blind.md) | 4 |
| [减益免疫/技能免疫](mechanisms/debuff_immunity.md) | 35 |
| [穿透减益免疫](mechanisms/pierces_debuff_immunity.md) | 1 |
| [无敌/不可选取](mechanisms/invulnerable_untargetable.md) | 34 |
| [护盾/伤害吸收/减伤](mechanisms/damage_block.md) | 49 |
| [免死](mechanisms/death_prevention.md) | 4 |
| [状态抗性](mechanisms/status_resistance.md) | 7 |
| [减速抗性](mechanisms/slow_resistance.md) | 14 |
| [施加弱驱散](mechanisms/applies_basic_dispel.md) | 39 |
| [施加强驱散](mechanisms/applies_strong_dispel.md) | 13 |
| [效果可驱散性](mechanisms/effect_dispellability.md) | 0 |
| [施加破坏](mechanisms/applies_break.md) | 8 |
| [受破坏影响](mechanisms/break_sensitive.md) | 183 |
| [隐身](mechanisms/invisibility.md) | 53 |
| [真视](mechanisms/true_sight.md) | 18 |
| [治疗/回复](mechanisms/healing.md) | 118 |
| [吸血](mechanisms/lifesteal.md) | 27 |
| [治疗削减](mechanisms/heal_reduction.md) | 10 |
| [烧蓝/法力削减](mechanisms/mana_burn.md) | 16 |
| [自身回蓝/吸蓝](mechanisms/mana_gain.md) | 46 |
| [法力消耗](mechanisms/mana_cost.md) | 0 |
| [幻象](mechanisms/illusions.md) | 17 |
| [召唤物](mechanisms/summons.md) | 52 |
| [自身位移](mechanisms/self_mobility.md) | 71 |
| [位移他人](mechanisms/displace_other.md) | 62 |
| [魔法伤害](mechanisms/magical_damage.md) | 0 |
| [纯粹伤害](mechanisms/pure_damage.md) | 0 |
| [物理伤害](mechanisms/physical_damage.md) | 0 |
| [反伤](mechanisms/damage_return.md) | 15 |
| [重击](mechanisms/bash.md) | 9 |
| [克敌击先](mechanisms/pierce_evasion.md) | 13 |
| [暴击](mechanisms/critical.md) | 15 |
| [单体指向技能](mechanisms/unit_target_spell.md) | 161 |
| [持续施法](mechanisms/channeled.md) | 48 |
