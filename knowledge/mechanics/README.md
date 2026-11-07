# 机制知识框架（U26；U27扩为完整版，里程碑MK）

三层结构，每层只依赖下层；设计与状态见[知识框架说明](../../docs/knowledge-framework.md)。

| 层 | 文件 | 状态 |
|---|---|---|
| 1 事实层：官方原始枚举的含义 | `enums-v1.json` | 已经用户确认（U30，MK-T2完成） |
| 1 事实层：机制词表 | `vocabulary-v13.json`（v1–v12保留） | 83项，定义来自用户决定，措辞由助手整理 |
| 1 事实层：复核后事实 | `extractions/v20/`（v1–v19保留） | MK-T3已结束（U67），`basis`标明依据 |
| 2 机制规则层：机制交互与克制 | `rules-v11.json`，结果在`extractions/v20/rules-evaluation.json` | 23条（U73结束T4，U94拆出R21，U97加R22，U100拆出R23），第8、12、13、15条的细节到T5 |
| 3 推导层：英雄/装备机制档案、克制图、英雄特性v3 | `profiles/derived-v11/` | 草稿；U5抽查已结束，R8、R15等B1数据 |

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

## 当前数据流（2026-11-06，U92–U113）

```
来源快照（Valve说明、游戏文件） → 候选 → AI审查＋用户裁定 → 事实v20
事实v20 ＋ 词表v13 ＋ 规则v11 → rules-evaluation（来源集合、目标集合）
                                → 派生层derived-v11（档案、克制关系候选）
```

读这些数据时要知道：

- **`basis`**：`user*`、`field`算确认；`two_ai`只是AI一致；`disputed_by_user`是用户标了错、还没裁定，不算确认，原来是用户裁定或字段也一样。
- **`user_feedback`**：抽查的标记和原话。行已不存在的反馈放在`unattached_feedback`，不丢。
- **`condition_notes`**：AI写的条件说明，只供阅读，不能用于自动推理。`condition_review=none`只表示没有说明，不代表无条件。结构化的只有`condition`（基础、A杖、魔晶、装备）。
- **克制关系是候选**：`rules-evaluation`和`counter-graph`只算集合，没有逐对核对条件和例外，`semantics`字段写明了这一点。每条边带`relation`和`status`（`candidate`或`pending`）。程序读边要用`data.mechanics_graph_v2.usable_edges`，查英雄之间的关系用`hero_relations`，两者默认不含待定规则，可读当前的`/3`图谱（带条件）和旧的`/2`图谱；`tests/test_mechanics_derived_v10.py`用当前图谱测试这两个接口。旧函数`mechanics_graph.edges_between`不带状态，目前只有旧测试在用，新代码不要用。
- **按英雄定目标**：规则v11的`target_heroes`（R12）列出例外英雄，`data.mechanics_rules_v8.expand_rules`展开成目标技能，展开结果在`extractions/v20/rules-expanded.json`。有条件的例外（如有A杖时）仍算目标，边上带`exception`。
- **反馈的身份**（U101）：每条反馈有`feedback_id`（由内容算出，重复导入不变），并记下反馈时这行声称什么（`claim`）。纠正记录用`resolves`写明解决哪几条反馈，见`reviews/feedback-resolutions-001.json`。没被写明解决的“错”一直是`disputed_by_user`；事实内容变了，旧的“对”不再算确认。每行的`feedback_status`写明原因。
- **装备档案的条件**（PR #17复核）：derived-v10起，装备档案每条关联带`target_conditions`（每个目标技能的条件）、`conditional_targets`和装备自己的`own_conditions`，页面列出“有条件的目标”，如林肯的巨浪“有A杖时不成立”（`data.mechanics_profiles_v4`）。
- **档案**（U101）：`hero-profiles.json`、`item-profiles.json`顶层写明`status=draft`、`relations=candidate`、`relation_verified=false`和来源版本。每条关联在`candidate_relations`里带`rule`、`relation`、`status`、`pending`、`not_evaluated`、对象编号；`own_facts_confirmed`只说事实，不说关联成立。页面标题改为“候选机制关联”，标签由`status`生成，不读中文规则名。
- **生效条件**（U104）：`rules-evaluation.json`的`source_conditions`、`target_conditions`给每个对象列出`when`（基础、A杖、魔晶、装备，或规则直接列出的`any`）和`unless`（哪种升级会让它不成立）。`unless`只来自事实的`condition_exceptions`和规则的条件例外，不从被排除的升级行推断。关联边带`conditional`和逐个技能的条件；`data.mechanics_conditions.edge_holds(edge, upgrades)`按已知升级返回成立、不成立或说不准（`None`）。
- **没算的规则字段**（MK-T6b，U113）：`pairs`、`target_exempt_mechanisms`、`parameters`不参与计算。规则v11必须在`not_computed`里写明字段、原因和用户决定，否则读取报错；程序不认识的字段也报错（`data.mechanics_rules_v11`）。目前只有R08、R09、R19这样声明，求值结果带`not_computed`和`not_evaluated`。
- **校验**：`manifest.json`记录数据输入（v18直接读冻结的v17，测试追踪真实读取）和导入到的全部仓库源码（测试沿导入关系检查）；数据和源码都在构建前后比对，中途变化或文件被删就报错。

**统一入口（MK-T6，U113）：`current.json`列出当前每份知识文件的路径和SHA-256。新代码用`dota_items.data.mechanics_current.read_current(名字)`读取；文件被改动、缺失或和构建manifest对不上都会报错。升版本时：生成并提交新版本文件 → 改`scripts/build_mechanics_current.py`里的列表 → 重新运行 → 同步文档；`tests/test_mechanics_current.py`会检查入口是否指向最新版本。**

- **数值升级的来源**（MK-T6c，U113）：`numeric_upgrades`每组带`ruling`：用户逐条裁定（U65、U66、U72，指向`reviews/user-rulings-001.jsonl`）或U65冷却规则。

- **版本核对**（MK-T6d，U99、U113）：2026-11-06核对当前知识与7.41f一致，结论和局限见`reviews/patch-check-001/README.md`；`current.json`的`patch.verified=true`。冻结事实包里的`patch_verified=false`不改。

- **补丁更新流程**（MK-T6e）：见`docs/mechanics-patch-update.md`；脚本`scripts/patch_update.py`（`status`、`item-diff`、`game-diff`、`impact`），试跑见`reviews/patch-update-dryrun-001/`。

- **被取代的旧知识**（MK-T6f）：登记在`knowledge/superseded.json`——各版本族里比`current.json`旧的版本自动算被取代，另有英雄特性v1、阵容规则包7.41f-v1、早期档案目录逐项列出（含谁还在读、为什么被取代）。`data.knowledge_superseded.superseded_status(路径)`可查；测试保证当前入口不会指向被取代的文件。旧版本目录的README顶部加了提示，冻结文件本身不改。

MK-T6还要做：文档与学习笔记收尾（并出事实下一版吸收U114）。

**当前入口：`current.json`（U113），即`extractions/v20/`、`vocabulary-v13.json`和`rules-v11.json`；派生层`profiles/derived-v11/`（草稿）。补漏见`reviews/full-audit-001/`、`full-audit-002/`，第1–8轮复查见`full-audit-003/`，控制分类重读见`full-audit-004/`，对照见`reviews/recall-check-002/`。**

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
