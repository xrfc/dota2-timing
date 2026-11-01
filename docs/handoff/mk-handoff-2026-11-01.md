# 交接：机制知识底座MK（2026-11-01）

> 写给接手的模型/开发者。用户要求“把待办事项详细写入文档”，由另一个模型接手。本文自成一体：先读§0，再按§3逐项做。进度仍以[开发计划](../development-plan-2026-10-30.md)§7为唯一来源，本文是MK的详细任务说明。

> 后续实现：MK-T3已有`knowledge/mechanics/extractions/v1/`首版证据包及校验器，待语义抽查。操作与局限见[机制事实](../mechanics-facts.md)，最新进度见计划§7。下文保留交接时点任务说明。

## 0. 先读这些（按顺序）

1. `AGENTS.md`：项目规则。重点：所有改动同步维护文档（U24）；临时环境用`<ai名>-temp`分支（U25）；改数据口径/标签/采集/训练前必须问用户；账号ID不得入库。
2. [开发计划](../development-plan-2026-10-30.md)§0（接手须知）、§2（决策登记）、§4“MK机制知识底座”、§7（状态表与下一步）。
3. [机制知识框架设计](../knowledge-framework.md)：三层结构、已确认内容、用户回答。
4. `docs/decisions/`中U26–U30（2026-10-31～11-01）：知识框架的全部用户决定与原话。
5. `knowledge/mechanics/README.md`与其中两个JSON。
6. [英雄特性分析](../hero-traits-analysis.md)§6：用户抽查反馈（v2要吸收）。

用户是在学ML的Dota玩家（主玩1/5号位、传奇段）。**回复用中文**，不要只给结果，要讲清数据、规则、局限和备选（AGENTS“学习与决策透明”）。用户的游戏知识非常关键：多次纠正了数据推断（见§4）。

## 1. 当前状态（2026-11-01，main＝b848657）

| 里程碑 | 状态 |
|---|---|
| M0、M1 | 完成 |
| M2 出装时间 | 结案（U13） |
| M2b 赛前针对装 | **暂停于T6c**（U27），MK完成后回M2b-T6d |
| **MK 机制知识底座** | **进行中**：T0、T1、T2完成；**下一步T3** |
| M3–M6 | 未开始 |

MK已有产物：

- `knowledge/mechanics/enums-v1.json`：官方技能原始枚举解码，**五个字段全部经用户确认**（U30）：
  - `dispellable`：0不产生可驱散效果 / 1仅强驱散 / 2弱驱散可驱散 / 3不可驱散
  - `immunity`：0不涉及 / 1对友方生效 / 2对减益免疫友方不生效 / 3穿透减益免疫 / 4不穿透 / 5对友穿透对敌不穿透
  - `target_team`：0无 / 1友 / 2敌 / 3双方 / 4自定义
  - `damage`：0无 / 1物理 / 2魔法 / 4纯粹
  - `type`：0普通 / 1大招
  - 未解码：`behavior`（只用位2＝被动、位8＝单位目标）、`target_type`
- `knowledge/mechanics/vocabulary-v1.json`：**45项机制、9类**，待答问题已全部由用户回答（U28–U30）。依据类型：`enum:X`、`field:X`、`item_attr:X`、`official_text`、`manual`。
- `src/dota_items/data/mechanics.py`：`load_enums(doc, registry_heroes)`（例子技能取值必须一致、登记表中出现的取值必须都有解释）、`load_vocabulary(doc, enums)`、`decode`、`unconfirmed`。测试`tests/test_mechanics.py`。

## 2. 环境与流程

**在云端/临时容器**（无`data/`、`reports/`、`.venv`、`configs/user.local.json`）：

```bash
python3 -m venv $SCRATCH/venv
$SCRATCH/venv/bin/pip install -q -e ".[dev,replay,data]" scipy   # 或逐个装：httpx pydantic pytest ruff pandas scikit-learn numpy gem-dota==0.10.0
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY NO_PROXY='*' no_proxy='*' \
  $SCRATCH/venv/bin/python scripts/check.py --scope all
```

