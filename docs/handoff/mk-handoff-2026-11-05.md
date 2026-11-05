# MK交接（2026-11-05）

取代[2026-11-01交接](mk-handoff-2026-11-01.md)的当前状态部分。

## 现状

- MK-T3已结束（U67）。入口：`knowledge/mechanics/extractions/v12/`、`vocabulary-v11.json`（81项）。
- MK-T4已结束（U73）：`knowledge/mechanics/rules-v5.json`（20条），计算结果`extractions/v12/rules-evaluation.json`，讨论过程[规则草稿](mk-t4-rules-draft.md)。
- 全部裁定在`knowledge/mechanics/reviews/user-rulings-001.jsonl`，汇总见[待用户裁定汇总](user-rulings-2026-11-02.md)。

## 下一步

1. 第20条已改为范围伤害（U71、U72），入口更新为`extractions/v8/`、`vocabulary-v8.json`、`rules-v2.json`。
2. MK-T4已结束（U73），当前任务MK-T5：英雄档案、装备档案、克制关系图、英雄特性v2已生成（`profiles/derived-v2/`，草稿）。全量补漏和第1–8轮复查已完成（U81–U89），下一步U5抽查。
3. MK-T5要解决：第12条“脆弱”的判断、第13条例外清单、第15条依赖普攻（读M1出装，一号位默认算）、第8条“常规会出”的门槛；并按U5抽查。
4. 新事实缺口出新版本，不改旧版本。

## 留到MK-T5抽查的风险

- `basis=two_ai`的组不算用户确认，可能错在同一处。
- 新增机制的证据靠关键词和字段找，已发现过清莲宝珠、黑皇杖、回光返照、末日的漏记。
- 未审：幻象字段19个；只在A杖、魔晶或天赋下生效的56个；升级规则其余93组没逐组看。
- 中立物品24组在`deferred_rows`，退出装备57组在`retired_rows`，都不算正式结果。

## 已知漏记

- 幻象：第4轮跳过的候选已由U80补入v10。恐怖利刃·倒影无敌，已从第20条目标排除（U81）。
- 全面漏记：见`knowledge/mechanics/reviews/recall-check-001/`。官方说明不用关键词的技能大量没有记录（莱恩·妖术、风暴之灵·球状闪电、自然先知·自然的呼唤等）。

## 工作方式

- Codex：`codex exec --sandbox read-only --skip-git-repo-check --ephemeral -C <空目录> --output-schema schema.json -o out.json -`，提示词走标准输入；输入不含Claude判断。每轮目录见`knowledge/mechanics/reviews/codex-round-00*/`。
- 给用户的问题写成具体的是非题，“按建议”这种说法用户看不懂时要展开。
- 不操作用户电脑打开Dota 2；用户的游戏知识记`user_reported`。
- `user-rulings-001.jsonl`变化后，只有最新版本能重放，旧版本校验冻结哈希。
