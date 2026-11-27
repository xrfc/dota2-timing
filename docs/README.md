# 文档索引

最新补证：[树身份与临时视野协议成员](viewer-wire-and-tree-identity.md)。

近期开发全景：[阶段总结与架构复核（2026-11-27）](development-review-2026-11-27.md)。

当前7.42原始字段补证：[树事件、树索引与视距来源](patch-tree-probe.md) · [本轮授权](decisions/2026-11-27-tree-probe.md)。

当前7.42机制消费：[工程证据准入与保守派生](mechanics-evidence-admission.md) · [本轮授权范围](decisions/2026-11-27-mechanics-evidence-admission.md)。

当前7.42时点消费与验证：[决策时可知证据](patch-decision-evidence.md) · [机制工程补证](patch742-engineering-evidence-followup.md) · [本轮授权](decisions/2026-11-27-decision-evidence.md)。

本轮7.42补证与复现：[营地、目标复活及视野证据](patch-evidence-followup.md) · [已执行的长局采集方案](patch742-evidence-collection-plan.md)。

2026-11-27续：[7.42候选行动资产](patch-review-assets.md)（营地、动态目标、地形/视野、机制派生） · [机制待决清单](patch742-open-decisions.md)。

[行动比较框架](decision-framework.md) · [带线决策复核记录](lane-decision-audit.md)


[一号位兵线意识复盘与取样口径](lane-decision-review.md)

**先看[当前状态](current-status.md)**：做完了什么、正在跑什么、接下来做什么（2026-11-27）。

**从这里开始**：[开发计划](development-plan-2026-10-30.md)（唯一进度：§7）· [架构](architecture.md) · [决策记录](decisions/README.md) · [变更记录](../CHANGELOG.md)

更新：2026-11-01（U37双线重构）。项目分为**共享底座**、**路线A 推荐**（阵容、出装、针对装、对线；比赛级机器学习）和**路线B 意识决策**（防被抓、参团、集合抓人；当时可知的录像证据）。A线当前暂停，B线当前推进一号位行动复盘；旧阶段选型只作参考。下面按这三部分组织；每个主题只有一个当前入口，其余是接口参考、日期证据或历史。

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
| [路线变更总览](route-changes.md) | 一页看清方向改过哪几次、为什么改、被替代的是什么（每行指向决策记录） |
| [长期产品目标](long-term-coach-goals.md) | 只做赛前/赛后、不做实时辅助；复盘信息边界原则（历史依据，仍有效） |
| [单模块维护](modular-maintenance.md) | 各层API细节、10/17–10/28结构整理记录（入口职责已移到架构页） |
| [技术选型与优化路线](long-term-roadmap.md) | 历史技术参考 |
| [总路线R0–R4](roadmap.md)、[项目状态入口](project-status.md) | 已被开发计划替代，保留历史导航 |
| [工程风险复核](project-review.md) | 后见之明、隐藏信息泄漏等风险清单 |

## 2. 共享底座

- [7.42地图与机制候选绑定](patch-asset-binding.md)：来源、能力矩阵、接口、实测和未决项。

### 2.1 MK机制知识（初版完成，补丁维护中）