基线：ruff通过；pytest **1391通过、17跳过**（跳过的是不在git中的本地冻结产物）；学习与前端JS测试通过。

- 分支：按[AI临时分支契约](ai-temp-branch-contract.md)，在自己的`<ai名>-temp`提交、随时推送、开PR到main；**合并PR、推送main、删除分支须用户同意**（用户曾明确说“你来合并吧”“可以整理合并了”，那是针对当时的PR，新PR需再确认）。
- 云端提交身份：`Claude <noreply@anthropic.com>`（其他AI用其环境要求的身份）。
- 云端git通道**不能推送标签**（见§5）。
- **本地OpenClaw工作区**：仍只用`main`，复用`.venv`，见AGENTS。

每完成一项：跑相关检查→更新文档（相关文档、计划§7/§8、CHANGELOG、决策记录、学习笔记`learning/docs/project-ml-notes.md`）→提交→推送→PR。

## 3. 待办任务（按顺序，只做当前一项）

### MK-T3 事实层·官方说明事实抽取（下一步）

**目标**：对全部英雄技能（基础技能＋A杖/魔晶升级，`granted_by_scepter`/`granted_by_shard`/`upgrade_text`）和全部可购买装备，逐条抽取词表中45项机制的事实，每条附原文引用与出处，可追溯、可校验。

**输入（全部已在仓库）**：

- 英雄：`knowledge/hero-capabilities/hero-registry.json`，127位英雄、734个技能；每个技能有`name`（内部名）、`name_zh`、`description_zh/en`、`notes_zh/en`、`upgrade_text`（`scepter_loc`/`shard_loc`）、`special_values`、`raw_mechanics`、`mana_costs`等。
- 装备：`knowledge/items/item-registry.json`（545件；非中立、非图纸且有价格的约209件）；机制文字只有英文：`knowledge/items/sources/dotaconstants-items.json`的`abilities[].description`、`notes`、`attrib`（如散夜对剑`status_resistance`=16、`slow_resistance`=30）。`itemlist-schinese.json`只有中文名，**没有中文说明**。
- 词表与枚举：`knowledge/mechanics/`。

**建议产出**（名称可调整，调整须写进文档）：

- `knowledge/mechanics/facts-v1.json`：每条事实`{fact_id, subject_type: hero_ability|item, subject, ability/item名, mechanism, evidence_kind, quote（原文片段）, pointer（来源文件+JSON路径）, extractor（规则名）, review: auto|needs_review}`。可参考旧推荐知识包`knowledge/recommendation/7.41f-v1/knowledge.json`的`facts`格式（source_id、pointer、quote、summary、conditions）。
- `src/dota_items/data/mechanics.py`（或新模块）中的抽取函数＋`load_facts`校验：mechanism必须在词表、quote必须真实出现在pointer指向的文本中、subject必须存在。
- 抽取脚本写到`scripts/`，输出到**新目录**（不覆盖旧产物）；覆盖率报告（每个机制命中多少技能/装备、哪些机制没有命中、哪些需人工复核）。
- 测试：合成用例＋真实文件校验。

**已知坑（务必处理，这些都是这次会话中踩过或用户纠正过的）**：

1. **误命中**：子串匹配会出错。`ward`命中towards/forward；`charge`命中技能充能`AbilityCharges`；“破坏”命中“破坏性的冰爆”“破坏树木”；`mana`命中通用字段名`AbilityManaCost`（每个技能都有）。用词边界、排除`Ability*`通用字段名（`hero_traits.ENGINE_FIELD`已有）、中文排除“破坏性”“破坏树木”。
2. **驱散**：
   - “施加驱散”：说明里写“驱散类型：弱驱散/强驱散”的有30个（弱20、强10，预览名单见下），但**有些只在正文里写**，如主宰·剑刃风暴英文“Applies a strong dispel at the end of the spin”，必须一起抽。
   - “效果可驱散性”直接用`enum:dispellable`，不要从文字推断。动人之舐`dispellable=0`（不留buff，用户确认）但它**施加**弱驱散——两件事分开记。
   - 弱驱散预览：主宰·无敌斩、幻影长矛手·神行百变、噬魂鬼·狂暴、噬魂鬼·感染、魅惑魔女·魅惑、哈斯卡·牺牲、末日使者·末日、炼金术士·化学狂暴、炼金术士·狂暴药剂（魔晶）、祈求者·强袭飓风、暗影恶魔·邪恶净化、暗影恶魔·邪恶净愈（魔晶）、混沌骑士·混沌之军、米波·掘地（魔晶）、娜迦海妖·镜像、巨魔战将·战斗专注、神谕者·气运之末、石鳞剑士·地雷滚滚、琼英碧灵·越界、朗戈·动人之舐。
   - 强驱散预览：暗影萨满·禽戏、潮汐猎人·海妖外壳、编织者·时光倒流、熊战士·激怒、斯拉克·黑暗契约、亚巴顿·无光之盾、亚巴顿·回光返照、军团指挥官·强攻、凤凰·超新星、神谕者·虚妄之诺。
