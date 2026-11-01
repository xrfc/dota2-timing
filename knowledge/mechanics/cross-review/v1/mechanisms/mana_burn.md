# 烧蓝/法力削减：完整候选清单

减少目标的法力值

以下是证据候选，不含预填的Claude结论。完整上下文见 subjects.jsonl。

## 3. 莱恩·法力吸取

ID：`003553bae9be6f4d48d0`

条件：base

- `mf-7cfc172de9c9e78dd6eb`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/25/abilities/2/description_zh`

~~~~text
持续施法 - 引导魔法能量，持续吸取魔法并减缓敌人的移动速度。
~~~~

## 146. 祸乱之源·魔爪

ID：`1d29eb4d1a0c64ca5fdd`

条件：base

- `mf-836b4699a6e6121cf7cf`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/2/abilities/3/description_zh`

~~~~text
持续施法 - 抓住一个敌方单位，使其失去行动能力并持续受到大量伤害，同时每%fiend_grip_tick_interval%秒按目标最大魔法值一定比例吸取魔法。
~~~~

## 373. 散魂剑

ID：`41d2d65fac23fce665b9`

条件：item；装备模式=passive

- `mf-265fd2db45d269280e8b`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/disperser/abilities/1/description`

~~~~text
Each attack burns 40 mana from the target, and deals 1 physical damage per burned mana.
~~~~

- `mf-572b54627fd4d63a3851`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/disperser/abilities/1/description`

~~~~text
Illusions do not burn mana.
~~~~

## 488. 敌法师·法力损毁

ID：`58afc8e51eb59d393ae3`

条件：base

- `mf-6c96650bb3f94a9a77d9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/0/abilities/0/description_zh`

~~~~text
每次攻击损毁目标魔法值，并造成相当于损毁魔法值一定百分比的伤害。
~~~~

- `mf-aa8d7d5181d53cb851e9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/0/abilities/0/description_en`

~~~~text
Burns an opponent's mana on each attack and deals damage equal to a percentage of the mana burnt.
~~~~

- `mf-cd229ec1a9e0d8a8d838`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/0/abilities/0/notes_zh/0`

~~~~text
幻象继承法力损毁的燃烧魔法为%illusion_percentage%%%。
~~~~

## 647. 司夜刺客·法力燃烧

ID：`6ff66cde6d8643ad15f6`

条件：base

- `mf-c7e1623fa3c231dee03a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/86/abilities/4/description_en`

~~~~text
Nyx Assassin's damage on enemies also burns mana as a percentage of the damage dealt.
~~~~

- `mf-fb5e90a6355a9b5024e4`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/86/abilities/4/description_zh`

~~~~text
司夜刺客对敌人造成伤害还会燃烧造成伤害一定百分比的魔法。
~~~~

## 793. 敌法师·法力损毁

ID：`8a9b3231570765ef9d60`

条件：scepter_upgrade；需要A杖

- `mf-9a77d6cbcfdc510d9bc2`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/0/abilities/0/upgrade_text/scepter_loc/zh`

~~~~text
提升每次攻击燃烧的最大魔法值。
~~~~

## 883. 祈求者·电磁脉冲

ID：`971771ea5ea6063d5b46`

条件：base

- `mf-2269d8a5060671b2a174`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/72/abilities/7/description_zh`

~~~~text
对敌方英雄造成损毁魔法值一定百分比的伤害。
~~~~

- `mf-55a87ed172659106e6f7`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/72/abilities/7/description_zh`

~~~~text
祈求者将获得%self_mana_restore_pct%%%损毁的魔法。
~~~~

- `mf-70b26a7246afccdad578`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/72/abilities/7/description_en`

~~~~text
The detonation covers an area, draining mana based on the level of Wex.
~~~~

- `mf-98f30c8f4986270e7275`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/72/abilities/7/description_en`

~~~~text
If EMP drains mana from an enemy hero, Invoker gains %self_mana_restore_pct%%% of the mana drained.
~~~~

- `mf-f054ca985d116418ad0b`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/72/abilities/7/description_zh`

~~~~text
爆炸将覆盖一定区域，并根据雷元素的等级损毁敌方的魔法值。
~~~~

## 926. 司夜刺客·神智爆裂

ID：`9d989fbf45a3c4ed4108`

条件：base

- `mf-2a47f4bf6fb4de15a388`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/86/abilities/1/description_zh`

~~~~text
造成等同于目标最大魔法值一定百分比的伤害，并燃烧部分魔法。
~~~~

## 948. 净魂之刃

ID：`a086c88da96613dced3d`

条件：item；装备模式=passive

- `mf-83a53a23f3ee1c39cc80`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/diffusal_blade/abilities/1/description`

~~~~text
Illusions do not burn mana.
~~~~

- `mf-acfc2c01c17d84daffee`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/diffusal_blade/abilities/1/description`

~~~~text
Each attack burns 40 mana from the target, and deals 1 physical damage per burned mana.
~~~~

## 1042. 拉席克·脉冲新星

ID：`aedbf4c26fc8f6b33b22`

条件：base

- `mf-223a5bf0f0ed35d40564`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/50/abilities/5/description_en`

~~~~text
Drains Leshrac's mana with each pulse.
~~~~

## 1148. 死灵书

ID：`be8f09a21737b12bf187`

条件：item；装备模式=active

- `mf-9b39fec0e28aee5bc45f`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/necronomicon_3/abilities/0/description`

~~~~text
Warrior: Burns mana every hit, and deals magical damage to whoever kills it.
~~~~

## 1280. 寒冬飞龙·严寒烧灼

ID：`d44c396f24f5f7fcc2f8`

条件：scepter_upgrade；需要A杖

- `mf-18363ed54f7c553cbd08`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/109/abilities/0/upgrade_text/scepter_loc/en`

~~~~text
Causes Arctic Burn to be a toggle ability, draining mana every second when active.
~~~~

## 1382. 祈求者·电磁脉冲

ID：`e3ecc540da945d8df118`

条件：shard_upgrade；需要魔晶

- `mf-d0a6908aa6cd5ce20828`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/72/abilities/7/upgrade_text/shard_loc/zh`

~~~~text
提升电磁脉冲燃烧魔法的伤害系数，并且将敌方单位以每秒%drag_speed%距离的速度向电磁脉冲的中心牵引。
~~~~

## 1412. 巫妖·阴邪凝视

ID：`e8673876ed3b951e6cbe`

条件：base

- `mf-c13e4746153c773291ad`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/24/abilities/2/description_zh`

~~~~text
持续施法 - 使一个敌方单位着魔，缓慢走到巫妖与其之间的一点，并吸取其当前魔法值的一定百分比。
~~~~

- `mf-e1b768dbf367e34c08c2`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/24/abilities/2/description_en`

~~~~text
CHANNELED - Hypnotizes an enemy unit, causing it to move towards a point between the two of you and drains a percentage of its current mana.
~~~~

## 1493. 死灵书

ID：`f5bf987dd610a9faf196`

条件：item；装备模式=active

- `mf-4395131fda31bc4efabc`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/necronomicon/abilities/0/description`

~~~~text
Warrior: Burns mana every hit, and deals magical damage to whoever kills it.
~~~~

## 1536. 死灵书

ID：`fd6aa3dda5a1ace21c87`

条件：item；装备模式=active

- `mf-13a9550b2c86fd5030fe`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/necronomicon_2/abilities/0/description`

~~~~text
Warrior: Burns mana every hit, and deals magical damage to whoever kills it.
~~~~

