# 护盾/伤害吸收/减伤：完整候选清单

吸收一定伤害或按比例减少受到的伤害

以下是证据候选，不含预填的Claude结论。完整上下文见 subjects.jsonl。

## 96. 死亡先知·驱使恶灵

ID：`133d4749ffcb45df4f81`

条件：base

- `mf-828817a74f2b07a10c68`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/41/abilities/4/notes_en/1`

~~~~text
Spirit damage isn't reduced by damage block abilities.
~~~~

## 116. 天怒法师·天裔之盾

ID：`16cc693e6676fafb99c4`

条件：base

- `mf-0508ce91ac70ab065d66`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/99/abilities/3/description_zh`

~~~~text
每次天怒法师用技能对敌方英雄造成魔法伤害时，他都会获得小型的魔法伤害护盾。
~~~~

- `mf-89ba56e637a4ae975605`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/99/abilities/3/description_en`

~~~~text
Every time Skywrath Mage deals magical damage to an enemy hero with his abilities, he gains a small magic damage barrier.
~~~~

## 127. 巨牙海民·寒冰碎片

ID：`19d2d263961c665d9908`

条件：base

- `mf-4c74ed3977d5d612040d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/98/abilities/0/description_en`

~~~~text
When the ball reaches its target destination the shards are released, creating a barrier that lasts for %shard_duration% seconds.
~~~~

- `mf-e6da4dbf96be957c4b62`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/98/abilities/0/notes_en/0`

~~~~text
Creates an impassable barrier.
~~~~

## 143. 水晶室女·冰川护体

ID：`1ce7199620358c6dbfce`

条件：base

- `mf-02347f4d103c8f4c21f1`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/4/abilities/4/description_en`

~~~~text
A portion of the mana Crystal Maiden spends on her abilities is converted into a physical barrier.
~~~~

- `mf-61d617d44f090ea54580`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/4/abilities/4/description_zh`

~~~~text
水晶室女消耗在她技能上的一部分魔法会转化为物理护盾。
~~~~

## 144. 杰奇洛·天生一对

ID：`1cf9056a0b39a73b1927`

条件：base

- `mf-9ace655f2bdee40360c4`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/62/abilities/4/notes_en/0`

~~~~text
The second attack ignores Damage Block.
~~~~

## 177. 虚无之灵·共鸣脉冲

ID：`21a3f725cef95ebc8ad8`

条件：base

- `mf-12111840e962adddc30a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/117/abilities/2/description_zh`

~~~~text
虚无之灵将自己包裹在保护性护盾之中，可以吸收物理伤害，并围绕自身发出一次伤害性脉冲。
~~~~

- `mf-8feb327f10f8a3849973`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/117/abilities/2/description_zh`

~~~~text
脉冲每击中一名敌方英雄，护盾的伤害吸收量都会提升。
~~~~

## 210. 斯温·战吼

ID：`287d0bfe2c98176493f0`

条件：shard_upgrade；需要魔晶

- `mf-69cfcdea27f5c1b4109d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/17/abilities/2/upgrade_text/shard_loc/en`

~~~~text
Warcry is now undispellable and provides a %base_barrier_amount% physical damage barrier.
~~~~

- `mf-e19bb8c5ed18ce8ab8dc`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/17/abilities/2/upgrade_text/shard_loc/zh`

~~~~text
现在战吼不可驱散，并提供%base_barrier_amount%点物理伤害护盾。
~~~~

## 276. 深渊之刃

ID：`325afb07ca5141e24d40`

条件：item

- `mf-c260d0c916d08ee8029d`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/abyssal_blade/notes`

~~~~text
Multiple sources of damage block do not stack.
~~~~

## 322. 幽鬼·折射

ID：`3a661073ca7a02fe545d`

条件：shard_upgrade；需要魔晶