3. **破坏**：
   - “施加破坏”：幻影刺客·刀阵旋风、冥界亚龙·蝮蛇突袭、司夜刺客·复仇、森海飞霞·一箭穿心；装备白银之锋（英文“disable their passive abilities”）。
   - “受破坏影响”＝**关键被动**（U28用户定义，例：敌法师·法力损毁、潮汐猎人·海妖外壳）。官方说明**经常不写**破坏（这两个都没写），海妖外壳`behavior`=2052也**不含被动位**——所以只能“字段/说明找候选＋助手标是否关键被动＋用户抽查”，在facts里标`needs_review`，不能自动定论。官方注明“破坏会使……失效”的约30个技能可作候选来源。
4. **减益免疫**：技能侧用`enum:immunity`（3＝穿透）；装备侧看英文说明（如深渊之刃“Pierces Debuff Immunity”）。用户定义：减益免疫时只有穿透效果生效，如碎颅锤重击能眩晕开黑皇杖的单位。注意碎颅锤英文说明里没写穿透，需要在facts里注明来源是用户知识（`manual`）或找到官方依据。
5. **闪避≠致盲**（U30）：金箍棒/标枪/血棘英文只写“pierce through evasion”，**没有装备说明提到致盲**。致盲技能的可驱散性：激光、麻痹之咬、致盲之光、旋风飞斧（近战）、扫射＝2；渡鸦之纱＝1；沙尘暴、烟幕＝3。v1把克林克兹·扫射标为致盲**需复查**。
6. **法力**：法力依赖不在T3判断（推导层）；T3只抽`mana_cost`（字段）与`mana_gain`（自身回蓝/吸蓝，如莱恩·法力吸取；中文“回复/恢复/获得/汲取/吸取…魔法/法力”约23个候选）与`mana_burn`。
7. **状态/减速抗性**：装备看`attrib`（`item_attr:status_resistance`等）；技能看说明（熊战士·激怒：状态抗性+50%，**没有减益免疫**，用户核对确认）。
8. **补丁**：快照未核对补丁版本（`patch_verified=false`），所有产物要标明。

**需要先问用户的**：若决定需要装备中文官方说明（Valve datafeed）而必须联网抓取——**联网采集须用户授权**（计划Q7）。助手此前的方案是先用英文说明完成T3，确有需要再问。

**验收**：所有fact的quote能在来源中逐字找到；mechanism都在词表；覆盖率报告；`needs_review`清单交用户抽查约1/3（U5判断类）；文档同步。

### MK-T4 机制规则层（T3后）

把“谁克制谁、机制如何交互”写成可执行规则，引用第1层字段与facts。助手起草、**用户拍板**（等同M2b的Q10）。已收集到的规则草案与用户知识：

