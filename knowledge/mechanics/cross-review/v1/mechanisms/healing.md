# 治疗/回复：完整候选清单

恢复生命值（治疗、生命恢复）

以下是证据候选，不含预填的Claude结论。完整上下文见 subjects.jsonl。

## 23. 噬魂鬼·盛宴

ID：`02d8e202a2237dc6f898`

条件：base

- `mf-18b62b1abe21c71ed986`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/52/abilities/2/notes_en/1`

~~~~text
The heal is independent of the damage.
~~~~

- `mf-5e990903053a4f57e160`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/52/abilities/2/description_en`

~~~~text
Lifestealer's attacks deal damage and provide heal for a percentage of his target's max health.
~~~~

- `mf-af72f7772476c2c358ea`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/52/abilities/2/description_zh`

~~~~text
噬魂鬼每次攻击时还会根据目标最大生命值的一定百分比造成伤害，同时获得治疗。
~~~~

## 40. 玛尔斯·无畏

ID：`06da11625b7e279d0f8e`

条件：base

- `mf-223741ff44b6cc1f2831`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/116/abilities/3/description_zh`

~~~~text
%radius%范围内敌方英雄数量更多时，玛尔斯就会获得生命恢复，敌人数量越多，生命恢复也越高。
~~~~

## 46. 撒旦之邪力

ID：`07d2022b8b44bd830c92`

条件：item；装备模式=passive

- `mf-2070920866b621d63e4d`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/satanic/abilities/1/description`

~~~~text
Heals the attacker for a percentage of physical damage dealt.
~~~~

## 59. 疯狂面具

ID：`0a5127ce075162242110`

条件：item；装备模式=passive

- `mf-5298bcdb1e4a8167ef56`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/mask_of_madness/abilities/1/description`

~~~~text
Heals the attacker for a percentage of physical damage dealt.
~~~~

## 66. 伐木机·活性护甲

ID：`0c79f5452c90546153db`

条件：base

- `mf-08f821083e335b8b263d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/description_zh`

~~~~text
伐木机每受到一次物理攻击，他的生命恢复和护甲值都会提升。
~~~~

- `mf-bdef03747ee680d29ca3`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/description_en`

~~~~text
Each time Timbersaw is attacked, he gains increased health regen and armor.
~~~~

## 86. 电炎绝手·龙炎饼干

ID：`10e8c5a87c2632a2d62b`

条件：shard_upgrade；需要魔晶

- `mf-09b8434af0983cfaa915`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/118/abilities/1/upgrade_text/shard_loc/zh`

~~~~text
龙炎饼干变得更具威力，治疗目标，并且朝着陆地点发射一个%shard_damage_multiplier_tooltip%%%冲击伤害的蜥蜴绝吻。
~~~~

- `mf-43956e4ae49614f0b554`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/118/abilities/1/upgrade_text/shard_loc/en`

~~~~text
Firesnap cookies become even more potent, healing the target and launching a Mortimer Kiss that does %shard_damage_multiplier_tooltip%%% impact damage to the landing destination.
~~~~

## 88. 巫医·巫毒疗法

ID：`10fde8df5c8ef1c5fe84`

条件：base

- `mf-0efb7cc0fd0dce2fd31a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/29/abilities/1/notes_en/0`

~~~~text
Healing is done in %heal_interval% second intervals.
~~~~

- `mf-c2548240d39dcdce2754`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/29/abilities/1/notes_zh/0`

~~~~text
治疗间隔为%heal_interval%秒。
~~~~

- `mf-e130c07b255a859f21a9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/29/abilities/1/notes_en/1`

~~~~text
Can heal Spell Immune units.
~~~~

- `mf-e87cfa4e8ce6ccbdb2ab`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/29/abilities/1/description_zh`

~~~~text
巫医集中魔力治疗附近的友军单位，开启巫毒疗法后会持续消耗巫医的魔法。
~~~~

- `mf-fa4566b2538bd8a58f50`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/29/abilities/1/description_en`

~~~~text
Witch Doctor focuses his magic to heal nearby allied units, costing Witch Doctor mana every second Voodoo Restoration is active.
~~~~

## 113. 魅惑魔女·自然之助

ID：`168d34ec5020caa25ee8`

条件：base

- `mf-36fbf927ab6f92dfa464`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/56/abilities/2/description_zh`

~~~~text
召唤一群小精灵治疗魅惑魔女以及身边的友方单位。
~~~~

- `mf-56725afa06b7f290682e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/56/abilities/2/description_en`

~~~~text
A cloud of wisps heals Enchantress and any friendly units nearby.
~~~~

## 126. 哈斯卡·狂战士之血

ID：`19cc7b49e8854b5788af`

条件：shard_upgrade；需要魔晶

- `mf-84bdfe9a8b80a48c6faf`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/57/abilities/2/upgrade_text/shard_loc/en`

~~~~text
Dispels Huskar, then after a delay, heals for the amount of health consumed plus an additional bonus per debuff dispelled.
~~~~

## 138. 圣堂刺客·心怀安宁

ID：`1c1aca2831bfa6788e8e`

条件：base

- `mf-8d976199b8439ea308ac`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/5/description_zh`

~~~~text
原地不动且未受到伤害超过%time_until_meditation%秒后，圣堂刺客开始冥想，获得生命恢复和魔法恢复加成，冥想%time_until_max_bonus%秒后达到最大加成。
~~~~

## 158. 瘟疫法师·死亡脉冲

ID：`1f7fff861457a5a8127a`

条件：base

- `mf-5684a0870ec42451240c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/34/abilities/0/description_zh`

~~~~text
瘟疫法师向他的周围释放死亡波纹，伤害敌方单位并治疗友军单位。
~~~~

- `mf-ec06e21e8bcf009f70e0`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/34/abilities/0/description_en`

~~~~text
Necrophos releases a wave of death around him, dealing damage to enemy units and healing allied units.
~~~~

## 170. 炼金术士·化学狂暴

ID：`20edb99c69c051d7946b`

条件：base

- `mf-1300fdad3499f30513e9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/71/abilities/5/description_en`

~~~~text
Alchemist causes his Ogre to enter a chemically induced rage, reducing base attack cooldown and increasing movement speed and health regeneration.
~~~~

- `mf-bc8f0eac4066b31d233e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/71/abilities/5/description_zh`

~~~~text
炼金术士诱发他的食人魔同伴进入化学狂暴，降低攻击间隔，提高移动速度和生命恢复。
~~~~

## 172. 哈斯卡·狂战士之血

ID：`2129d188654c4973c554`

条件：base

- `mf-0fb85f101d7d4a270703`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/57/abilities/2/description_zh`

~~~~text
生命恢复为力量的一定百分比。
~~~~

- `mf-7c70343be77b20643bd7`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/57/abilities/2/description_zh`

~~~~text
哈斯卡的伤痛赐予他力量，根据他损失的生命值将获得攻击速度、魔法抗性和生命恢复加成。
~~~~

- `mf-a517629b9e9dacd7958a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/57/abilities/2/description_en`

~~~~text
Health regen is a percentage of your strength.
~~~~