- `mf-fefa16818175a0348660`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/65/abilities/2/upgrade_text/shard_loc/zh`

~~~~text
折射可以主动施放，吸收和反弹的伤害比例提升%activation_bonus_pct%%%，持续%activation_duration%秒。
~~~~

## 353. 潮汐猎人·利维坦的渔获

ID：`3f688fde8c50c887101a`

条件：base

- `mf-134ece03f7fc34bbcf5c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/28/abilities/5/notes_en/1`

~~~~text
Bonus Damage Block only applies if another source of Damage Block will be affecting the incoming physical attack.
~~~~

- `mf-3cbe55b665c582a31f55`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/28/abilities/5/description_en`

~~~~text
Whenever an enemy hero is killed by Tidehunter or dies under his debuffs, a fish appears in their place; Tidehunter can eat the fish to permanently gain %fish_health_bonus% Health, %fish_attack_range% Attack Range, and %fish_damage_block% Bonus Damage Block.
~~~~

## 356. 龙骑士·火焰气息

ID：`3fc4a148fde9bd9cb9ba`

条件：base

- `mf-15525368282bbce0bdd2`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/47/abilities/0/description_en`

~~~~text
Unleashes a breath of fire in front of Dragon Knight that burns enemies and reduces the damage their attacks deal.
~~~~

## 397. 先锋盾

ID：`46a68fce35d5f904fce3`

条件：item

- `mf-19ac37dbdf00c7d17b66`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/vanguard/notes`

~~~~text
Multiple sources of damage block do not stack.
~~~~

## 398. 暗影萨满·禽戏

ID：`46acc3dfe5b9f414eabe`

条件：shard_upgrade；需要魔晶

- `mf-3479fa457daae6c8befa`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/26/abilities/3/upgrade_text/shard_loc/zh`

~~~~text
伤害减免时间提升至%damage_reduction_duration%秒。
~~~~

## 422. 钢背兽·刺针扫射

ID：`4b11dc76587eb491d9a6`

条件：base

- `mf-07cb16e78474f0b12094`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/97/abilities/1/notes_en/0`

~~~~text
Quill Spray damage is not reduced by damage block abilities.
~~~~

## 439. 长盾

ID：`4ec068786133e91d40cd`

条件：item；装备模式=active

- `mf-46311570910ea233e2c9`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/pavise/abilities/0/description`

~~~~text
When cast on an ally, grants them a physical damage barrier that absorbs 250 damage.
~~~~

## 470. 洞察烟斗

ID：`54a8041616495ab6f4ad`

条件：item；装备模式=active

- `mf-9a9583881ef4d4ad2ab0`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/pipe/abilities/0/description`

~~~~text
Gives a magic damage barrier that absorbs 425 damage to all nearby allies.
~~~~

## 496. 亚巴顿·无光之盾

ID：`5991fbaf7387e26a1eb7`

条件：base

- `mf-22880fc42f9ce430bd03`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/1/notes_zh/0`

~~~~text
不论护盾因持续时间结束或吸收足够伤害后被摧毁都将造成最大伤害。
~~~~

- `mf-35c37f6449eeae2aa21c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/1/description_en`

~~~~text
When the barrier is destroyed it will burst and deal damage equal to the amount it could absorb to an area around it.
~~~~

- `mf-5adf4021a62dc66000cb`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/1/description_zh`

~~~~text
护盾消失或被摧毁后将会爆炸，对附近区域的单位造成伤害，伤害值为护盾的最大吸收量。
~~~~

- `mf-8b7b80f78ae67948e49d`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/1/description_en`

~~~~text
Summons dark energies around an ally unit, dispelling them and creating an all damage barrier that absorbs a set amount of damage before expiring.
~~~~

- `mf-a4e426aa417105530d78`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/1/description_zh`

~~~~text
召唤黑暗能量环绕友方单位，驱散他们并创造一个全伤害护盾，护盾在消失前能吸收一定量的伤害。
~~~~

- `mf-b17c814bef782a2a8827`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/1/notes_en/0`

~~~~text
The max damage is always dealt whether the barrier is destroyed by expiring or absorbing damage.
~~~~

## 497. 石鳞剑士·幸运一击

ID：`599eeca1d2077418a54f`

条件：base

- `mf-d2dd4af07cc1e6627384`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/113/abilities/2/description_en`

