# MK-T3：机制事实与待复核证据

本页是 MK-T3 的接口、复现与评审入口；唯一进度仍在[开发计划 §7](development-plan-2026-10-30.md#7-状态表唯一进度来源)。基于已有快照离线生成，不采集比赛、不训练。T4 的机制交互与出装规则尚未开始。

## 交付与结果

> **最新（2026-11-05，U85–U92）**：后续任务读取`knowledge/mechanics/current.json`指向的版本（现为[复核后事实v19](../knowledge/mechanics/extractions/v19/README.md)，U113）；对照见`knowledge/mechanics/reviews/recall-check-002/`。[v12](../knowledge/mechanics/extractions/v12/README.md)、[v11](../knowledge/mechanics/extractions/v11/README.md)、[v10](../knowledge/mechanics/extractions/v10/README.md)保留。v9及之前：[复核后事实v9](../knowledge/mechanics/extractions/v9/README.md)，它在v3上叠加全部判断；v1–v8保留。

> **当前版本（2026-11-01）**：v2（词表v3、规则v2）见[知识框架§6](knowledge-framework.md)；v3在v2基础上去掉Valve标记为“当前无此升级”的A杖/魔晶文字，见§7，命令`PYTHONPATH=src python scripts/build_mechanics_facts_v3.py --output <新目录>`。下文描述v1，保留不改。

产物在 [`knowledge/mechanics/extractions/v1/`](../knowledge/mechanics/extractions/v1/)：

| 文件 | 用途 |
|---|---|
| `facts-v1.json` | 逐条证据、来源、条件、字段值、引用与稳定 ID；含全部受检对象及文本扫描清单 |
| `coverage.json` | 全部45个机制的命中数、未知对象、限制与复核统计 |
| `review.csv` | 完整复核队列，保留空白 decision/reason |
| `review-sample.csv` | 按U5抽取的约三分之一复核组 |
| `manifest.json` | 输入、实现、输出的字节SHA-256收据 |

扫描127位英雄的734个技能，以及登记表中非中立、非图纸、价格大于0的209个装备候选条目。产生4,807条证据：2,006条结构化字段观测（`auto`），2,801条待语义复核（`needs_review`）。45个机制均有命中；这不证明召回完整或语义正确。107个装备没有命中，63个装备没有可扫描的说明文字，详细名单在覆盖报告；未命中表示未知。

装备筛选复用交接约定的价格/中立/图纸口径，是快照清单代理，不认证当前商店可购买性：清单仍含信使、历史装备、Roshan消耗品等。候选记录显式标记`inventory_status=registry_candidate`；本任务不自行改变数据范围。后续如需严格当前商店清单，须另行核对来源与口径。

## 证据与条件

- `official_text`是沿用词表的证据种类名，**不等于发布者认证**。英雄说明来自Valve登记表；装备说明来自OpenDota社区快照，`publisher`逐条标明。上游出处分别见[英雄来源清单](../knowledge/hero-capabilities/source-manifest.json)与[装备来源清单](../knowledge/items/sources/manifest.json)。本次指针定位仓库登记表/说明文件，没有重新核验所有登记表文字与原始HTTP响应的转换关系。
- `enum:*`只记录已确认的枚举值。`dispellable=0`保留为“不产生可驱散效果”的字段观测，不能解释为不可驱散。施加强/弱驱散另从说明提取。
- `field:mana_costs`保留完整数值列表，包括0；不在T3推断“法力依赖”。`item_attr:*`保留快照原值，不转换单位或合并不同版本数值。
- 所有文字匹配均为`assertion=candidate`，需要判断施加者、接受者、否定、触发时点和条件；`auto`只表示字段观测可机械复现，不是游戏效果认证。
- 原始技能获得条件（`granted_by_scepter/shard`）和升级说明条件分别保留。A杖/魔晶说明不会合并成基础技能能力；同一技能若两种标志均有，保留两者供核对，不擅自推断替代关系。命石相关文字需人工判读，本次不单独扫描命石字段或天赋。
- 被动位只产生“受破坏影响”候选，不能认证“关键被动”。敌法师法力损毁、潮汐猎人海妖外壳额外引用U28用户原话，标`manual`与待复核；不伪装成官方说明。
- 所有产物`patch_verified=false`。版本未核对，不能把此快照用于历史比赛机制结论。

## 评审方法

相同对象、机制和条件的中英文/多段引用合并为1组，共1,551组。按组的SHA-256排序每3组取1组，得到517组抽查表；抽样用于U5协作，不构成独立准确率评估。

在CSV副本的`decision`填`accept`、`reject`或`uncertain`，在`reason`解释接受者、条件、时点或错误。审阅结果保存为独立修订，不编辑v1冻结文件；此版本尚无自动应用评审结论的接口。原始候选不会因为被抽中而自动通过，也不能直接用于T4规则或训练标签。

建议先核对以下关键例子，然后分批处理抽查表：

| 对象 | 本次证据/处理 | 重点 |
|---|---|---|
| 主宰·剑刃风暴 | 结束时施加强驱散，保留英文原句 | 时机在结束时，不是把整段旋转都标为强驱散 |
| 朗戈·动人之舐 | 弱驱散、位移他人；可驱散性值0 | 施加驱散与自身留下可驱散效果是两回事 |
| 熊战士·激怒 | 强驱散、状态抗性；没有减益免疫候选 | 穿透枚举字段不等于自身获得免疫 |
| 克林克兹·扫射 | 当前说明未产生致盲候选 | 仅表示当前抽取未发现，不能证明所有版本无致盲 |
| 金箍棒 | 穿透闪避；未推断针对致盲 | 机制交互留待T4 |
| 白银之锋 | “disable their passive abilities”破坏候选 | 与被破坏影响区分 |
| 散夜对剑 | 状态抗性16、减速抗性30（原始属性字符串） | 数值与补丁快照绑定 |
| 海妖外壳/法力损毁 | U28关键被动人工证据候选 | 官方未明确写破坏，不能用缺失字段当反例 |

已知缺口：碎颅锤穿透减益免疫在现有装备说明中没有依据；用户知识已在交接中记录，但该机制词表不允许`manual`证据，因此这里只在覆盖报告提示缺口，不扩改已确认词表。关键词规则仍可能把引用其他技能、受害者效果或升级的条件描述列为候选；否定句过滤也可能漏掉复合句中的正面事实。没有全量游戏语义验收或召回率估计。

## API与复现

`dota_items.data.mechanics_facts`是纯数据模块：

- `build_facts(sources)`：从固定6个来源文档产生确定性证据。JSON来源以解析对象传入，U28 Markdown以`{"text": 原文}`传入。
- `load_facts(doc, sources)`：验证来源摘要、JSON指针、逐字引用、字段原值、唯一ID；重放固定版本抽取，拒绝错归属、错误条件、篡改审批状态、漏行和多行。
- `coverage(doc, terms)`：逐机制/对象计数，明确未知和无文本对象。
- 指针遵循RFC 6901；字符串引用使用原文子串，结构化引用为`quote_encoding=json`，是该字段值的规范JSON序列化，不冒充自然语言原文。

新环境依照交接安装已声明依赖；当前云端检查环境为`/workspace/scratch/dota-venv`。从根目录复现到一个**不存在的新目录**：

```bash
PYTHONPATH=src python scripts/build_mechanics_facts.py --output /tmp/mechanics-facts-new
PYTHONPATH=src python -m pytest tests/test_mechanics_facts.py tests/test_mechanics.py -q
python scripts/check.py --scope all
```

脚本来源读取统一走`data.source_io`，不访问网络，不覆盖既有目录。输入、规则或词表变化时，旧v1仍按旧来源/实现验证；升级生产者必须出新版本，不回写旧证据来通过哈希校验。`source_hashes`是解析对象的规范JSON摘要；收据额外保存实际文件字节摘要。哈希仅用于一致性检查，不是来源真实性签名。

## 验证范围

专项44项通过：真实快照全部引用核验、全对象覆盖、已知语义回归、A杖/魔晶条件、否定和子串误命中、字段/来源/归属/复核状态篡改拒绝、可重复生成、旧目录保护。全量`check.py --scope all`通过：pytest 1,426通过、17跳过；Ruff、22项学习/英雄知识unittest及全部JS检查通过。17项跳过来自不在Git中的本地冻结产物。检查前后所有跟踪/未跟踪文件指纹一致，随后仅补记本验收结果。工程通过不代表候选已经过用户语义评审。

产物目录在`.gitattributes`中标为`-text`，避免Git转换CSV换行符使收据失配；提交时额外对Git暂存区blob逐项核对输出哈希。

## 独立语义复核

首批24组助手判定与原抽样中的8组用户抽查见[语义复核说明](mechanics-review.md)，机器记录在`knowledge/mechanics/reviews/batch-001.json`。评审建议独立保存，接受建议不等于用户批准，不修改v1事实或抽查CSV。