- `mf-ee43784192503dd9920b`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/57/abilities/2/description_en`

~~~~text
Huskar's injuries feed his power, giving increased attack speed, magic resistance and health regen based on missing health.
~~~~

## 192. 修补匠·机械行军

ID：`24d00d2e3d6a77e54fb9`

条件：scepter_upgrade；需要A杖

- `mf-a557a4b5d76e8679929e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/32/abilities/1/upgrade_text/scepter_loc/en`

~~~~text
March of the Machines applies a non-stacking heal over time when passing through allied heroes.
~~~~

- `mf-fef1767ceb497403e63a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/32/abilities/1/upgrade_text/scepter_loc/zh`

~~~~text
机械行军在穿过友方英雄时会施加不可叠加的持续治疗效果。
~~~~

## 254. 破晓辰星·天光现世

ID：`2f52036e3285bae6ee31`

条件：base

- `mf-51b37556fa139bdbea5c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/4/description_en`

~~~~text
Each pulse damages enemies and heals allies.
~~~~

- `mf-a6b9a40925a052d4d826`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/4/description_zh`

~~~~text
每次脉冲都会对敌人造成伤害，并治疗友军。
~~~~

## 264. 米波·洗劫

ID：`309bd56fa1ca2113a91b`

条件：base

- `mf-57f59b985e4cecaa7ac1`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/80/abilities/2/description_zh`

~~~~text
每次攻击都会窃取敌人的生命值，并治疗所有其他米波相同数值生命。
~~~~

- `mf-982eb772d7cca68383ec`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/80/abilities/2/description_en`

~~~~text
Steals health from the enemy with each strike and heals all other Meepos for that amount.
~~~~

- `mf-d224400380d6b96c5dcc`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/80/abilities/2/notes_zh/0`

~~~~text
治疗数值会被生命回复增强效果提升。
~~~~

## 286. 瘟疫法师·竭心光环

ID：`33c0cdd50d3450c629c8`

条件：scepter_upgrade；需要A杖

- `mf-a4fb6598f1ac9e9359e8`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/34/abilities/2/upgrade_text/scepter_loc/zh`

~~~~text
竭心光环的生命流失伤害提升，数值为瘟疫法师当前生命恢复的%heal_regen_to_damage%%%。
~~~~

- `mf-eb64dec5aa41009ea5ed`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/34/abilities/2/upgrade_text/scepter_loc/en`

~~~~text
Heartstopper Aura's Health Decay is increased by %heal_regen_to_damage%%% of Necrophos's current health regeneration.
~~~~

## 289. 陈·上帝之手

ID：`3487aac99041f6125d2e`

条件：scepter_upgrade；需要A杖

- `mf-03eabbbe36da9b41e2b8`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/upgrade_text/scepter_loc/zh`

~~~~text
初始治疗会在持续施法起始时发生，持续施法期间其他附近友方单位变为减益免疫状态，拥有%debuff_immune_resist%%%魔法抗性，而且持续治疗的威力提升%nearby_hot_boost%%%。
~~~~

- `mf-197402af262a55e3966d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/upgrade_text/scepter_loc/en`

~~~~text
The initial heal happens at the start of the channel, and while channeling other nearby allied units become debuff immune with %debuff_immune_resist%%% magic resistance and the power of the heal over time is increased by %nearby_hot_boost%%%.
~~~~

## 313. 狼人·野性驱使

ID：`3896eb6a185ea5d94dc2`

条件：base

- `mf-149d913408808279d876`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/75/abilities/2/description_zh`

~~~~text
提升狼人和所有他控制的单位的生命恢复和攻击力。
~~~~

## 315. 帕格纳·生命汲取

ID：`390ace6a8585d2e16f1d`

条件：base

- `mf-d2920e344afe4c9b04bc`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/43/abilities/4/description_en`

~~~~text
CHANNELED - When cast on an enemy, Pugna drains health from the target enemy unit to heal himself and granting vision over the target.
~~~~

## 337. 黑暗贤者·才思敏捷

ID：`3ce6f9c00c953fd713ff`

条件：base

- `mf-59b8ac1aeb88863449f9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/53/abilities/4/description_zh`

~~~~text
黑暗贤者升级时会恢复最大生命值和魔法值的一定百分比。
~~~~

## 339. 戴泽·薄葬

ID：`3d1c5f16614b7cb8b255`

条件：base

- `mf-4324f8c30cf52e41a5a9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/1/description_en`

~~~~text
Healing on that ally is also amplified for the duration based on the hero's HP.
~~~~

- `mf-654f683621c44191d4e6`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/1/description_zh`

~~~~text
对该友军的治疗效果在持续时间内也会根据其生命值得到增强。
~~~~

## 344. 吸血面具

ID：`3df37d289718ca76d249`

条件：item；装备模式=passive

- `mf-3cafdc66014c5599f008`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/lifesteal/abilities/0/description`

~~~~text
Heals the attacker for a percentage of physical damage dealt.
~~~~

## 364. 统御头盔

ID：`41067bd31b1da3d75367`

条件：item；装备模式=active

- `mf-71ad9e571afc7e2dd717`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/helm_of_the_overlord/abilities/0/description`

~~~~text
Also provides the unit with +70 base attack damage, +12 health regen, +4 mana regen, +7 armor, and levels up some abilities of the target by 1 level.
~~~~

## 402. 龙骑士·龙族血统

ID：`46ee0c2da109795a55b4`

条件：base

- `mf-31cd1305b1401a940e72`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/47/abilities/4/description_en`

~~~~text
The life blood of the Dragon improves Dragon Knight's health regeneration and armor.
~~~~

- `mf-5e2d43ef4df023a9b442`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/47/abilities/4/description_zh`

~~~~text
在古龙形态下生命恢复和护甲均提升%regen_and_armor_multiplier_during_dragon_form%%%。
~~~~

- `mf-b135ea27731744dc6ad9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/47/abilities/4/description_zh`

~~~~text
神龙的生命之血提升了龙骑士的生命恢复和护甲。
~~~~

## 425. 树之祭祀

ID：`4b63ef28d1bd55ce3b98`

条件：item；装备模式=use

- `mf-c5624357454dac46eb6f`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/tango/abilities/0/description`

~~~~text
Consuming an Ironwood Tree doubles the heal duration.
~~~~

- `mf-e7451960abca50389f0b`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/tango/abilities/0/description`

~~~~text
Consumes a target tree to gain 7 health regeneration for 16 seconds.
~~~~

## 430. 米波·地卜术

ID：`4ca362a8405b4c4e9335`

条件：base

- `mf-f97391b9019cc05aaae1`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/80/abilities/6/description_zh`

~~~~text
如果%tree_radius%范围内有树木，他会获得%tree_regen%点/秒生命恢复。
~~~~

## 434. 破晓辰星·熠熠生辉

ID：`4dd00b1efdc13bf7a6e7`

条件：base

- `mf-0c4033e95487e1e1a608`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/2/description_en`

~~~~text
Creeps and neutral enemies provide less healing.
~~~~

- `mf-3877e0301038423fa836`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/2/description_zh`

~~~~text
破晓辰星在数次攻击后提升了力量，她的下一次攻击会造成致命一击，并治疗她附近%heal_radius%范围内所有友方英雄，治疗量为攻击伤害的一定百分比。
~~~~

- `mf-6cc24a278c46af71c545`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/2/notes_zh/0`

~~~~text
熠熠生辉的治疗效果可以通过生命回复增强效果获得提升。
~~~~

- `mf-703d6fdd19781571c84c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/2/description_en`

~~~~text
After a number of attacks, Dawnbreaker powers up, charging her next attack with a critical hit that heals all allied heroes within %heal_radius% units around her for a portion of attack damage dealt.
~~~~

- `mf-804f74631f00cef74bde`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/2/description_zh`

~~~~text
对友军的治疗量为%allied_healing_pct%%%。
~~~~

