# 文档索引

**从这里开始**：[开发计划](development-plan-2026-10-30.md)（唯一进度：§7）· [架构](architecture.md) · [决策记录](decisions/README.md) · [变更记录](../CHANGELOG.md)

更新：2026-11-01（U37双线重构）。项目分为**共享底座**、**路线A 推荐**（阵容、出装、针对装、对线；比赛级机器学习）和**路线B 意识决策**（防被抓、参团、集合抓人；当时可知的录像证据）。下面按这三部分组织；每个主题只有一个当前入口，其余是接口参考、日期证据或历史。

## 如何读

- **状态只看计划§7。**其他文档里的“本轮／未推送／待确认”只对其记录日期有效。
- `data/`、`reports/`、`coach-workspace/`链接指本地冻结证据，不随Git分发；干净克隆打不开属于正常情况，不是文件丢失。
- `archive/`里是历史原文：只从下方入口进入，内部旧相对链接按原位置解释，不批量改写历史授权与数值。
- 本目录全部非归档Markdown都列在下方（`tests/test_docs_links.py`检查所有相对链接）。
- 新读者路线：[项目简介](../README.md) → [开发计划](development-plan-2026-10-30.md)§0–§1 → [架构](architecture.md) → 所在线的入口。开发者另读[贡献指南](../CONTRIBUTING.md)与[脚本导航](../scripts/README.md)。

## 1. 计划、架构与产品目标

| 文档 | 作用 |
|---|---|
| [开发计划](development-plan-2026-10-30.md) | **唯一执行计划**：双线里程碑、决策登记、待决问题、状态表 |
| [架构](architecture.md) | **当前架构入口**：层×线、模块归属、依赖规则、迁移策略 |
| [路线B设计](awareness-track.md) | 差异化分析、三类判断、四层设计、B0–B5、数据工程难点 |
| [决策记录](decisions/README.md) | U1起每条用户决定 |
| [长期产品目标](long-term-coach-goals.md) | 只做赛前/赛后、不做实时辅助；复盘信息边界原则（历史依据，仍有效） |
| [单模块维护](modular-maintenance.md) | 各层API细节、10/17–10/28结构整理记录（入口职责已移到架构页） |
| [技术选型与优化路线](long-term-roadmap.md) | 历史技术参考 |
| [总路线R0–R4](roadmap.md)、[项目状态入口](project-status.md) | 已被开发计划替代，保留历史导航 |
| [工程风险复核](project-review.md) | 后见之明、隐藏信息泄漏等风险清单 |

## 2. 共享底座

### 2.1 MK机制知识（当前进行中）

- [机制知识框架](knowledge-framework.md)：事实层→规则层→推导层设计（U26/U27）
- [MK-T3机制事实：接口、复现与抽查](mechanics-facts.md)
- [MK-T3语义复核：批次与判定方法](mechanics-review.md)
- [知识维护、路径映射与证据恢复](knowledge-maintenance.md)
- [英雄知识能否作为训练冷启动？](knowledge-cold-start.md)

### 2.2 来源、契约与数据管线

- [公共来源读取接口与生产者迁移](public-source-reader.md)
- [数据与模型接口契约](data-contracts.md)
- [版本化任务契约](task-contracts.md)
- [Demo到训练样本的数据管线](data-pipeline.md)
- [教练工作流：训练前后基础设施](coach-workflow.md)
- [真实回放采集与准入](real-data-acceptance.md)
- [训练准入与桌面核验交接](training-admission.md)
- [数据流程与开发（历史主文档）](data-prep-progress.md)、[模型流程与开发（历史主文档）](model-foundation.md)

### 2.3 工程、验收与日常操作

