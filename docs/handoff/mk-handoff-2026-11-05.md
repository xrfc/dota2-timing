# MK交接（2026-11-05）

取代[2026-11-01交接](mk-handoff-2026-11-01.md)的当前状态部分。

## 现状

- MK-T3已结束（U67）。入口：`knowledge/mechanics/extractions/v7/`、`vocabulary-v7.json`（75项）。
- MK-T4规则第1版：`knowledge/mechanics/rules-v1.json`（20条），计算结果`extractions/v7/rules-evaluation.json`，讨论过程[规则草稿](mk-t4-rules-draft.md)。
- 全部裁定在`knowledge/mechanics/reviews/user-rulings-001.jsonl`，汇总见[待用户裁定汇总](user-rulings-2026-11-02.md)。

## 下一步

1. **问用户第20条哪些光环算克制幻象和召唤物。** 现在28个光环都没算进去，因为字段分不出加友军还是打敌方。助手建议只算对敌方造成伤害的，如辉耀、竭心光环。
2. 用户确认后结束MK-T4，进入MK-T5。
3. MK-T5要解决：第12条“脆弱”的判断、第13条例外清单、第15条依赖普攻（读M1出装，一号位默认算）、第8条“常规会出”的门槛；并按U5抽查。
4. 新事实缺口出新版本，不改旧版本。

## 留到MK-T5抽查的风险

- `basis=two_ai`的组不算用户确认，可能错在同一处。
- 新增机制的证据靠关键词和字段找，已发现过清莲宝珠、黑皇杖、回光返照、末日的漏记。
- 未审：幻象字段19个；只在A杖、魔晶或天赋下生效的56个；升级规则其余93组没逐组看。
- 中立物品24组在`deferred_rows`，退出装备57组在`retired_rows`，都不算正式结果。

## 工作方式

- Codex：`codex exec --sandbox read-only --skip-git-repo-check --ephemeral -C <空目录> --output-schema schema.json -o out.json -`，提示词走标准输入；输入不含Claude判断。每轮目录见`knowledge/mechanics/reviews/codex-round-00*/`。
- 给用户的问题写成具体的是非题，“按建议”这种说法用户看不懂时要展开。
- 不操作用户电脑打开Dota 2；用户的游戏知识记`user_reported`。
- `user-rulings-001.jsonl`变化后，只有最新版本能重放，旧版本校验冻结哈希。