- `mf-9e009e631db25c41f487`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/2/notes_en/0`

~~~~text
Luminosity Heal is increased by sources of Health Restoration Amplification.
~~~~

- `mf-b66d8863b4eb783dce37`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/2/description_zh`

~~~~text
攻击小兵和野怪产生的治疗量有所减少。
~~~~

## 435. 树之祭祀（共享）

ID：`4dd7c32bb2647226e4a3`

条件：item；装备模式=use

- `mf-3e0ccb4ae253ebb44031`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/tango_single/abilities/0/description`

~~~~text
5 health regeneration for 16 seconds.
~~~~

- `mf-f7d6c7182748e7efaad7`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/tango_single/abilities/0/description`

~~~~text
Consuming an Ironwood Tree doubles the heal duration.
~~~~

## 443. 魔棒

ID：`5005580668d9564e4782`

条件：item；装备模式=active

- `mf-07e82a94f9df2bfb9ab2`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/magic_stick/abilities/0/description`

~~~~text
Instantly restores 15 health and mana per charge stored.
~~~~

## 445. 兽王·斯洛姆战鼓

ID：`509cf3880151f8127b43`

条件：base；需要A杖

- `mf-69b3b281104a94e893f7`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/36/abilities/4/description_en`

~~~~text
Attacks from Beastmaster or a nearby unit he controls will cause him bang his drum, dealing damage to nearby units and healing Beastmaster and units under his control for a portion of the damage dealt.
~~~~

- `mf-8915ddef8fdc256c1167`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/36/abilities/4/description_zh`

~~~~text
兽王或周围他控制的单位攻击敌人都会使他敲下战鼓，对附近单位造成伤害，并且治疗自身和他控制的单位，数值为造成伤害的一定百分比。
~~~~

## 456. 狼人·饿狼撕咬

ID：`522b75b460a924a0a717`

条件：base；需要A杖

- `mf-3c0161585c16a3f3a8c3`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/75/abilities/3/description_en`

~~~~text
Lycan and the bitten target gain %lifesteal_percent%%% Lifesteal and share the healing effect of Lifesteal with each other as long as they are within %lifesteal_range% range of each other.
~~~~

## 463. 凤凰·烈日炙烤

ID：`534860cf3f3f7cf4e803`

条件：base

- `mf-559a4bbb8f7f4935a70a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/106/abilities/2/description_en`

~~~~text
The beam damages enemies and heals allies for a base amount plus a percentage of their max health.
~~~~

- `mf-c1fe2f07a5c9b58e15e4`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/106/abilities/2/description_zh`

~~~~text
光线对敌人造成伤害，并且能治疗友军，伤害和治疗的数值均为基础数值加上目标最大生命值的一定百分比。
~~~~

## 476. 梅肯斯姆

ID：`5604e10b42e1a570aae3`

条件：item；装备模式=passive

- `mf-79ca2113cee392926436`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/mekansm/abilities/1/description`

~~~~text
5 health regeneration to allied units in a 1200 radius.
~~~~

## 483. 陈·上帝之手

ID：`572d3f6c4a7926e111f3`

条件：base

- `mf-0f68884282b607a17b06`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/description_en`

~~~~text
Heals all allied heroes on the map as well as all units under Chen's control.
~~~~

- `mf-62d3683e6c74df1ed21f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/description_zh`

~~~~text
一开始先施加高额治疗，在之后%hot_duration%秒内持续进行小额治疗。
~~~~

- `mf-67dcfe9617c22778fe81`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/notes_en/0`

~~~~text
Can heal invulnerable and hidden/banished allies.
~~~~

- `mf-769cf3dee22de2c572a3`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/description_zh`

~~~~text
治疗地图上的所有友军英雄以及陈控制的所有单位。
~~~~

- `mf-c6c22a8101a15e8bb590`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/description_en`

~~~~text
A large heal is applied at first and a slow heal over time is applied for %hot_duration% seconds afterwards.
~~~~

- `mf-ee2a887e894704a55daf`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/4/notes_zh/0`

~~~~text
可以治疗无敌和被隐藏/放逐友军。
~~~~

## 516. 巫妖·寒冰尖柱

ID：`5bd57d05a91336a3a658`

条件：base；需要魔晶

- `mf-0ecac6bcfd0d8132e689`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/24/abilities/3/description_zh`

~~~~text
冰霜魔盾每次造成伤害时会治疗尖柱，使其回复1次英雄攻击次数。
~~~~

- `mf-d031690040c552f507e1`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/24/abilities/3/description_en`

~~~~text
Each Frost Shield tick will heal the spire by 1 hero attack.
~~~~

## 523. 破晓辰星·辰星破晓

ID：`5d660fa78540060cbf5f`

条件：scepter_upgrade；需要A杖

- `mf-42cbfdac822822332cce`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/3/upgrade_text/scepter_loc/zh`

~~~~text
辰星破晓提供治疗增强，数值等于当前攻击力提升。
~~~~

- `mf-5f542e55a4f1c2aa1533`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/120/abilities/3/upgrade_text/scepter_loc/en`

~~~~text
Break of Dawn provides healing amplification equal to the current damage increase.
~~~~

## 535. 神谕者·虚妄之诺

ID：`5ef1d0e1f81d8094c6fd`

条件：base

- `mf-4a7429358f82cb947f01`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/4/notes_zh/0`

~~~~text
伤害和治疗效果虽然被延缓结算，但是结算时依然会考虑护甲和魔法抗性的减免。
~~~~

- `mf-5f4d88ed3162976bb02b`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/4/notes_en/0`

~~~~text
Delayed damage and healing will take armor and magic resistance reductions into account when received.
~~~~

- `mf-7511ce4c3b506b48a98e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/4/description_en`

~~~~text
Temporarily alters an ally's destiny, delaying any healing or damage taken until False Promise ends.
~~~~

- `mf-7884d0c0f5cf14b7db6d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/4/notes_zh/1`

~~~~text
经过延缓的伤害和治疗效果在目标失去本技能效果后立刻结算。
~~~~

- `mf-a66dc4e0649abfcd968e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/4/description_en`

~~~~text
Any healing that is delayed by False Promise is amplified.
~~~~

- `mf-ab2269a1dae0a75a01ac`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/4/description_zh`

~~~~text
暂时篡改队友的命运，技能期间受到的任何治疗和伤害效果将在虚妄之诺结束后结算，其中治疗效果结算时效果更强。
~~~~

- `mf-e337475eea5d4cdcd8e1`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/4/notes_en/1`

~~~~text
The delayed damage and healing takes effect as soon as the target becomes vulnerable.
~~~~

## 543. 炼金术士·狂暴药剂

ID：`6087ba2c896efaf75a14`

条件：base；需要魔晶

- `mf-f023658438780c6804d3`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/71/abilities/3/description_zh`

~~~~text
炼金术士向友军目标扔出一瓶药剂，施加弱驱散效果，并提供攻击速度、移动速度和生命恢复。
~~~~

## 564. 卫士胫甲

ID：`62a813f6e3fa1f91694a`

条件：item；装备模式=active

- `mf-b3407199397f4d40463d`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/guardian_greaves/abilities/0/description`

~~~~text
Restores 325 health and 200 mana to nearby allies, and removes most negative effects from the caster.
~~~~

## 572. 军团指挥官·强攻

ID：`63992e5449b19eb0c26f`

条件：base

- `mf-90ada465a0ca19a16401`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/102/abilities/1/description_en`

~~~~text
Removes debuffs and disables from the target friendly unit, and grants bonus movement speed and health regen for a short time.
~~~~