~~~~text
Grants a chance to drastically slow their attack speed and reduce armor on any damage dealt by Pangolier's attacks or abilities.
~~~~

## 584. 树精卫士·活体护甲

ID：`65b3103d3fcdb3e8f522`

条件：base

- `mf-d881212687a3d1502504`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/81/abilities/2/description_en`

~~~~text
If the damage block is decreased to 0, the buff is removed early.
~~~~

## 628. 昆卡·统帅朗姆酒

ID：`6ce1cd8aef442a011a9d`

条件：base

- `mf-022f1ec06db574188c7a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/22/abilities/3/description_en`

~~~~text
Damage from enemy heroes, buildings, or Roshan that would reduce Kunkka below %damage_threshold%%% threshold causes him to douse himself with The Admiral's Rum, receiving bonus movement speed and a delayed reaction to %ghostship_absorb%%% of incoming damage for %buff_duration%s.
~~~~

## 633. 灰烬之灵·烈火罩

ID：`6d838d8f57cbfad8a8c0`

条件：base

- `mf-85ba00a2dc2583c2d058`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/103/abilities/2/description_zh`

~~~~text
护盾消失后将失去伤害效果。
~~~~

- `mf-9b5bbfad36869d8ddba5`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/103/abilities/2/notes_zh/0`

~~~~text
魔法伤害的吸收伤害值计算先于任何伤害减免效果。
~~~~

## 770. 暗影萨满·禽戏

ID：`86107472b869ac2c47ec`

条件：base

- `mf-60ee8e052e28df14c3c3`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/26/abilities/3/notes_zh/1`

~~~~text
受到的伤害减免效果会阻止生命移除类效果杀死暗影萨满。
~~~~

## 802. 伐木机·活性护甲

ID：`8b64c6b15da1e5814a65`

条件：scepter_upgrade；需要A杖

- `mf-5a733185bd06890fc81b`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/upgrade_text/scepter_loc/en`

~~~~text
After %duration% seconds, Timbersaw deals damage to every hero within %explosion_radius% radius equal to %base_explosion% + his remaining barrier amount and loses all of his barrier.
~~~~

- `mf-63f3a71214af2b62f52e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/upgrade_text/scepter_loc/zh`

~~~~text
护盾的恢复速度为每秒%shield_per_sec% + 伐木机%radius%范围内每名敌方英雄都会增加%shield_per_sec_per_enemy%，最高为%max_shield%。
~~~~

- `mf-ca3b78de7c4653b42f83`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/upgrade_text/scepter_loc/en`

~~~~text
Reactive Armor can now be activated to get max stacks and %initial_shield% damage barrier.
~~~~

- `mf-ccf4d79ad15a333a1ea8`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/upgrade_text/scepter_loc/zh`

~~~~text
活性护甲可以主动施放，获得最大叠加次数和%initial_shield%点生命的护盾。
~~~~

- `mf-d2517829d99e736e102f`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/upgrade_text/scepter_loc/zh`

~~~~text
%duration%秒后伐木机会对%explosion_radius%范围内每个英雄造成伤害，数值为%base_explosion% + 护盾剩余生命，而且失去全部护盾。
~~~~

- `mf-ef114c9e5667bb7c5de6`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/96/abilities/2/upgrade_text/scepter_loc/en`

~~~~text
Grants Timbersaw %shield_per_sec% + %shield_per_sec_per_enemy% barrier amount per second for each enemy hero within %radius% radius of Timbersaw up to a maximum of %max_shield%.
~~~~

## 814. 自然先知·传送

ID：`8c8d355aafc58e4701dd`

条件：base

- `mf-599faa51414414723334`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/51/abilities/1/description_zh`

~~~~text
到达地点后获得一个护盾。
~~~~

- `mf-a864ba8bfa24f472039c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/51/abilities/1/description_en`

~~~~text
Gains a barrier after arriving to its destination.
~~~~