- 弱驱散（否决坠饰主动为弱驱散，OpenDota物品说明）→ 去除敌方`dispellable=2`的正面效果（风行、幽魂护罩、无光之盾、冰霜魔盾等）；对`dispellable=3`无效（守护天使、虚妄之诺、折光——v1误标过）。
- 破坏（白银之锋）→ 使“关键被动”失效。
- 金箍棒类 → 克制**闪避**，不克制致盲。
- 散夜对剑 → 状态抗性16%、减速抗性30%，克制“敌方控制/减速多”（用户：能降低被控制时间）。“控制多”的旧定义（≥2个控制技能）不用。
- 碎颅锤 → 重击可穿透减益免疫；对**能强驱散自身解控**的英雄（熊战士·激怒）可在解控后重新控制（用户解释）。
- 金箍棒在敌方噬魂鬼/露娜/司夜刺客时也高，用户确认原因是敌方常出蝴蝶/辉耀 → 触发条件必须包含**敌方装备**（U22）。
- 巫妖×碎颅锤偏高：**未解释**，不建规则。
- 法力依赖＝高蓝耗**且**无自身回蓝（U28）；门槛在T4/T5和用户定。
- 待用户：各规则的具体门槛、“敌方先出”的时间口径（原Q10）。

### MK-T5 推导层（T4后）

由规则自动生成：英雄机制档案、装备机制档案、克制关系图、hero-traits v2（替代`knowledge/hero-traits/hero-traits-v1.json`，v1不改）。每条附证据链；人工改动须登记理由。吸收[英雄特性分析](../hero-traits-analysis.md)§6的抽查反馈（朗戈证据技能、3条不可驱散、致盲≠金箍棒、扫射复查等）。交用户抽查约1/3（含助手标注的“关键被动”）。

### MK-T6 维护（T5后）

补丁更新流程（新快照→`load_enums`/`load_facts`校验失败点→重算→差异报告）；标注被替代的旧知识（hero-traits v1、`knowledge/recommendation/7.41f-v1`）；文档与学习笔记。之后MK结案，回**M2b-T6d**（触发条件直接引用MK规则），再T8数据验证（需本地M1快照，云端没有）。

## 4. 用户已纠正过的事（避免重犯）

- 朗戈“高机动”证据技能写错（灵呱一闪是降蓝耗）；相关的是动人之舐（位移他人＋弱驱散），归`displace_other`而非自身位移。
- 守护天使、虚妄之诺、折光是**不可驱散**，不能算“依赖可驱散保命”。
- 金箍棒**解决不了致盲**。
- 莱恩蓝耗高但**法力吸取**能抽蓝，所以不算法力依赖。
- 熊战士·激怒**没有减益免疫**，只有状态抗性（＋强驱散）。
- 不要把“不能确认”写成“已证实不符合”；数据没写的不等于不存在（破坏常被官方说明漏写）。

## 5. 等用户做的事（不是接手模型的任务）

- **推送标签**：`v0.3.0`→331c6d0、`v0.4.0`→63d395a（补打，U30）。云端推送标签被拒，用户回到电脑后执行：
  ```bash
  git fetch origin
  git tag -a v0.3.0 331c6d0 -m "v0.3.0: version bumped in pyproject on 2026-10-04 (tagged retroactively 2026-11-01, U30)"
  git tag -a v0.4.0 63d395a -m "v0.4.0: version bumped in pyproject on 2026-10-05 (tagged retroactively 2026-11-01, U30)"
  git push origin v0.3.0 v0.4.0
  ```
- **删除旧远端分支**`claude/hero-traits-candidate-rules`（内容已全部在main；云端会话无删除权限）。

## 6. 计划中更远的待决项（到点再问，不要提前假设）

| 编号 | 问题 | 何时 |
|---|---|---|
| — | M2b针对装清单是否加入白银之锋等 | 回到M2b时 |
| Q10 | 触发条件与“敌方先出”口径 | M2b-T6d（用MK规则） |
| Q4 | 对线“打法”和“10分钟优势”定义 | M3-T1 |
| Q5 | 独立评估采集参数 | M4-T1 |
| Q7 | 每次真实训练与联网采集须单独授权 | 随时 |

## 7. 不做

- 不重训、不在原验证集上调参重跑冻结模型；不覆盖`reports/`旧产物与逐字节快照（`docs/archive/2026-10-22/`、`2026-10-26/`）。
- 不做中立物品与天赋（U27以后再加）；不输出强度/胜率评分；不把“机制存在/高分段常出”说成“该出”。