- `mf-c6d96930c51f1aad1f12`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/102/abilities/1/description_zh`

~~~~text
移除友方目标单位的负面效果和控制技能，并提升其移动速度和生命恢复，持续一定时间。
~~~~

## 582. 卫士胫甲

ID：`64dfa12adf518896c095`

条件：item；装备模式=passive

- `mf-4f4df7f8aac422b031e5`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/guardian_greaves/abilities/1/description`

~~~~text
If the wearer's health falls below 25%, their health regeneration is increased to 14.
~~~~

- `mf-de581af4d4090f437e56`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/guardian_greaves/abilities/1/description`

~~~~text
5 health regeneration and 1.
~~~~

## 608. 暗夜魔王·暗夜猎影

ID：`6a48ad79b0e9539d3fc5`

条件：shard_upgrade；需要魔晶

- `mf-b96f6b420f6965775b69`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/58/abilities/3/upgrade_text/shard_loc/zh`

~~~~text
可以主动对一个普通单位施放暗夜猎影，将其秒杀并恢复暗夜魔王最大生命和魔法的一定百分比。
~~~~

## 609. 巫毒面具

ID：`6a70f1e22098a4e74127`

条件：item；装备模式=passive

- `mf-b0240a6b6c702024ee5e`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/voodoo_mask/abilities/0/description`

~~~~text
Heals the wearer for a percentage of spell damage dealt to enemies.
~~~~

## 619. 帕格纳·衰老

ID：`6bdc3362ebedd3032325`

条件：base

- `mf-428ac09ec217e11f9814`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/43/abilities/1/description_zh`

~~~~text
受作用的友军提升了治疗效果，而受作用的敌军会被减速，并且承受额外魔法伤害。
~~~~

- `mf-950783c6b097cfeb024d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/43/abilities/1/description_en`

~~~~text
Healing on affected allies is increased, while afflicted enemies take extra magic damage instead.
~~~~

## 621. 韧鼓

ID：`6bfdd52c47781dd4f0d9`

条件：item；装备模式=passive

- `mf-297e2720d6a38e244cac`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/ancient_janggo/abilities/1/description`

~~~~text
5 health regeneration to allies.
~~~~

## 624. 陈·狂热者

ID：`6c70df57fa809cc68e1b`

条件：base

- `mf-652a8da78f9c9b5404b3`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/3/description_zh`

~~~~text
陈复活时都会带着一个狂热者加入战斗，这是近战小兵战士，可以牺牲自己治疗友军，或者对敌人造成伤害。
~~~~

- `mf-a8d40cd8e0d3fd1a5e6a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/3/description_en`

~~~~text
Whenever Chen respawns, he is joined by a Zealot, a melee warrior creep with the ability to sacrifice itself to heal or deal damage to an enemy.
~~~~

## 634. 梅肯斯姆

ID：`6d9e2d1f32351c5c3a2d`

条件：item；装备模式=active

- `mf-ff1e1bd7e784ed141509`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/mekansm/abilities/0/description`

~~~~text
Restores 250 health to allied units in a 1200 radius.
~~~~

## 651. 全能骑士·洗礼

ID：`70b1f3ba252f6653b610`

条件：base

- `mf-386b858657f3fbf25620`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/55/abilities/0/description_zh`

~~~~text
立即治疗一个友方单位，并对周围的敌军造成伤害。
~~~~

- `mf-dfcdc03ae98583accf08`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/55/abilities/0/description_en`

~~~~text
Instantly heals a friendly unit and damages all nearby enemy units.
~~~~

## 670. 育母蜘蛛·蜘蛛奶

ID：`74ef47b600ee8227e970`

条件：base

- `mf-1c79521d505bf5f463fb`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/59/abilities/4/description_zh`

~~~~text
非英雄单位提供的治疗量减少%kill_creeps_penalty%%%。
~~~~

- `mf-5d992ceeccdac097ce2d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/59/abilities/4/description_en`

~~~~text
Whenever Broodmother kills a unit, she and all units under her control in a %kill_heal_aoe% radius receive a buff for %kill_heal_duration%s that heals them for a percentage of the victim's health every %tick_rate% seconds.
~~~~

- `mf-b06474557b45eb860947`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/59/abilities/4/description_en`

~~~~text
Healing from creeps is reduced by %kill_creeps_penalty%%%.
~~~~

- `mf-c49d0f7bd303d301d889`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/59/abilities/4/description_zh`

~~~~text
育母蜘蛛击杀一个单位后，她和%kill_heal_aoe%范围内她控制的所有单位都会获得持续%kill_heal_duration%秒的状态效果，每%tick_rate%秒治疗一定生命，治疗量为遇害者生命值的一定百分比。
~~~~

## 677. 陈·神力恩泽

ID：`762d9498167f9b140529`

条件：base

- `mf-3dcd851c6dd136e8f3f5`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/2/description_zh`

~~~~text
被动提供光环，提供生命恢复加成。
~~~~

- `mf-519e922f775ce7f98ccc`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/2/description_en`

~~~~text
Passively provides an aura that grants increased health regeneration.
~~~~

- `mf-b555b08d1bded3d38e95`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/2/description_en`

~~~~text
Can be cast on allies to provide them with bonus armor and increasing the healing and health regeneration they receive.
~~~~

- `mf-cfaa09152b2c9368a3c9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/64/abilities/2/description_zh`

~~~~text
可以主动对友军施放，提供护甲加成，以及治疗和生命恢复增强。
~~~~

## 679. 暗夜魔王·午夜盛宴

ID：`76a58b1b7460224e4e9c`

条件：base

- `mf-217ce602cc2d25ad5f14`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/58/abilities/2/description_en`

~~~~text
Night Stalker heals himself when attacking enemy units.
~~~~

- `mf-e73b815a1bfbed4dc0ac`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/58/abilities/2/description_zh`

~~~~text
暗夜魔王攻击敌方单位时治疗自身。
~~~~

## 684. 戴泽·暗影波

ID：`771f615b7fc5c8481b50`

条件：scepter_upgrade；需要A杖

- `mf-3e3577e29493ce37fb05`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/2/upgrade_text/scepter_loc/en`

~~~~text
When bouncing to an enemy, they will take damage and heal nearby allies equal to %scepter_heal_pct%%% of the normal healing and damage values.
~~~~

- `mf-b5dbe5e1a568ac5da762`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/2/upgrade_text/scepter_loc/zh`

~~~~text
弹跳至敌人时，他们会受到伤害，并且治疗附近友军，数值为%scepter_heal_pct%%%平常治疗和伤害量。
~~~~

## 701. 戴泽·编织

ID：`799443581e85b1792948`

条件：shard_upgrade；需要魔晶

- `mf-509be97a4e2ff4cb3c1f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/3/upgrade_text/shard_loc/zh`

~~~~text
对友军施加编织时，每层编织效果治疗%ally_heal%点。
~~~~

- `mf-62445aa0e4cb370edf92`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/3/upgrade_text/shard_loc/en`

~~~~text
Applying Weave to an ally heals them for %ally_heal% per stack of Weave.
~~~~

## 723. 朗戈·动人之舐

ID：`7dc61ffd245ed6757635`

条件：base

- `mf-dccd525fc48210cf68f5`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/126/abilities/0/description_en`

~~~~text
Killing or dispelling an effect from a target grants Largo temporary health regeneration.
~~~~

- `mf-f9515c2ec22e23881848`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/126/abilities/0/description_zh`