- [验证与交付：完成标准与历史验收](validation-and-delivery.md)
- [日常操作、迁移与恢复](workflow.md)
- [Git结构与已合并分支清理（2026-10-30）](git-maintenance-2026-10-30.md)
- [PR #7编码修复与审查记录（2026-10-29）](pr-review-2026-10-29.md)

## 3. 路线A：推荐（比赛级机器学习）

### 3.1 当前里程碑产物（M1–M2b）

- [M1数据卡：多英雄比赛级数据表](m1-data-card.md)
- [M2设计](m2-design.md) · [M2结果](m2-results.md) · [M2模型卡](m2-model-card.md)（出装时间预测，已结案U13）
- [M2b设计](m2b-design.md) · [M2b结果](m2b-results.md) · [M2b模型卡](m2b-model-card.md)（赛前针对装，暂停于T6c）
- [英雄特性初步分析（U23）](hero-traits-analysis.md)

### 3.2 阵容推荐原型与购买实验（历史，仅维护）

- [本地阵容推荐：一号位主宰](lineup-recommendation.md)
- [主宰A/B阵容对比：功能与案例复盘](lineup-comparison-review-2026-10-25.md)
- [7.41f阵容推荐契约](recommendation-contracts.md)
- [推荐质量评审](recommendation-quality-review.md) · [2026-10-13推荐报告内部审查](acceptance/recommendation-review-2026-10-13.md)
- [首个机器学习实验](ml-first-experiment.md)
- [整局实验层维护](experiment-maintenance.md)
- [日志观测建模快照与玩家分组评估](purchase-log-modeling-snapshot.md)
- [购买日志观测契约v1](purchase-observation-contract.md)
- [主宰购买标签可行性审计](data-feasibility.md)
- [主宰位置与装备标签语义核验](data-semantics.md)
- [训练前数据准备与阻塞清单](pretraining-readiness.md)
- [前瞻独立评估：已确认执行参数（已撤销）](evaluation-execution-proposal-2026-10-23.md)

## 4. 路线B：意识决策（录像证据）

- [路线B设计](awareness-track.md)：**当前入口**
- [录像质量补齐、地图校准与阵营时间线](replay-quality-2026-10-26.md)
- [视野、战斗与英雄状态接入](observer-context.md)
- [教练任务字段核查：视野、装备、技能与战斗](coach-field-audit.md)
- [本地地图回放器](replay-viewer.md)
- [决策时点证据与五个复盘案例](data-decision-cases-2026-10-27.md)
- [决策字段可用性清单与增强两例](decision-field-readiness-2026-10-27.md)
- [决策状态卡：血蓝、技能CD与TP取证](decision-state-card-2026-10-27.md)
- [支援vs刷钱：条件对照包与试标草稿](decision-comparison-2026-10-27.md)
- [R1：修复蓝量接入新版本评审包（8770）](decision-mana-integration-2026-10-30.md)
- [决策学习任务草案（B0参考）](archive/history/decision-training-task-draft-2026-10-27.md)

## 5. 协作与交接

- [AI临时分支契约（U25）](handoff/ai-temp-branch-contract.md)
- [并行开发与串行集成协议](handoff/parallel-development.md)
- [MK机制知识底座交接（2026-11-01）](handoff/mk-handoff-2026-11-01.md)
- [MK-T3交Claude全量交叉复核](handoff/mk-claude-cross-review.md)
- [请Codex复核Claude第1轮结果（可选）](handoff/mk-codex-review-of-claude.md)
- 历史交接：[双分支上下文（10-16）](handoff/2026-10-16-context.md) · [单目录整合（10-16）](handoff/single-workspace-2026-10-16.md) · [数据接口交接](handoff/purchase-data-interface.md) · [数据agent提示词](handoff/data-agent-prompt.md) · [模型agent提示词](handoff/model-agent-prompt.md)

## 6. 历史归档

- [历史阶段文档](archive/history/README.md)（2026-11-01起归档，含4份2026-10-10设计文档：[阵容推荐规划](archive/history/development-mainline.md)、[模块边界](archive/history/module-boundaries.md)、[文档盘点](archive/history/documentation-inventory.md)、[工程设计](archive/history/engineering-design.md)）
- [整理前原文快照（2026-10-22）](archive/2026-10-22/INDEX.md) · [2026-10-26整理前入口](archive/2026-10-26/INDEX.md)
- 其余10/13–10/28日期记录（采集、队列、录像试点、整局实验等）均在[历史阶段文档](archive/history/README.md)中列出。