## 854. 戴泽·剧毒之触

ID：`929c2e3ee8e05365a8ab`

条件：base

- `mf-5a190bd957396af31478`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/48/abilities/0/notes_en/0`

~~~~text
The damage is not reduced by damage block abilities.
~~~~

## 881. 圣化护服

ID：`9688b836a476295ad496`

条件：item；装备模式=passive

- `mf-afeda574a1e4fa788e26`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/consecrated_wraps/abilities/0/description`

~~~~text
Whenever you take damage from a player-controlled source or Roshan, consume all charges to gain an all damage barrier for 5s that absorbs 120 damage per charge (360 max).
~~~~

## 930. 狙击手·震荡手雷

ID：`9e01a5d70e1b79d6e271`

条件：shard_upgrade；需要魔晶

- `mf-0b606e0fa74c16de00a4`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/33/abilities/3/upgrade_text/shard_loc/en`

~~~~text
Reduces cooldown, increases damage, and allows the knockback to affect Sniper as well.
~~~~

## 956. 圣堂刺客·折光

ID：`a1ad761ffebc6fa4d46e`

条件：base

- `mf-05a612c6380b27dc9028`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/0/description_en`

~~~~text
If an instance of damage would deal more damage than the remaining barrier, all of the damage is absorbed.
~~~~

- `mf-383557199f6ef5e87d33`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/0/description_zh`

~~~~text
如果护盾被摧毁，只要还有能量点数就会再产生一个新的。
~~~~

- `mf-521ae3764f4e181d7241`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/0/description_zh`

~~~~text
圣堂刺客变得高度难以捉摸，获得一个小型护盾，同时获得攻击力加成。
~~~~

- `mf-8acefe4fde98042be823`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/0/description_zh`

~~~~text
攻击力加成和护盾效果相互独立，并且都是有限次数的效果。
~~~~

- `mf-b5727964ea2ba0b94f92`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/0/description_zh`

~~~~text
如果单次伤害超过了剩余的护盾，该次的全部伤害都会被吸收。
~~~~

- `mf-c69bd5f821700dd2a351`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/0/description_en`

~~~~text
If a barrier is consumed, a new one is created as long as there are charges left.
~~~~

- `mf-d19b51511d0de2defd02`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/44/abilities/0/description_en`

~~~~text
Templar Assassin becomes highly elusive, gaining a small barrier and bonus to her damage.
~~~~

## 959. 维萨吉·陵卫斗篷

ID：`a21820793ab04c0c5693`

条件：base

- `mf-f02ecbc5c9606b68b92c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/90/abilities/2/description_en`

~~~~text
Visage generates a layered barrier that protects him from damage.
~~~~

## 984. 赤红甲

ID：`a66f10aab173f53f255e`

条件：item

- `mf-ad6fcb03ee8e27bc1428`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/crimson_guard/notes`

~~~~text
Multiple sources of damage block do not stack.
~~~~

## 1008. 殁境神蚀者·责难

ID：`aaec6a55fe0e79dc1885`

条件：scepter_upgrade；需要A杖

- `mf-0503ad975f7b345d8ae1`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/74/abilities/2/upgrade_text/scepter_loc/zh`

~~~~text
提升最大魔法值转为护盾的比例。
~~~~

- `mf-4f6df7df66009c62f26e`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/74/abilities/2/upgrade_text/scepter_loc/en`

~~~~text
Increases max mana to barrier.
~~~~

## 1033. 炎阳纹章

ID：`add7c06a75f6759f1fa9`

条件：item；装备模式=active

- `mf-798dabdd71eb5b37cc28`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/solar_crest/abilities/0/description`

~~~~text
When cast on an ally, grants them 5 armor, 60 attack speed, 15% movement speed and a 350 physical damage barrier.
~~~~

## 1037. 食人魔魔法师·烈火护盾

ID：`ae41b539256d703aaa7b`

条件：base；需要魔晶

