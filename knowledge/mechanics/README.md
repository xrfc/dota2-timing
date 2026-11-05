# 机制知识框架（U26；U27扩为完整版，里程碑MK）

三层结构，每层只依赖下层；设计与状态见[知识框架说明](../../docs/knowledge-framework.md)。

| 层 | 文件 | 状态 |
|---|---|---|
| 1 事实层：官方原始枚举的含义 | `enums-v1.json` | 已经用户确认（U30，MK-T2完成） |
| 1 事实层：机制词表 | `vocabulary-v9.json`（v1–v8保留） | 76项，定义来自用户决定，措辞由助手整理 |
| 1 事实层：复核后事实 | `extractions/v10/`（v1–v9保留） | MK-T3已结束（U67），`basis`标明依据 |
| 2 机制规则层：机制交互与克制 | `rules-v5.json`，结果在`extractions/v12/rules-evaluation.json` | 20条（U73结束T4），第8、12、13、15条的细节到T5 |
| 3 推导层：英雄/装备机制档案、克制图、hero-traits v2 | `profiles/derived-v2/` | MK-T5进行中，草稿已生成，待U5抽查 |

- 读取一律用`dota_items.data.mechanics.load_enums(doc, registry_heroes)`与`load_vocabulary(doc, enums)`：每个例子技能必须存在且取值一致；登记表中出现的取值必须全部有解释，补丁更新出现新取值时直接报错。
- 修改须记决策并升版本（v2…），旧版本不覆盖。

**当前入口：`extractions/v12/`、`vocabulary-v11.json`和`rules-v5.json`（U83、U85–U89）；派生层`profiles/derived-v2/`（草稿）。补漏见`reviews/full-audit-001/`、`full-audit-002/`，第1–8轮复查见`full-audit-003/`，控制分类重读见`full-audit-004/`，对照见`reviews/recall-check-002/`。**

“可被破坏”与游戏文件的对照见[破坏对照](reviews/break-check-001/README.md)（U46，U47已裁定）；其他机制见[排查报告](reviews/game-files-audit-001/README.md)（U48）；退出装备标记见`retired-items-v1.json`（U51）。

MK-T3接口、来源限制、复现命令与抽查入口见[机制事实说明](../../docs/mechanics-facts.md)。v1包含全部734个技能和209个装备清单候选；原文匹配均待复核，不能直接当作机制规则。

语义复核建议独立放在`reviews/`；首批24组说明与8组抽查见[复核入口](../../docs/mechanics-review.md)。`assistant_decision`与`user_decision`分开，未回复保持null，不能当作用户已同意。

U31的最新四条例子见`reviews/targeting-examples-v2.json`（旧v1保留）：目标方式、林肯响应、莲花响应分别有value/status/evidence；null表示未知，不是false。这里只记录说明例子，不作为MK-T4可执行规则。

用户反馈独立保存：`reviews/batch-001-feedback-001.json`记录抽查3/7/8；魂断的两项交互在例子v2中标为`user_reported`，与`snapshot_supported`区分。

批次001的8条用户抽查已全部反馈；`batch-001-feedback-002.json`记录剩余5条确认，`batch-001-resolution.json`给出合并解释。原批次不覆盖；未抽样的16组仍是助手建议。

U32完整交叉复核包：[cross-review/v1](cross-review/v1/README.md)；[Claude操作说明](../../docs/handoff/mk-claude-cross-review.md)。包括全部候选与结构化附表，Codex既有判断单独放置；回传未审null不当作同意。
- 怕破坏英雄名单（推导层，U35）：`break-vulnerable-heroes-v1.json`，与“被动能否被破坏”（事实层）分开。
- **第2版证据（2026-11-01，U34）**：`vocabulary-v3.json`（写入U33/U35定义）、`src/dota_items/data/mechanics_rules_v2.py`、`mechanics_facts_v2.py`，输出`extractions/v2/`（`facts-v2.json`、`review.csv`、`delta-vs-v1.json`、`manifest.json`）。构建：`PYTHONPATH=src python scripts/build_mechanics_facts_v2.py --output <新目录>`。v1与其冻结包不变。
