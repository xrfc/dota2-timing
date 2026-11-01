# 覆盖检查发现（Claude第1轮）

检查范围：PR #11复核包`coverage.json`的无命中对象清单、`field-observations.jsonl`中的装备属性观测，以及U15/U21针对装和常见克制装备的说明原文（OpenDota dotaconstants社区快照，`patch_verified=false`）。没有逐个检查全部943个对象。以下都是**新候选，不改现有case ID**；指针相对仓库根目录。

## 1. 重要：针对装本身漏抽

| 对象 | 机制 | 原文 | 指针 | 影响 |
|---|---|---|---|---|
| 斯嘉蒂之眼 `skadi` | 减速 `slow`、治疗削减 `heal_reduction` | “Attacks lower enemy movement by -25% … lower enemy attack speed by -25% and Health Restoration by 50%.” | `knowledge/items/sources/dotaconstants-items.json` `/skadi/abilities/0/description` | U15主宰针对装，包里**没有任何候选组**；原文用“lower”而非“slow/reduces”，抽取规则漏掉 |
| 辉耀 `radiance` | 闪避 `evasion` | 属性字段`evasion`=25 | 同上文件 `/radiance/attrib/4`（key=`evasion`, value=`25`） | 与用户确认的“敌方出辉耀时会出金箍棒”（U29）直接相关；装备属性目前只抽了状态/减速抗性 |
| 天堂之戟 `heavens_halberd` | 缴械 `disarm` | “Disarm: Prevents a target from attacking for 3.5 seconds.” | `/heavens_halberd/abilities/0/description` | 描述只写“阻止攻击”，没出现disarm；技能标题才是“Disarm” |
| 希瓦的守护 `shivas_guard` | 减速（攻速）`slow` | “Freezing Aura: Reduces the attack speed of all enemies by -40.” | `/shivas_guard/abilities/1/description` | 主动减速已收录，光环的攻速降低漏掉 |
| 林肯法球 `sphere` | 格挡指向技能（U31交互，不在45项词表） | “Spellblock: Blocks most targeted spells once every 14 seconds.” | `/sphere/abilities/0/description` | U21辅助针对装相关；U31把林肯格挡定为单独记录项，建议在交互记录中补上林肯法球本身 |

### 用户补充的漏抽与交互（U33）

- 斧王·反击螺旋：用户确认固定值反击算反伤，但它不在反伤候选中（`knowledge/hero-capabilities/hero-registry.json`中`axe_counter_helix`）。
- 编织者·连击、米拉娜·天界箭袋、凯·影武长刀等可主动施放/开关的攻击类技能：用户报告不触发敌法师法术反制、清莲宝珠、林肯法球。按U31应单独记为交互（user_reported），建议补入`targeting-examples`。
- 神谕者·虚妄之诺：用户认为不算治疗、应算“免疫”类，当前没有对应候选组。

## 2. 装备属性字段（`item_attr:`）只覆盖了两类

`field-observations.jsonl`中只有`slow_resistance`（4件）和`status_resistance`（3件）的属性观测，散夜对剑的+16%状态抗性也在其中，没有漏。但其他与针对相关的属性没有抽取，例如：

- 闪避：辉耀（上表）；蝴蝶、闪避护符只有附注“与其他闪避来源递减叠加”被收录，数值在属性字段。
- 伤害格挡：先锋盾、深渊之刃、赤红甲只靠附注“多个伤害格挡来源不叠加”间接收录（第1轮按附注接受），格挡数值在属性字段。

建议：对词表中依据含`item_attr:`的机制，扫描装备`attrib`的对应key（至少evasion、damage_block类）。

## 3. 抽取规则的系统性问题（供修正抽取器）

1. 动词不只“slow/reduce”：`lower`、`prevents … from attacking`、`steal … speed`都会漏抽。
2. 英雄名误命中：中文“魅惑魔女”触发“魅惑”，英文“Lifestealer”触发lifesteal。建议匹配前去掉英雄名和技能名。
3. 复合词误命中：slow resistance、slow heal、slow-moving bolt、“破坏性”“破坏树木”、strikes fear、summons a … (flames/meteor/storm)、barrier（地形屏障）、swaps（切换形态）、pulling points（属性转移）。
4. 方向与状态：大量“while/if stunned”“interrupted if”“can hit invisible”“works on spell immune”“reveals invisibility”被抽成施加该机制。建议对“被X时/对X单位有效/揭示X”加否定或交互标记。
5. 被动字段≠受破坏影响：海妖外壳`behavior`=2052不含被动位，靠用户知识才收录；反过来，大量先天被动有被动位但不一定受破坏影响（第1轮100组不确定）。

## 4. 词表可能的缺口（定义属于用户，只作提示）

- 虚无/物理免疫：虚灵之刃、幽魂权杖、帕格纳·衰老、琼英碧灵·越界让目标免疫物理伤害但不能攻击；目前只能拆进“缴械”“吹风/放逐”，不完全贴切。
- 护甲削减：黯灭、强袭胸甲、斯拉达·侵蚀雾霭、粘稠鼻液。常与物理核心的出装相关，词表中没有。
- 攻击/技能伤害降低（对敌减益）：龙骑士·火焰气息、潮汐猎人·锚击、法师克星。第1轮把它们从“护盾/减伤”中排除，但没有对应机制可归。

## 5. 来源与版本

- 熊战士·激怒：用户核对“没有减益免疫，只有状态抗性”，与快照一致（U29）。
- 金箍棒、标枪、血棘只写“穿透闪避”，没有任何装备说明提到致盲（U30）。
- 全部装备说明来自社区快照；本轮没有联网核对当前补丁。
