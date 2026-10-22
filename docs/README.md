# 文档入口

2026-10-22整理：只维护三份流程／开发主文档；其余作为接口、手册、历史证据或学习材料。

## 三份主文档

| 目的 | 唯一入口 |
|---|---|
| 整体目标、两侧依赖及优先级 | [项目总开发路线](roadmap.md) |
| 来源、采集、筛选、标签、划分、交接及数据任务 | [数据流程与开发](data-prep-progress.md) |
| 输入、训练、评估、诊断、结论及模型任务 | [模型流程与开发](model-foundation.md) |

## 按需参考（不另维护路线）

- 协作／结构：[并行协议](handoff/parallel-development.md)、[单目录](handoff/single-workspace-2026-10-16.md)、[模块维护](modular-maintenance.md)。
- 接口：[公共读取](public-source-reader.md)、[任务契约](task-contracts.md)、[数据交接](handoff/purchase-data-interface.md)。
- 数据证据：[随机v2](random-cohort-v2-2026-10-21.md)、[整局11装备](whole-log-task-2026-10-21.md)。
- 模型证据：[固定基线](whole-log-baseline-2026-10-21.md)、[校准诊断](whole-log-calibration-2026-10-21.md)。
- 操作／质量：[工作流](workflow.md)、[教练命令](coach-workflow.md)、[推荐评审](recommendation-quality-review.md)、[验证记录](validation-and-delivery.md)。
- 学习：[个人任务](../learning/docs/roadmap.md)、[基线练习](../learning/docs/whole-log-baseline-lab.md)、[诊断练习](../learning/docs/calibration-lab.md)。
- 历史：[原文快照与哈希](archive/2026-10-22/INDEX.md)、[原完整索引](archive/2026-10-22/README.md)。其他按日期文档保留，不把旧“当前／下一步”当新指令。

## 更新规则

数据流程、决策和DATA任务只改数据主文档；模型流程、决策和MODEL任务只改模型主文档；跨侧出口及产品优先级只改总路线。
长实验日志和验收可另存并引用，不再新增按日期的开发路线。历史文档不删除；数据、模型和reports不因整理改写。

- [整局实验层维护](experiment-maintenance.md)：当前／历史CLI、模块API、兼容与结构整理验收。

- [两组C真实对照](whole-log-regularization-2026-10-22.md)：固定正则化结果、逐装备诊断与只读复验证据。

- 录像证据：[试点](replay-pilot-2026-10-22.md)、[兼容解析](replay-pilot-compat-results-2026-10-22.md)、[语义](replay-semantics-2026-10-22.md)、[实体/地标](replay-identity-2026-10-22.md)、[突跳事件](replay-jump-events-2026-10-23.md)。仅限定离线审计，不代表训练准入。
- [2026-10-23近期交付摘要](recent-progress-2026-10-23.md)：本轮已完成事项与交付范围；持续路线仍以上述三份主文档为准。