- `mf-0527d9f6cef30f5b5790`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/82/abilities/4/description_zh`

~~~~text
创造一个围绕友军目标的护盾，吸收接下来%attacks%次来自敌方英雄攻击的一定百分比伤害。
~~~~

- `mf-33b70e088c0ed759e72b`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/82/abilities/4/description_zh`

~~~~text
吸收伤害后向攻击者发射火球。
~~~~

- `mf-7d9e403e6ee581f5596c`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/82/abilities/4/notes_zh/0`

~~~~text
触发多重施法时，%multicast_fireshield_aoe%范围内的友方单位将随机获得烈火护盾效果。
~~~~

## 1073. 树精卫士·活体护甲

ID：`b26204baa97325751bc8`

条件：shard_upgrade；需要魔晶

- `mf-97f2cfe4ac423d7b0691`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/81/abilities/2/upgrade_text/shard_loc/en`

~~~~text
Treant now also passively benefits from Living Armor, with the damage block resetting after not taking damage for %passive_reset_cd% seconds.
~~~~

## 1095. 亚巴顿·无光之盾

ID：`b6e74ff2589b8c45f1ef`

条件：shard_upgrade；需要魔晶

- `mf-a78f6e729f1e38f7fd83`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/100/abilities/1/upgrade_text/shard_loc/zh`

~~~~text
会对附近敌人造成吸收伤害的%absorb_to_damage%%%。
~~~~

## 1192. 孽主·侵略大军

ID：`c5c60221b29ab7606e25`

条件：base

- `mf-9cda906a6fa7d3fb1eca`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/111/abilities/3/description_zh`

~~~~text
友方英雄传送后会临时获得承受伤害降低和移动速度加成。
~~~~

## 1195. 石鳞剑士·甲盾冲击

ID：`c5f2867d9eea6599e6ec`

条件：base

- `mf-43d63679198862811925`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/113/abilities/1/description_zh`

~~~~text
甲盾冲击只要击中任意敌方英雄，他就能在短时间内获得一定数值的全伤害护盾。
~~~~

- `mf-e9167ad21d26492bfc3a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/113/abilities/1/description_en`

~~~~text
Pangolier gains an all damage barrier for a short time if Shield Crash hits an enemy hero.
~~~~

## 1227. 殁境神蚀者·责难

ID：`cb2c3f6f91609387f4e2`

条件：base

- `mf-ccd7eb0fe37ea1376673`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/74/abilities/2/description_zh`

~~~~text
施放后，殁境神蚀者获得全伤害护盾，数值为固定值 + 最大魔法值的一定百分比。
~~~~

- `mf-e069badb737439bc2473`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/74/abilities/2/description_en`

~~~~text
When cast, protects Outworld Destroyer with an all damage barrier equal to a flat amount and a percentage of his maximum mana.
~~~~

## 1253. 克林克兹·骨隐步

ID：`cfae8cc03fcac5a12dba`

条件：base

- `mf-e91dbbfbbf97e1aca8e8`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/54/abilities/5/description_zh`

~~~~text
骷髅弓手继承克林克兹一定百分比的攻击力，对建筑造成的伤害降低%skeleton_building_damage_reduction%%%。
~~~~

## 1266. 复仇之魂·移形换位

ID：`d1e70e3519462102ed21`

条件：base

- `mf-7a43aa4b432d9cb74981`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/19/abilities/4/description_en`

~~~~text
Vengeful Spirit and allied swapped units gain a barrier equal to the damage dealt.
~~~~

- `mf-d2f822c71adb68235ce0`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/19/abilities/4/description_zh`

~~~~text
复仇之魂和被交换的友方英雄都会获得等同于造成伤害的护盾。
~~~~

## 1274. 殁境神蚀者·奥术天球

ID：`d3917c7271c8a9fb8413`

条件：scepter_upgrade；需要A杖

- `mf-b05115c2d8e660976016`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/74/abilities/0/upgrade_text/scepter_loc/zh`

~~~~text
奥术天球额外弹跳至一个目标，造成的伤害降低%bounce_damage_reduction%%%。
~~~~

## 1299. 军团指挥官·压倒性优势

ID：`d7ed05993029d123aa15`

条件：shard_upgrade；需要魔晶

- `mf-4a4a104576517622332b`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/102/abilities/0/upgrade_text/shard_loc/zh`