~~~~text
击杀目标或驱散目标的效果后都会使朗戈暂时获得生命恢复。
~~~~

## 733. 亚巴顿·回光返照

ID：`7f888fc2eb8cd385bef3`

条件：base

- `mf-3f6042d04e81e4e567a4`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/4/description_zh`

~~~~text
启动后驱散自身，所有受到的伤害转而产生治疗效果。
~~~~

- `mf-49722e629aa49f356aff`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/4/description_en`

~~~~text
When activated, dispels you and all damage dealt to you will heal instead of harm.
~~~~

## 745. 秘奥闪光

ID：`81ae6f5d51f1d69ed25f`

条件：item；装备模式=active

- `mf-69cf2196c18555c11be7`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/arcane_blink/abilities/0/description`

~~~~text
After teleportation, you restore 250 health and 100 mana.
~~~~

## 747. 宽容之靴

ID：`82575df4377ae353ddd9`

条件：item；装备模式=passive

- `mf-5dbe030e26f3f6c9b423`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/boots_of_bearing/abilities/1/description`

~~~~text
5 health regeneration to allies.
~~~~

## 750. 艾欧·羁绊

ID：`82fe61f1d43ad6d3f68b`

条件：base

- `mf-00cd865890fad1d66a9e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/89/abilities/0/notes_en/1`

~~~~text
The tethered unit will heal faster and will heal even if Io is at full health.
~~~~

- `mf-7be9df574947676f5086`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/89/abilities/0/description_en`

~~~~text
When Io restores health or mana, the tethered unit gains a portion of that amount.
~~~~

## 755. 支配头盔

ID：`841d73dbbce0084f6b3a`

条件：item；装备模式=active

- `mf-98cac88d4e235a7d4989`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/helm_of_the_dominator/abilities/0/description`

~~~~text
Also provides the unit with +25 base attack damage, +12 health regen, +4 mana regen and +4 armor.
~~~~

## 761. 影之灵龛

ID：`84e972325f807614a471`

条件：item；装备模式=active

- `mf-42aa634ae2ab7330cda3`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/urn_of_shadows/abilities/0/description`

~~~~text
Provides 30 health regeneration when cast on allies, and deals 25 damage per second when cast on enemies.
~~~~

## 763. 治疗药膏

ID：`8551e1c08b5be2aca75f`

条件：item；装备模式=use

- `mf-7e71ba10814986960fb7`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/flask/abilities/0/description`

~~~~text
Grants 30 health regeneration to the target for 13 seconds.
~~~~

- `mf-abfa1d4f54ccdeabcc07`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/flask/abilities/0/description`

~~~~text
Heals for half the amount per second when cast on an ally.
~~~~

## 784. 独行德鲁伊·灵魂链接

ID：`88c4af135854022b3484`

条件：scepter_upgrade；需要A杖

- `mf-11a52edd4c9856479be2`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/78/abilities/1/upgrade_text/scepter_loc/en`

~~~~text
Damage done by the ally heals Lone Druid, as well as the other way around.
~~~~

- `mf-78bcd9b2104cfb4da984`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/78/abilities/1/upgrade_text/scepter_loc/zh`

~~~~text
友军造成的伤害会治疗独行德鲁伊，反之亦然。
~~~~

## 804. 树精卫士·寄生种子

ID：`8b97ffb99c9db33c1209`

条件：base

- `mf-b5fa8c998d0f3cdef795`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/81/abilities/1/description_zh`

~~~~text
该单位会受到额外魔法伤害，被缠绕和缴械一小段时间，并放出%healing_pulse_count%次治疗脉冲，最多对附近%max_heal_units%名友军根据当次攻击造成的伤害进行治疗。
~~~~

- `mf-ef8dc7813f7b00ba333e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/81/abilities/1/description_en`

~~~~text
That unit takes additional magic damage, is rooted and disarmed for a short duration, and emits %healing_pulse_count% healing pulses to up to %max_heal_units% nearby allies of Treant Protector based on the damage dealt by the attack.
~~~~

## 806. 克林克兹·死亡契约

ID：`8bb1ddd6ecbc2d06d72c`

条件：base

- `mf-7c1a4e68c3b1e25a92b0`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/54/abilities/2/description_zh`

~~~~text
克林克兹以敌方非英雄单位或友方骷髅弓手为吞噬的目标，治疗并获得最大生命值。
~~~~

- `mf-977d66cf8f1bf26947f0`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/54/abilities/2/description_en`

~~~~text
Clinkz consumes the target enemy creep or friendly Skeleton Archer, healing and gaining max health.
~~~~

## 815. 光之守卫·灵魂形态

ID：`8c9783d9ca7a0ad37a57`

条件：shard_upgrade；需要魔晶

- `mf-87695cf0295b50863cb9`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/88/abilities/5/upgrade_text/shard_loc/en`

~~~~text
Increases illuminate heal.
~~~~

- `mf-acb47b401b1ebd7b3a58`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/88/abilities/5/upgrade_text/shard_loc/zh`

~~~~text
提升冲击波的治疗效果。
~~~~

## 821. 朗戈·大屿灵药

ID：`8de52a1022429003bbd3`

条件：base

- `mf-0b9ff382a1ba5d6427d7`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/126/abilities/7/description_en`

~~~~text
Largo plays a song that heals nearby friendly heroes.
~~~~

- `mf-d05995081eda91a00ab2`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/126/abilities/7/description_zh`

~~~~text
朗戈弹奏的乐曲会治疗附近友方英雄。
~~~~

## 823. 奶酪

ID：`8e4ec203d47c4c381fb0`

条件：item；装备模式=use

- `mf-88ca48a75799e634875a`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/cheese/abilities/0/description`

~~~~text
Instantly restores 2500 health and 1500 mana.
~~~~

## 824. 光之守卫·灵魂形态

ID：`8e7e9d5afc2b0e772cf7`

条件：base

- `mf-7caf9f09fb1c01163f2e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/88/abilities/5/description_zh`

~~~~text
伊扎洛暂时使身体发光，获得施法距离加成，提升光明速度的移速加成，并且冲击波将由一个单独的灵魂施法，可以治疗友军。
~~~~

- `mf-ef20317f8f51663f9337`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/88/abilities/5/description_en`

~~~~text
Ezalor temporarily turns his body luminescent, gaining cast range, increasing the speed bonus from Bright Speed, and allows Illuminate to be channeled by a separate spirit and heal allies.
~~~~

## 844. 斯拉克·海浪短刀

ID：`9137472ff89394661d89`

条件：base

- `mf-14280a34908eaa55313f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/91/abilities/2/description_zh`

~~~~text
斯拉克用他的海浪短刀划开目标，窃取目标一部分的移动速度、生命恢复和生命回复。
~~~~

- `mf-cc9db354e2c28b959aca`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/91/abilities/2/description_en`

~~~~text
Slark slices the target with his salty shiv, stealing a portion of the target's movement speed, Health Regen and Health Restoration.
~~~~

## 860. 末日使者·焦土

ID：`941a2aa7b329800adf22`

条件：base

- `mf-379b6a76829adc161808`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/66/abilities/1/description_en`

~~~~text
Carpets the nearby earth in flames which damage enemies, while also granting Doom increased movement speed and health regeneration.
~~~~