- [机制知识框架](knowledge-framework.md)：事实层→规则层→推导层设计（U26/U27）
- [MK-T3机制事实：接口、复现与抽查](mechanics-facts.md)
- [解析器v3设计](parser-v3-design.md)：从demo补全每秒状态（技能和物品冷却、单位状态原始掩码、战斗属性、地图大局、兵线），已实现（U130，2026-11-09）
- [对游戏的理解还缺什么](game-understanding-gaps.md)：上网查加自己数据核对后的缺口清单——视野、定时目标、肉山换坑、野点升级、传送和扫描等，按影响排序（2026-11-13，只是清单）
- [地图知识设计](map-knowledge-design.md)：地图快照、静态路径及观察者区域组合已实现；战术区域语义、动态规则和完整FOW仍待验收，旧草案按顶部更新阅读。
- [B0“被抓”规则](b0-gank-rules.md)：U115、U116、U131写成的可执行规则——流程、保命手段清单、三个阈值、第一轮结果（162场），2D回放抽查页和开雾指标（§9，U136），待用户抽查实例后冻结（2026-11-10）
- [自动采集demo](demo-collection.md)：自己启动的全量demo采集脚本，怎么跑、看进度、续跑、补采（U128、U129）
- [知识读取接口](knowledge-api.md)：路线A、B读取机制知识的统一方式和固定含义（U124）
- [M2b主宰针对装：触发条件与数据验证](m2b-triggers.md)：用户定的触发条件（U123）和在M1训练集上的验证（M2b-T6d、T8）
- [机制知识库：补丁更新流程](mechanics-patch-update.md)：新补丁出来后怎么找变化、复核、出新版本（MK-T6e）
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

### 3.1 既有里程碑产物（M1–M2b；路线A暂停）

- [M1数据卡：多英雄比赛级数据表](m1-data-card.md)
- [模型卡：死亡风险基线和死亡代价（路线B第一批模型）](b2-death-risk-baseline.md)
- [计划§7的历史记录（2026-11-16之前）](plan-history.md)
- [外部评估（2026-11-27）与处理](external-review-2026-11-17.md)
- [审查与修复：死亡风险模型（2026-11-18）](review-2026-11-18-death-risk.md)
- [7.42补丁预案](patch-7.42-plan.md)
- [用Workshop Tools导出7.42地图数据](map-workshop-export.md)：用户自己导出地图数据的步骤（上游未更新时用）
- [交接：7.42知识库更新与视野检验（2026-11-20）](handoff/patch-7.42-and-vision-2026-11-20.md)：交给Codex继续开发的入口
- [7.42影响清单](patch-7.42-impact.md)：7.42对机制知识库的影响，需要用户裁定的部分和AI已定的部分（2026-11-20）
- [路线B任务契约草稿：预测“接下来会不会死”（U160）](b2-death-risk-contract.md)
- [重训前清单：死亡风险模型（U170，会改表／只改评估／只改解释）](b2-retrain-checklist.md)
- [demo数据卡：多英雄demo采集的覆盖（段位、时长、1/5号位英雄）](demo-data-card.md)
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

- [行动判断总架构](decision-framework.md)：**当前产品设计入口**
- [路线B早期设计](awareness-track.md)：历史阶段与选型参考
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
- [待用户裁定汇总（2026-11-02）](handoff/user-rulings-2026-11-02.md)
- [词表v6新增机制草稿](handoff/vocabulary-v6-draft.md)
- [MK-T4规则草稿](handoff/mk-t4-rules-draft.md)
- [MK交接（2026-11-05）](handoff/mk-handoff-2026-11-05.md)
- [MK-T5英雄机制档案](../knowledge/mechanics/profiles/README.md)
- 历史交接：[双分支上下文（10-16）](handoff/2026-10-16-context.md) · [单目录整合（10-16）](handoff/single-workspace-2026-10-16.md) · [数据接口交接](handoff/purchase-data-interface.md) · [数据agent提示词](handoff/data-agent-prompt.md) · [模型agent提示词](handoff/model-agent-prompt.md)

## 6. 历史归档

- [历史阶段文档](archive/history/README.md)（2026-11-01起归档，含4份2026-10-10设计文档：[阵容推荐规划](archive/history/development-mainline.md)、[模块边界](archive/history/module-boundaries.md)、[文档盘点](archive/history/documentation-inventory.md)、[工程设计](archive/history/engineering-design.md)）
- [整理前原文快照（2026-10-22）](archive/2026-10-22/INDEX.md) · [2026-10-26整理前入口](archive/2026-10-26/INDEX.md)
- 其余10/13–10/28日期记录（采集、队列、录像试点、整局实验等）均在[历史阶段文档](archive/history/README.md)中列出。
