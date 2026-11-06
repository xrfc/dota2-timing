# MK交接（2026-11-05）

取代[2026-11-01交接](mk-handoff-2026-11-01.md)的当前状态部分。

## 现状

- MK-T3已结束（U67）。入口：`knowledge/mechanics/extractions/v18/`、`vocabulary-v13.json`（83项）。怎么读这些数据见`knowledge/mechanics/README.md`“当前数据流”。
- MK-T4已结束（U73）：`knowledge/mechanics/rules-v10.json`（23条），计算结果`extractions/v18/rules-evaluation.json`，讨论过程[规则草稿](mk-t4-rules-draft.md)。
- 全部裁定在`knowledge/mechanics/reviews/user-rulings-001.jsonl`，汇总见[待用户裁定汇总](user-rulings-2026-11-02.md)。

## 下一步

1. 第20条已改为范围伤害（U71、U72）。当前入口见上。
2. MK-T4已结束（U73），当前任务MK-T5：英雄档案、装备档案、克制关系图、英雄特性v2已生成（`profiles/derived-v8/`，草稿）。全量补漏和第1–8轮复查已完成（U81–U89），U5抽查第二轮进行中：`knowledge/mechanics/reviews/u5-spot-check-002/`，用户标完后读回页面`verdicts`再写入事实。
3. R12、R13已定，单体指向已筛查（U100–U103）。MK-T5还要解决（英雄特性已定，U105–U107；R8、R15不用M1（只有主宰对局），已授权重新无差别采集超凡以上对局，试采100场仅11场有购买记录，是否请求解析待定，U109–U111）：第12条“脆弱”的判断、第13条例外清单、第15条依赖普攻（一号位默认算，出装数据待重新采集）、第8条“常规会出”的门槛；并按U5抽查。
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
