# U42 U5抽查剩余部分交给Codex

- 背景：U5规定判断类标注由助手先标、用户抽查约1/3。MK-T3第1轮抽了497组给用户（`knowledge/mechanics/reviews/claude-round-001/spot-check-sample.json`）。截至2026-11-02，用户标记93组：判对85、不确定5、判错3（直接一致率约91%，判错约3%）；判错与不确定的8组已在第1、2次回读中改判或解释，之后新增的17组标记全部为“对”，不需改判。
- 用户决定（2026-11-02）：**剩余抽查交给Codex做**，用户认为“分辨的差不多了”。
- 范围：497组去掉用户已标的93组、再去掉Codex第2轮P1已复核的17组，共**387组**（`knowledge/mechanics/reviews/u5-spot-check/codex-queue.json`；当前结论接受386、排除1）。
- 含义与局限（助手说明）：
  - 这387组从此是**AI交叉复核**，不是用户验证。机制事实的“用户抽查”只覆盖93组样本，报告时分开写“用户抽查一致率（93组）”和“Codex复核一致率（387组）”，不合并成一个数。
  - Codex与Claude同标签只说明两个AI一致；与用户既有决定冲突的项仍交用户裁定。
  - 这是对MK-T3这一处U5执行方式的调整，不改变U5本身对以后其他标注任务的要求。
- 用户标记快照：`knowledge/mechanics/reviews/u5-spot-check/user-verdicts-2026-11-02.json`。交接说明：`docs/handoff/mk-codex-spot-check.md`。
- 来源：2026-11-02用户消息“u5抽查可以给codex做吗，我觉得我分辨的差不多了”。