- `mf-723324f9e0c609c44d44`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/66/abilities/1/description_zh`

~~~~text
用火焰覆盖周围的土地，对敌人造成伤害，同时末日使者的移动速度和生命恢复得到提升。
~~~~

## 866. 全能骑士·驱逐

ID：`949bfed2d0b954a9dba6`

条件：base

- `mf-c08d777137d915c2423a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/55/abilities/1/description_zh`

~~~~text
提供减益免疫状态和%magic_resist%%%魔法抗性，以及额外生命恢复。
~~~~

## 875. 不朽尸王·墓碑

ID：`95de13655b39ceaff5dd`

条件：base

- `mf-35f49f8f66a162299137`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/83/abilities/2/notes_zh/0`

~~~~text
墓碑免疫技能，但是可以被噬魂治疗。
~~~~

## 892. 祈求者·冰

ID：`9802f5a4f2be2453e6be`

条件：base

- `mf-706fcc90e6031d824267`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/72/abilities/0/description_zh`

~~~~text
每个活跃的冰元素会让祈求者获得生命恢复加成。
~~~~

## 901. 天涯墨客·墨涌

ID：`997fb8f90cf29995cdf6`

条件：shard_upgrade；需要魔晶

- `mf-52c9347827c09d40adf7`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/115/abilities/2/upgrade_text/shard_loc/en`

~~~~text
Causes Ink Swell to deal %shard_bonus_damage_pct%%% more damage and heal the target for %shard_heal_pct%%% of the damage Ink Swell deals.
~~~~

- `mf-b6882696a72b1a1aed93`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/115/abilities/2/upgrade_text/shard_loc/zh`

~~~~text
墨涌造成的伤害增加%shard_bonus_damage_pct%%%，并且治疗目标，治疗量为墨涌造成伤害的%shard_heal_pct%%%。
~~~~

## 904. 帕吉·肢解

ID：`9a32114bd655cb3921ea`

条件：base

- `mf-2afa221b6f55316476a4`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/13/abilities/4/description_en`

~~~~text
Damage is increased by Pudge's Strength and heals him for the total amount.
~~~~

## 912. 末日使者·末日

ID：`9b73ffd7bfa1787916ac`

条件：base

- `mf-2b5fe605b031a7b395db`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/66/abilities/3/description_en`

~~~~text
Inflicts a curse that dispels an enemy and prevents them from casting spells or healing in any way, while taking damage over time.
~~~~

## 913. 噬魂鬼·撕裂伤口

ID：`9b7ca0d9a87f4c7b0802`

条件：base

- `mf-8521217c124ac3fcb5c3`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/52/abilities/1/notes_zh/1`

~~~~text
治疗数值会被噬魂鬼的生命回复增强效果提升。
~~~~

## 918. 斯拉克·暗影之舞

ID：`9be4a5a3df96daf08bd8`

条件：base

- `mf-862a37e9c4eed3f5c502`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/91/abilities/5/description_zh`

~~~~text
当斯拉克不处于敌方视野内时，他会被动获得移动速度加成和生命恢复。
~~~~

- `mf-9d11fb1c8cf977acc583`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/91/abilities/5/description_zh`

~~~~text
如果受到来自中立单位的伤害，%neutral_disable%秒内会失去被动移速和生命恢复加成。
~~~~

- `mf-9d86d767bf7de76a4f04`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/91/abilities/5/description_en`

~~~~text
When not visible to the enemy team, Slark passively gains bonus movement speed and health regeneration.
~~~~

- `mf-f7ab997a45db11aac656`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/91/abilities/5/description_en`

~~~~text
If Slark is damaged by a neutral unit, the passive movement and health regeneration bonuses are lost for %neutral_disable% seconds.
~~~~

## 927. 恐鳌之心

ID：`9daacd4d97df7ca7c2c3`

条件：item；装备模式=passive

- `mf-38f4c8a1108ba6311cc3`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/heart/abilities/0/description`

~~~~text
Your health regeneration is increased by 1.
~~~~

## 966. 不朽尸王·噬魂

ID：`a398d8c969e4c08402c6`

条件：base

- `mf-0a1e9c170f969ac8dd86`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/83/abilities/1/description_zh`

~~~~text
不朽尸王从附近的所有单位身上扯出生命力，并使用它治疗队友或伤害敌人。
~~~~

- `mf-3193d097a31adb587374`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/83/abilities/1/description_en`

~~~~text
Soul Rip can also be used to heal Tombstone.
~~~~

- `mf-33b02b79ddc4bee303df`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/83/abilities/1/description_en`

~~~~text
Undying rips health away from all nearby units and uses it to heal an ally, or damage an enemy.
~~~~

- `mf-80066d85ca6a74847727`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/83/abilities/1/description_zh`

~~~~text
可以使用噬魂治疗墓碑。
~~~~

## 977. 远古冰魄·冰晶爆轰

ID：`a48dba2c6b9516657805`

条件：base

- `mf-066c51f81fb55276bb6c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/67/abilities/4/notes_en/4`

~~~~text
The HP Freeze prevents most kinds of healing, including the fountain, except Sunder, Time Lapse and Supernova.
~~~~

- `mf-4fa1d89aadaaedc23552`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/67/abilities/4/description_en`

~~~~text
Enemies caught in the explosion, or who touch the icy ball of hail as it travels, are Frostbitten, taking damage over time and prevented from regenerating or healing.
~~~~

## 1014. 魂之灵瓮

ID：`ab8cfdd06667726fbcdb`

条件：item；装备模式=active

- `mf-27070fedc04d30923cd3`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/spirit_vessel/abilities/0/description`

~~~~text
When used on allies, it provides 40 health regeneration per second.
~~~~

## 1015. 艾欧·过载

ID：`abaec203c99d69fe7a4c`

条件：base

- `mf-1be0b3ce311f8c09f10e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/89/abilities/2/description_zh`

~~~~text
艾欧获得攻击速度、技能增强和基于最大生命值的生命恢复。
~~~~

- `mf-8546bfd4b127a9d82e26`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/89/abilities/2/description_en`

~~~~text
Io gains attack speed, spell amplification, and health regeneration based on max health.
~~~~

## 1041. 艾欧·衡势

ID：`aec717141fc6af6bcc02`

条件：base

- `mf-b3d5cddeacaf00828fe5`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/89/abilities/6/description_zh`

~~~~text
同时，艾欧还获得生命回复和治疗增强，血量越低，数值越高。
~~~~

- `mf-eb2b92af03721500f442`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/89/abilities/6/description_en`

~~~~text
Io gains outgoing damage amplification the closer it is to full health, and Health Restoration and Healing Amplification the closer it is to zero health.
~~~~

## 1043. 树精卫士·活体护甲

ID：`aedf3247732e1e44a45b`

条件：base

- `mf-82e9e6f2b513cf8e66dc`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/81/abilities/2/description_zh`

~~~~text
将目标英雄或建筑笼罩在保护性外壳中，治疗目标并格挡来自玩家控制来源的伤害。
~~~~

- `mf-9fbac11cc4a1382c8edd`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/81/abilities/2/description_en`

~~~~text
Infuses the target hero or structure with a protective coating which heals the target and blocks damage from player-controlled sources.
~~~~

## 1076. 神谕者·涤罪之焰

ID：`b2d1f3c6091d4d8168ee`

条件：base

- `mf-3d6910c3916074f912df`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/2/description_en`

~~~~text
The amount of health regenerated over its duration exceeds the amount of initial damage.
~~~~

- `mf-44e43c2f80a5cdde496e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/2/description_zh`

~~~~text
将目标身上一切不洁之物净化，对其造成大量魔法伤害，并使其在接下来的一段时间内逐渐恢复生命值。
~~~~

- `mf-b838c7c25a9d10d9afc7`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/2/notes_en/0`

