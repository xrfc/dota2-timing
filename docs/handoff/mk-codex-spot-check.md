# 交接：请Codex完成MK-T3的U5抽查剩余387组（U42）

用户已抽查93组（对85、不确定5、错3），决定剩余部分交给Codex（[U42](../decisions/2026-11-02-spot-check-to-codex.md)）。这是AI交叉复核，结果与用户抽查分开记录。

## 1. 先读

1. `AGENTS.md`；[开发计划](../development-plan-2026-10-30.md)§2（U28–U42）与§7。
2. Claude第1轮方法与局限：`knowledge/mechanics/reviews/claude-round-001/review-summary.md`。
3. 之后的改判：[第4轮](../../knowledge/mechanics/reviews/claude-round-004/README.md)（U40）、[第5轮](../../knowledge/mechanics/reviews/claude-round-005/README.md)（U41）。
4. 你自己的第2轮：`knowledge/mechanics/reviews/codex-round-002/README.md`（方法沿用）。

## 2. 复核对象

- `knowledge/mechanics/reviews/u5-spot-check/codex-queue.json`的387组。`current_decision`是当前结论（接受386、排除1），复核以它为准，而不是第1轮原始标签。
- 每组的完整证据、fact_id与原文指针在`knowledge/mechanics/cross-review/v1/cases.jsonl`（第2版新增14组在`knowledge/mechanics/extractions/v2/`）。
- 主要机制：减速60、单体指向51、治疗/回复36、眩晕30、受破坏影响23、自身位移14、自身回蓝/吸蓝14、施加弱驱散13，其余较少。

## 3. 重点

- **读完整原文**，不要只读截断片段（利维坦的渔获、热血竞技场都是这样错的）。完整文本：`knowledge/hero-capabilities/hero-registry.json`或`knowledge/items/sources/dotaconstants-items.json`。
- 已有两类错误：截断导致漏看；理由已引用关键句但结论判错。两类分开统计。
- 已失效A杖/魔晶文字按`knowledge/mechanics/stale-upgrade-text-v1.json`处理。
- 先天能否被破坏：U40的9个与U41的24个不能被破坏；10个按官方原文；其余战斗类按U33可被破坏。不要以记忆推翻用户决定。
- 用户的定义（U28、U31、U33、U35、U40）优先；与之冲突的标`needs_user_ruling`，不要自行覆盖。

## 4. 回传

- 在`codex-temp`工作（U25），从最新main开始；结果写新目录`knowledge/mechanics/reviews/codex-round-003/`。
- 每组：`review_id`、Codex结论（accept/reject/uncertain）、解释、条件、理由、引用的fact_id、与`current_decision`是否一致、不一致原因、是否需用户裁定。
- README写清：一致率（只对这387组）、两类错误各多少、需用户裁定清单。不要和用户的93组抽查合并成一个一致率。
- 不授权合并、推送main、训练或联网采集。

## 5. 给Codex的提示词（用户可直接粘贴）

> 请完成MK-T3的U5抽查剩余387组（U42，AI交叉复核）。先读`docs/handoff/mk-codex-spot-check.md`和`AGENTS.md`；队列在`knowledge/mechanics/reviews/u5-spot-check/codex-queue.json`，以其中`current_decision`为准。逐组读完整原文，结果写到`knowledge/mechanics/reviews/codex-round-003/`，在`codex-temp`分支提交并开PR，不要合并。
