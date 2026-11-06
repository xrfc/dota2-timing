# 机制知识框架（U26；U27扩为完整版，里程碑MK）

三层结构，每层只依赖下层；设计与状态见[知识框架说明](../../docs/knowledge-framework.md)。

| 层 | 文件 | 状态 |
|---|---|---|
| 1 事实层：官方原始枚举的含义 | `enums-v1.json` | 已经用户确认（U30，MK-T2完成） |
| 1 事实层：机制词表 | `vocabulary-v13.json`（v1–v12保留） | 83项，定义来自用户决定，措辞由助手整理 |
| 1 事实层：复核后事实 | `extractions/v17/`（v1–v12保留） | MK-T3已结束（U67），`basis`标明依据 |
| 2 机制规则层：机制交互与克制 | `rules-v9.json`，结果在`extractions/v17/rules-evaluation.json` | 23条（U73结束T4，U94拆出R21，U97加R22，U100拆出R23），第8、12、13、15条的细节到T5 |
| 3 推导层：英雄/装备机制档案、克制图、hero-traits v2 | `profiles/derived-v7/` | MK-T5进行中，草稿已生成，待U5抽查 |

- 读取一律用`dota_items.data.mechanics.load_enums(doc, registry_heroes)`与`load_vocabulary(doc, enums)`：每个例子技能必须存在且取值一致；登记表中出现的取值必须全部有解释，补丁更新出现新取值时直接报错。
- 修改须记决策并升版本（v2…），旧版本不覆盖。

## 目录和职责（2026-11-06）

| 路径 | 是什么 | 谁写 | 怎么更新 |
|---|---|---|---|
| `enums-v1.json`、`vocabulary-v*.json`、`rules-v*.json` | 枚举、机制词表、规则 | 用户决定，助手写 | 只出新版本 |
| `reviews/` | 审查结果、抽查、裁定操作 | Codex、Claude、用户 | 每轮一个目录，不改旧结果 |
| `extractions/v*/` | 复核后事实和规则求值 | 脚本生成 | 只出新版本；提交后不覆盖 |
| `profiles/derived-v*/` | 档案、克制关系候选、英雄特性 | 脚本生成 | 只出新版本 |
| `extra-abilities-v1.json` | 注册表没有的技能（熊灵） | 用户决定，助手写 | 只出新版本 |

旧版本保留用于复现，新代码只读下面的当前入口。

## 当前数据流（2026-11-06，U92–U98）

```
来源快照（Valve说明、游戏文件） → 候选 → AI审查＋用户裁定 → 事实v17
事实v17 ＋ 词表v13 ＋ 规则v9 → rules-evaluation（来源集合、目标集合）
                                → 派生层derived-v7（档案、克制关系候选）
```

读这些数据时要知道：

- **`basis`**：`user*`、`field`算确认；`two_ai`只是AI一致；`disputed_by_user`是用户标了错、还没裁定，不算确认，原来是用户裁定或字段也一样。
- **`user_feedback`**：抽查的标记和原话。行已不存在的反馈放在`unattached_feedback`，不丢。
- **`condition_notes`**：AI写的条件说明，只供阅读，不能用于自动推理。`condition_review=none`只表示没有说明，不代表无条件。结构化的只有`condition`（基础、A杖、魔晶、装备）。
- **克制关系是候选**：`rules-evaluation`和`counter-graph`只算集合，没有逐对核对条件和例外，`semantics`字段写明了这一点。每条边带`relation`和`status`（`candidate`或`pending`）。程序读边要用`data.mechanics_graph_v2.usable_edges`，查英雄之间的关系用`hero_relations`，两者默认不含待定规则。旧函数`mechanics_graph.edges_between`不带状态，目前只有旧测试在用，新代码不要用。
- **按英雄定目标**：规则v9的`target_heroes`（R12）列出例外英雄，`data.mechanics_rules_v8.expand_rules`展开成目标技能，展开结果在`extractions/v17/rules-expanded.json`。有条件的例外（如有A杖时）仍算目标，边上带`exception`。
- **反馈的身份**（U101）：每条反馈有`feedback_id`（由内容算出，重复导入不变），并记下反馈时这行声称什么（`claim`）。纠正记录用`resolves`写明解决哪几条反馈，见`reviews/feedback-resolutions-001.json`。没被写明解决的“错”一直是`disputed_by_user`；事实内容变了，旧的“对”不再算确认。每行的`feedback_status`写明原因。
- **档案**（U101）：`hero-profiles.json`、`item-profiles.json`顶层写明`status=draft`、`relations=candidate`、`relation_verified=false`和来源版本。每条关联在`candidate_relations`里带`rule`、`relation`、`status`、`pending`、`not_evaluated`、对象编号；`own_facts_confirmed`只说事实，不说关联成立。页面标题改为“候选机制关联”，标签由`status`生成，不读中文规则名。
- **生效条件**（U104）：`rules-evaluation.json`的`source_conditions`、`target_conditions`给每个对象列出`when`（基础、A杖、魔晶、装备，或规则直接列出的`any`）和`unless`（哪种升级会让它不成立）。`unless`只来自事实的`condition_exceptions`和规则的条件例外，不从被排除的升级行推断。关联边带`conditional`和逐个技能的条件；`data.mechanics_conditions.edge_holds(edge, upgrades)`按已知升级返回成立、不成立或说不准（`None`）。
- **没算的规则字段**：`pairs`、`target_exempt_mechanisms`、`parameters`现在不参与计算，`not_evaluated`会列出来。
- **校验**：`manifest.json`记录数据输入（v17直接读冻结的v16，测试追踪真实读取）和导入到的全部仓库源码（测试沿导入关系检查）；数据和源码都在构建前后比对，中途变化或文件被删就报错。