~~~~text
压倒性优势的范围更大，会根据对敌方英雄造成的伤害提供全伤害护盾。
~~~~

- `mf-eea42dd95bbb45453939`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/102/abilities/0/upgrade_text/shard_loc/en`

~~~~text
Overwhelming Odds has larger radius and grants an all damage barrier based on the damage it deals to enemy heroes.
~~~~

## 1313. 微光披风

ID：`da560f636802aa0119e5`

条件：item；装备模式=active

- `mf-e60f1bcd3af443556d42`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/glimmer_cape/abilities/0/description`

~~~~text
5 second delay, grants invisibility, 20 movement speed and a magic damage barrier that absorbs up to 375 damage to you or a target allied unit for 5 seconds.
~~~~

## 1360. 熊战士·激怒

ID：`e07b592a711dcc6e45cd`

条件：base

- `mf-1855c9fb62dce523085b`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/68/abilities/4/description_zh`

~~~~text
乌尔萨进入狂怒状态，承受的伤害降低并获得状态抗性。
~~~~

## 1368. 玛西·护卫术

ID：`e1925c21fa9dbe8aa332`

条件：base

- `mf-4dd6467feb4529756f67`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/121/abilities/2/notes_en/2`

~~~~text
The shared barrier is reduced by damage on either Marci or her partner.
~~~~

- `mf-52a85f73cae49cf36850`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/121/abilities/2/description_en`

~~~~text
As Marci attacks heroes, %shared_barrier_replenish_amount%%% of the damage dealt restores the barrier.
~~~~

- `mf-9043412fdcf9de3a5508`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/121/abilities/2/description_zh`

~~~~text
另外马上还会给她和她的搭档制造共用的全伤害护盾。
~~~~

- `mf-b8306fc0c0684c74c3da`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/121/abilities/2/description_zh`

~~~~text
在玛西攻击英雄时，造成伤害的%shared_barrier_replenish_amount%%%会补充护盾。
~~~~

- `mf-c9beb6881c4fa1d42ea6`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/121/abilities/2/description_en`

~~~~text
Additionally Marci creates a shared all damage barrier for herself and her partner.
~~~~

- `mf-ebc934180079473a492a`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/121/abilities/2/notes_zh/2`

~~~~text
不论是玛西或她的搭档受到伤害都会使共用护盾的数值减少。
~~~~

## 1373. 潮汐猎人·锚击

ID：`e21e1eadb8fa8951d82d`

条件：base

- `mf-fc880475296adfb513c2`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/28/abilities/2/description_en`

~~~~text
Tidehunter swings his mighty anchor to attack and deal bonus damage to nearby enemies and reduce their attack damage.
~~~~

## 1392. 露娜·环月

ID：`e531761c1a75af3bcc9b`

条件：shard_upgrade；需要魔晶

- `mf-ce508cf0c4b3fb5953ea`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/46/abilities/1/upgrade_text/shard_loc/zh`

~~~~text
提升伤害降低效果。
~~~~

## 1394. 美杜莎·魔法盾

ID：`e559bfaf21dd9091be96`

条件：base

- `mf-d20b5355b9ae71b614b0`；Valve via hero registry；`official_text`
- 来源：`knowledge/hero-capabilities/hero-registry.json#/heroes/92/abilities/4/description_zh`

~~~~text
创造一个魔法护盾，消耗美杜莎的魔法值以吸收%absorption_pct%%%的伤害。
~~~~

## 1470. 圆盾

ID：`f227fdd6ca9c2646cf04`

条件：item

- `mf-58fb3cd0c19390bab284`；OpenDota dotaconstants (community)；`official_text`
- 来源：`knowledge/items/sources/dotaconstants-items.json#/stout_shield/notes`

~~~~text
Multiple sources of damage block do not stack.
~~~~