~~~~text
The healing from Purifying Flames can be stacked with itself.
~~~~

- `mf-e96c783a879c727beb21`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/2/description_zh`

~~~~text
恢复的生命值总量将超过受到的伤害。
~~~~

- `mf-f5d06985981f649e9a5d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/2/notes_zh/0`

~~~~text
涤罪之焰的治疗效果可以相互叠加。
~~~~

## 1086. 术士·暗言术

ID：`b46650dee93fe7e9918e`

条件：scepter_upgrade；需要A杖

- `mf-2d8638f30e68fb2142dd`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/35/abilities/1/upgrade_text/scepter_loc/zh`

~~~~text
额外单位的治疗和伤害量减少%secondary_reduction%%%。
~~~~

- `mf-85155be12d33d9824c90`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/35/abilities/1/upgrade_text/scepter_loc/en`

~~~~text
The healing and damage on the additional targets is reduced by %secondary_reduction%%%.
~~~~

## 1104. 恢复头巾

ID：`b8c8c99076b3d0c29f51`

条件：item；装备模式=passive

- `mf-f2359e828e6a411aa978`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/headdress/abilities/0/description`

~~~~text
Grants 2 health regeneration to allies.
~~~~

## 1128. 噬魂鬼·感染

ID：`bbb16bbd8ee85bd314c7`

条件：base

- `mf-bf9331d22423e02b1e02`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/52/abilities/4/description_en`

~~~~text
Lifestealer infests the body of a target unit, becoming undetectable, and healing for a portion of his max hitpoints every second while inside.
~~~~

## 1132. 主宰·治疗守卫

ID：`bcb155ce403841ce268d`

条件：shard_upgrade；需要魔晶

- `mf-750c188af8973c7d6c5a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/upgrade_text/shard_loc/en`

~~~~text
Increases ward healing and health.
~~~~

- `mf-a242b2d69847e1290b7f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/upgrade_text/shard_loc/zh`

~~~~text
提升守卫的治疗量和生命值。
~~~~

## 1152. 圣洁吊坠

ID：`bf23e33ed21d08fb396f`

条件：item；装备模式=active

- `mf-164f5a9998f51640abf5`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/holy_locket/abilities/0/description`

~~~~text
Target an allied unit to increase their incoming Heal Amplification by 15% for 4s and instantly restore 17 health and 15 mana per charge stored.
~~~~

## 1166. 主宰·治疗守卫

ID：`c20f8d937ae4e0dae860`

条件：base

- `mf-4aca70f7871c64e41d8e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/notes_zh/0`

~~~~text
可以控制治疗守卫。
~~~~

- `mf-50df0bf3889c119e66b8`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/description_en`

~~~~text
Summons a Healing Ward which heals all nearby allied units, based on their max health.
~~~~

- `mf-78bef67af13376c4e0dd`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/description_zh`

~~~~text
治疗守卫可以移动，移动速度为%healing_ward_movespeed_tooltip%。
~~~~

- `mf-799e78438b9142e2d149`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/notes_en/1`

~~~~text
Multiple Healing Wards do not stack.
~~~~

- `mf-94fe45d7c19bc221a5e0`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/description_en`

~~~~text
The Healing Ward moves at %healing_ward_movespeed_tooltip% movement speed after being summoned.
~~~~

- `mf-de0af82f2cbf1fea0598`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/description_zh`

~~~~text
召唤一个治疗守卫，按周围友军单位最大生命值的一定比例治疗他们。
~~~~

- `mf-e20ce36940b2c3f98986`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/7/abilities/1/notes_en/0`

~~~~text
The Healing Ward can be controlled.
~~~~

## 1210. 术士·暗言术

ID：`c833aebf0e3a3c79accf`

条件：base

- `mf-7ce6cde306ef32b2dccd`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/35/abilities/1/description_en`

~~~~text
Target Unit will also heal or be damaged depending on whether they are ally or enemy.
~~~~

- `mf-96573665675082726d48`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/35/abilities/1/description_zh`

~~~~text
目标单位也会被治疗或受到伤害，取决于他是友军还是敌人。
~~~~

- `mf-a8b35e774b8c976a2b34`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/35/abilities/1/description_en`

~~~~text
Warlock whispers an incantation, casting a spell on a unit that makes it deal damage to nearby enemy units and heal nearby ally units.
~~~~

- `mf-fba0af5f0bb0812d5b49`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/35/abilities/1/description_zh`

~~~~text
术士低声说出一个咒语，对一个单位施展法术，使周围的敌方单位受到伤害，周围的友方单位被治疗。
~~~~

## 1230. 仙灵之火

ID：`cba2eb6ac4678dd8b56e`

条件：item；装备模式=use

- `mf-0700e391ee800a854e7a`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/faerie_fire/abilities/0/description`

~~~~text
Instantly restores 85 health.
~~~~

## 1240. 精之灵器

ID：`cd915fd6db53b408a271`

条件：item；装备模式=active

- `mf-ed8e1c2b66d301d994ea`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/essence_distiller/abilities/0/description`

~~~~text
Provides 40 health regeneration when cast on allies.
~~~~

## 1269. 戴泽·暗影波

ID：`d27deb5cc39247959220`

条件：base

- `mf-1012c8559971c6d9263e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/2/description_en`

~~~~text
Sends out a bolt of power that arcs between allies, healing them while damaging any enemy units standing nearby.
~~~~

- `mf-205b060096b249685b16`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/2/description_zh`

~~~~text
放出一道能量弧，可以瞬间跳跃至目标附近的队友，治疗的同时还将对附近的敌方单位造成伤害。
~~~~

- `mf-6bdd8e6963e232b08d52`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/2/description_zh`

~~~~text
施放暗影波时戴泽必定会享受到治疗效果。
~~~~

- `mf-c5243936a90ed2e31032`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/2/notes_zh/0`

~~~~text
优先治疗友方英雄
~~~~

## 1279. 魔杖

ID：`d421d071bb7cd79bb58c`

条件：item；装备模式=active

- `mf-dac30d41e5e14d86215d`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/magic_wand/abilities/0/description`

~~~~text
Instantly restores 15 health and mana per charge stored.
~~~~

## 1284. 斯拉达·汪洋前哨

ID：`d4b958734995fb3b5be1`

条件：scepter_upgrade；需要A杖

- `mf-f01af2efb8165ce1cdee`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/27/abilities/3/upgrade_text/scepter_loc/zh`

~~~~text
在水洼、水迹或河道中获得额外生命恢复、护甲，还有状态抗性。
~~~~

## 1287. 虚无之灵·内在优势

ID：`d5236cfcc4951e23ed90`

条件：base

- `mf-c2de10648d03fc125634`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/117/abilities/3/description_zh`

~~~~text
虚无之灵从每点属性获得的攻击力提升%damage_stat_bonus_pct%%%，并且从力量中获得的生命恢复、敏捷中获得的攻击速度和智力中获得的魔法恢复提升%secondary_stat_bonus_pct%%%。
~~~~

## 1301. 死亡先知·驱使恶灵

ID：`d88096fd63d70fb63eb3`

条件：base

- `mf-95c1063e0063830eb903`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/41/abilities/4/description_zh`

~~~~text
持续时间结束后，死亡先知根据造成的伤害量，获得一定比例的治疗。
~~~~

## 1315. 帕克·顽皮克敌

ID：`da636ec2685f662623e3`

条件：base

- `mf-954742aed055dc508a22`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/12/abilities/3/description_en`