MK-T6再做：统一入口文件`current.json`、补丁状态、数值升级的裁定来源、未生效规则字段改为明确报错。

**当前入口：`extractions/v17/`、`vocabulary-v13.json`和`rules-v9.json`（U83、U85–U104）；派生层`profiles/derived-v7/`（草稿）。补漏见`reviews/full-audit-001/`、`full-audit-002/`，第1–8轮复查见`full-audit-003/`，控制分类重读见`full-audit-004/`，对照见`reviews/recall-check-002/`。**

“可被破坏”与游戏文件的对照见[破坏对照](reviews/break-check-001/README.md)（U46，U47已裁定）；其他机制见[排查报告](reviews/game-files-audit-001/README.md)（U48）；退出装备标记见`retired-items-v1.json`（U51）。

熊灵不算单独英雄，技能列在独行德鲁伊下（`extra-abilities-v1.json`，U90）。

MK-T3接口、来源限制、复现命令与抽查入口见[机制事实说明](../../docs/mechanics-facts.md)。v1包含全部734个技能和209个装备清单候选；原文匹配均待复核，不能直接当作机制规则。

语义复核建议独立放在`reviews/`；首批24组说明与8组抽查见[复核入口](../../docs/mechanics-review.md)。`assistant_decision`与`user_decision`分开，未回复保持null，不能当作用户已同意。

U31的最新四条例子见`reviews/targeting-examples-v2.json`（旧v1保留）：目标方式、林肯响应、莲花响应分别有value/status/evidence；null表示未知，不是false。这里只记录说明例子，不作为MK-T4可执行规则。

用户反馈独立保存：`reviews/batch-001-feedback-001.json`记录抽查3/7/8；魂断的两项交互在例子v2中标为`user_reported`，与`snapshot_supported`区分。

批次001的8条用户抽查已全部反馈；`batch-001-feedback-002.json`记录剩余5条确认，`batch-001-resolution.json`给出合并解释。原批次不覆盖；未抽样的16组仍是助手建议。

U32完整交叉复核包：[cross-review/v1](cross-review/v1/README.md)；[Claude操作说明](../../docs/handoff/mk-claude-cross-review.md)。包括全部候选与结构化附表，Codex既有判断单独放置；回传未审null不当作同意。
- 怕破坏英雄名单（推导层，U35）：`break-vulnerable-heroes-v1.json`，与“被动能否被破坏”（事实层）分开。
- **第2版证据（2026-11-01，U34）**：`vocabulary-v3.json`（写入U33/U35定义）、`src/dota_items/data/mechanics_rules_v2.py`、`mechanics_facts_v2.py`，输出`extractions/v2/`（`facts-v2.json`、`review.csv`、`delta-vs-v1.json`、`manifest.json`）。构建：`PYTHONPATH=src python scripts/build_mechanics_facts_v2.py --output <新目录>`。v1与其冻结包不变。