~~~~text
Whenever Puck disjoints an attack, it restores %mana_and_health_restore_pct%%% of its max health and mana.
~~~~

## 1318. 恐怖利刃·狂魔

ID：`da9c8172497100231a4b`

条件：base；需要魔晶

- `mf-1825efa3f46dcdc70f0e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/105/abilities/3/description_zh`

~~~~text
施放需消耗恐怖利刃当前生命值的一部分，为恐怖利刃和他附近的幻象提供生命恢复、移动和攻击速度加成。
~~~~

## 1331. 魔瓶

ID：`dcd38a673d30f957f0d4`

条件：item；装备模式=active

- `mf-9f22ac619a8347ab97c3`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/bottle/abilities/0/description`

~~~~text
Consumes a charge to restore 110 health and 60 mana over 2.
~~~~

## 1358. 亚巴顿·迷雾缠绕

ID：`e01f7cdb62122e1046a5`

条件：base

- `mf-6cc093c00f7c14d0eed4`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/0/description_en`

~~~~text
Abaddon releases a coil of deathly mist that can damage an enemy unit or heal a friendly unit at the cost of some of Abaddon's health.
~~~~

- `mf-87256f71772d383e5b15`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/0/description_zh`

~~~~text
亚巴顿以自身的部分生命为代价，释放出一团致命迷雾，可以对敌方单位造成伤害，或者治疗友方单位。
~~~~

## 1367. 戴泽·虚无投影

ID：`e141a2d57a89b0e6b4bf`

条件：base

- `mf-1e6f0702651a12bed18f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/4/description_en`

~~~~text
While active, Dazzle's basic abilities are empowered: Poison Touch hexes enemies, Shallow Grave heals upon expiration, and Shadow Wave has a shorter cooldown.
~~~~

- `mf-550c22238f3620dd539e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/4/description_zh`

~~~~text
在灵魂形态下，戴泽的基础技能都已强化：剧毒之触带有妖术效果；薄葬结束时会治疗；暗影波的冷却时间变短。
~~~~

## 1378. 寒冬飞龙·极寒之拥

ID：`e334bb67db85cc0d0813`

条件：base

- `mf-f488ff556700d0281a25`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/109/abilities/2/description_zh`

~~~~text
将队友封入一个冰茧中，使其被冻在原地并恢复生命值，恢复数值为基础数值加上最大生命值的一定比例。
~~~~

- `mf-fcbf193a5ae16d54753e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/109/abilities/2/description_en`

~~~~text
Encases an ally in an icy cocoon, freezing them solid while healing a base amount as well as a percentage of their maximum health each second.
~~~~

## 1395. 祸乱之源·蚀脑

ID：`e5950d9618750a3af0f7`

条件：base

- `mf-11116843ace9aa9cc3f7`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/2/abilities/1/description_en`

~~~~text
Feasts on the vital energies of an enemy unit, healing Bane and dealing damage.
~~~~

## 1397. 娜迦海妖·海妖之歌

ID：`e5d167e5b2de0ef45f8c`

条件：shard_upgrade；需要魔晶

- `mf-088df6ace8be85fc7ffe`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/87/abilities/4/upgrade_text/shard_loc/zh`

~~~~text
海妖之歌范围内友军每秒会恢复一定百分比的生命和魔法。
~~~~

## 1400. 戴泽·虚无投影

ID：`e66dd326b4e5773e543a`

条件：shard_upgrade；需要魔晶

- `mf-5ff20c07d120be1a607f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/4/upgrade_text/shard_loc/zh`

~~~~text
他在虚无之境时治疗效果得到增强。
~~~~

- `mf-b41ccec9d51cb6ace753`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/4/upgrade_text/shard_loc/en`

~~~~text
Increases healing done while in the Nothl Realm.
~~~~

## 1451. 斯拉达·汪洋前哨

ID：`ede75e1cc0b0f62e8c49`

条件：base

- `mf-4198b2f9675e7bfb7f04`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/27/abilities/3/description_zh`

~~~~text
斯拉达在水洼、水迹或河道中将获得移动速度、生命恢复、攻击力和护甲加成。
~~~~

- `mf-6e51bde7382fe3cddc11`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/27/abilities/3/description_en`

~~~~text
Slardar gains bonus movement speed, health regeneration, attack damage, and armor while in a puddle, trail, or river.
~~~~

## 1452. 祸乱之源·蚀脑

ID：`ee4efca2197c20e479f8`

条件：shard_upgrade；需要魔晶

- `mf-47787d7fc2b7f65ac1aa`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/2/abilities/1/upgrade_text/shard_loc/en`

~~~~text
Secondary targets only heal for %shard_secondary_target_heal_pct%%%.
~~~~

- `mf-efb748f33def6f40e62c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/2/abilities/1/upgrade_text/shard_loc/zh`

~~~~text
次级目标只有%shard_secondary_target_heal_pct%%%治疗效果。
~~~~

## 1455. 影魔·魂之挽歌

ID：`ef2cf1208f6434562032`

条件：scepter_upgrade；需要A杖

- `mf-c0a3b7f5a4c12a376310`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/9/abilities/3/upgrade_text/scepter_loc/en`

~~~~text
The wave back to Shadow Fiend heals him for all the damage it dealt.
~~~~

## 1471. 全能骑士·纯洁之锤

ID：`f292d3b0a154035bc0ec`

条件：base

- `mf-f3beec09ae999534a0de`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/55/abilities/2/description_en`

~~~~text
Omniknight heals for %heal_pct%%% of the damage dealt over %heal_duration%s.
~~~~

## 1473. 凯·猛禽之舞

ID：`f3094bee1ae808d5f1cf`

条件：base

- `mf-74c9a32c3ff50087383f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/125/abilities/4/description_zh`

~~~~text
如果施法成功完成，凯会对周围发动致命的辐射状斩击，基于目标的最大生命值造成伤害，并且造成伤害的一定百分比会治疗凯。
~~~~

- `mf-965d6cba15df920d8e2a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/125/abilities/4/description_en`

~~~~text
If the cast completes successfully, Kez performs a series of deadly radial slashes around him that deal damage based on the max health of the target and heal Kez for a percentage of all damage dealt.
~~~~

## 1481. 暗影恶魔·邪恶净愈

ID：`f3eb3feeda51824f539b`

条件：base；需要魔晶

- `mf-1cf8189ec0058e50b48d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/77/abilities/3/description_zh`

~~~~text
在持续时间结束时该单位受到治疗效果。
~~~~

## 1499. 圣洁吊坠

ID：`f7b67f8c245ad7fdd7ca`

条件：item；装备模式=passive

- `mf-7229fff243ea84faf7ed`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/holy_locket/abilities/1/description`

~~~~text
Amplifies heals you provide by 10%.
~~~~

## 1529. 神谕者·天命之雨

ID：`fbf66e320cac4d66ddf8`

条件：base；需要魔晶

- `mf-01cfdcbbdbb74e51dacf`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/3/description_zh`

~~~~text
站在该区域的敌人受到每秒伤害，并且治疗增强被削弱。
~~~~

- `mf-28be09bc03e42ff7e32f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/3/description_en`

~~~~text
Allies in the area heal and have increased incoming Heal Amplification.
~~~~

- `mf-72c2a3825b94f878b0fc`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/3/description_en`

~~~~text
Enemies standing in the area receive damage and have reduced Heal Amplification.
~~~~

- `mf-bffbb5ff52f07d9185cf`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/107/abilities/3/description_zh`

~~~~text
区域内友军被治疗，并且具有治疗增强效果。
~~~~

