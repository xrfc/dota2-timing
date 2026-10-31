# 文档索引

**当前执行计划：[开发全流程计划 M0–M6](development-plan-2026-10-30.md)；[决策记录](decisions/README.md)。**


> 2026-10-27目标同步：当前产品主线是根据位置与当时可用装备，解释什么时候注意地图、保守或激进走位。开发顺序与阶段出口唯一维护在[总路线](roadmap.md)；[数据](data-prep-progress.md)§19、[模型](model-foundation.md)§13分别负责证据与学习流程。回放器是工具，不是最终决策交付。日期证据、冻结协议和归档不因目标调整而重写。

更新：2026-10-28。流程与当前任务只维护三份主文档：**总路线、数据、模型**；其他文档是接口/操作参考、日期证据或历史快照，不另设竞争路线。

新读者：[项目简介](../README.md) → [总路线](roadmap.md) → [数据](data-prep-progress.md)/[模型](model-foundation.md)。开发者另读[贡献指南](../CONTRIBUTING.md)、[模块维护](modular-maintenance.md)、[脚本导航](../scripts/README.md)。

## 如何理解状态与链接

- 日期报告中的“本轮/未推送/待确认”只对其记录时刻有效，当前状态查主文档；训练、推送、合并分别记录。
- `data/`、`reports/`、`coach-workspace/`链接指本地冻结证据，GitHub不分发这些文件。公开文档含汇总与复现条件，不声称干净克隆拥有原始数据/模型。
- `archive/`原文快照保持字节与哈希，内部旧相对链接按原位置解释。只从下方索引进入，不批量修改历史授权/数值。
- 学习材料见[learning](../learning/README.md)，知识来源维护见[knowledge维护](knowledge-maintenance.md)；不自动勾选个人任务。
- 本目录全部非归档Markdown均列在下方；归档原文由各INDEX及manifest管理。无物理搬迁，旧链接继续兼容。

## 主流程与导航

- [数据流程与开发](data-prep-progress.md)
- [模型流程与开发](model-foundation.md)
- [项目状态入口](project-status.md)
- [项目总开发路线](roadmap.md)

## 架构、接口与操作

- [Git结构与已合并分支清理（2026-10-30）](git-maintenance-2026-10-30.md)

- [架构与分步任务审查（2026-10-28）](architecture-review-2026-10-28.md)
- [蓝量独立修复与证据边界](decision-mana-repair-2026-10-28.md)
- [R1：修复蓝量接入新版本评审包（8770）](decision-mana-integration-2026-10-30.md)
- [数据质量与X/y学习练习](data-quality-ml-lab-2026-10-28.md)

- [教练任务字段核查：视野、装备、技能与战斗](coach-field-audit.md)
- [教练工作流：训练前后基础设施（v0.3）](coach-workflow.md)
- [数据与模型接口契约](data-contracts.md)
- [Demo 到训练样本的数据管线](data-pipeline.md)
- [主宰位置与装备标签语义核验](data-semantics.md)
- [工程设计：阵容推荐与回放基础设施](engineering-design.md)
- [整局实验层维护（2026-10-22）](experiment-maintenance.md)
- [英雄知识能否作为训练冷启动？](knowledge-cold-start.md)
- [知识维护、路径映射与证据恢复](knowledge-maintenance.md)
- [机制知识框架（U26）：事实层→机制规则层→推导层](knowledge-framework.md)
- [长期产品目标：赛前准备与赛后复盘教练](long-term-coach-goals.md)
- [技术选型与优化路线](long-term-roadmap.md)
- [单模块维护与长期扩展（2026-10-17）](modular-maintenance.md)
- [工程风险复核](project-review.md)
- [公共来源读取接口与生产者迁移（2026-10-17）](public-source-reader.md)
- [购买日志观测契约 v1](purchase-observation-contract.md)
- [7.41f 阵容推荐契约（M01 首个切片）](recommendation-contracts.md)
- [版本化任务契约（2026-10-20）](task-contracts.md)
- [训练准入与桌面核验交接](training-admission.md)
- [验证与交付：完成标准与历史验收](validation-and-delivery.md#工程交付完成标准)
- [日常操作、迁移与恢复](workflow.md)

## 录像、地图与观察证据

- [本地地图回放器：启动、交互、事件证据现状与验证边界](replay-viewer.md)

- [地图资料获取与地标对照（2026-10-26）](map-reference-2026-10-26.md)
- [视野、战斗与英雄状态接入](observer-context.md)
- [位置与可见性数据扩量（2026-10-26）](replay-expansion-2026-10-26.md)
- [录像坐标直接实体来源与原生地标（2026-10-22）](replay-identity-2026-10-22.md)
- [三场突跳与技能、物品、复活事件核对（2026-10-23）](replay-jump-events-2026-10-23.md)
- [原始录像轨迹与视野试点（2026-10-22）](replay-pilot-2026-10-22.md)
- [原始录像兼容修复与轨迹、视野续报（2026-10-22）](replay-pilot-compat-results-2026-10-22.md)
- [录像质量补齐、地图校准与阵营时间线（2026-10-26）](replay-quality-2026-10-26.md)
- [三场录像语义审计（2026-10-22）](replay-semantics-2026-10-22.md)

## 模型、阵容与实验记录

- [2026-10-13 推荐报告内部审查](acceptance/recommendation-review-2026-10-13.md)
- [主宰阵容分析原型（2026-10-25）](lineup-analysis-prototype-2026-10-25.md)
- [主宰A/B阵容对比：功能与案例复盘](lineup-comparison-review-2026-10-25.md)
- [本地阵容推荐：一号位主宰](lineup-recommendation.md)
- [首个机器学习实验：先证明数据能支持任务](ml-first-experiment.md)
- [首轮源购买日志机器学习基线（2026-10-15）](purchase-log-baseline-2026-10-15.md)
- [购买日志基线：验证集误差与分布诊断（2026-10-15）](purchase-log-diagnostics-2026-10-15.md)
- [日志观测建模快照与玩家分组评估](purchase-log-modeling-snapshot.md)
- [截距与正则化对照：实现已完成，真实实验待确认](purchase-log-sensitivity-plan-2026-10-15.md)
- [推荐质量评审：从可运行到建议合理](recommendation-quality-review.md)
- [整局11装备：固定频率与阵容逻辑回归对照](whole-log-baseline-2026-10-21.md)
- [整局固定预测：校准与训练/验证差距诊断](whole-log-calibration-2026-10-21.md)
- [整局两组C真实对照（2026-10-22）](whole-log-regularization-2026-10-22.md)
- [开局阵容 → 整局11装备源日志任务（2026-10-21）](whole-log-task-2026-10-21.md)

## 采集、资格与独立评估

- [双方向架构审查（2026-10-16）](architecture-2026-10-16.md)
- [代码审查修复与复审（2026-10-18）](code-review-fixes-2026-10-18.md)
- [队列v2整组划分可行性：实际分析](cohort-v2-feasibility-2026-10-18.md)
- [1,000场购买行为候选采集任务](collection-1000-2026-10-14.md)
- [新增1,000场候选采集（2026-10-15）](collection-additional-1000-2026-10-15.md)
- [下一批主宰采集准备（2026-10-19，未启动网络采集）](collection-next-batch-plan-2026-10-19.md)
- [主宰购买标签可行性审计](data-feasibility.md)
- [数据脚本审查修复（2026-10-20）](data-review-fixes-2026-10-20.md)
- [前瞻独立评估：已确认执行参数（保留设计理由）](evaluation-execution-proposal-2026-10-23.md)
- [独立评估离线可行性与采集400排查（2026-10-23）](evaluation-feasibility-2026-10-23.md)
- [独立评估来源小预算复测（2026-10-23）](evaluation-source-probe-2026-10-23.md)
- [开发分支同步检查（2026-10-20）](github-sync-2026-10-20.md)
- [较晚同补丁评估：研究口径设计（DATA-02 / MODEL-07）](independent-evaluation-design-2026-10-23.md)
- [训练前数据准备与阻塞清单](pretraining-readiness.md)
- [现有952场离线处理](purchase-952-processing-2026-10-14.md)
- [新队列 v2 接入方案（2026-10-18，待研究选择确认）](purchase-cohort-v2-plan-2026-10-18.md)
- [v2 比赛级随机划分与模型输入（2026-10-21）](random-cohort-v2-2026-10-21.md)
- [真实回放采集与准入](real-data-acceptance.md)
- [近期开发进度与交付摘要（截至2026-10-23）](recent-progress-2026-10-23.md)

## 协作与交接

- [双分支交接：对话上下文与共同协议（2026-10-16）](handoff/2026-10-16-context.md)
- [数据准备agent提示词](handoff/data-agent-prompt.md)
- [模型搭建agent提示词](handoff/model-agent-prompt.md)
- [并行开发与串行集成协议](handoff/parallel-development.md)
- [AI临时分支契约（U25）](handoff/ai-temp-branch-contract.md)
- [数据接口交接（2026-10-16）](handoff/purchase-data-interface.md)
- [单目录整合与模型agent接续（2026-10-16）](handoff/single-workspace-2026-10-16.md)

## 历史快照索引

- [整理前原文快照（2026-10-22）](archive/2026-10-22/INDEX.md)
- [2026-10-26整理前入口](archive/2026-10-26/INDEX.md)

## 2026-10-27数据侧交付证据

- [决策时点证据与五个复盘案例](data-decision-cases-2026-10-27.md)：操作、数据边界、专项与待评审案例；不另设开发路线。

- [决策字段可用性清单与增强两例](decision-field-readiness-2026-10-27.md)：两场来源审查、当前缺口、证据与8769操作入口。
- [决策学习任务草案（待确认）](decision-training-task-draft-2026-10-27.md)：候选行动可接受性建议、替代任务、标注/划分/指标未决项；不注册task_id。

- [决策状态卡：血蓝、技能CD与TP取证](decision-state-card-2026-10-27.md)：最新独立探针、真实两场结果、API/命令、mana限制、旧产物保护和验收入口；字段旧表须结合此增量阅读。

### 2026-10-27案例评审追补

案例1追加反馈与四项具体评审问题已纳入当前对照页，含最后可见22秒核对和未证实路线边界。 详见[对照包追加反馈](decision-comparison-2026-10-27.md)。

- [地图选中英雄与集中状态面板](decision-comparison-2026-10-27.md#地图选中英雄与集中状态面板2026-10-27)：8769交互、同刻状态连接、隐藏/历史隔离、现有字段边界与新UI验收。

## 历史设计归档（不替代当前入口）

- [2026-10-10阵容推荐规划](development-mainline.md)：历史范围与设计理由。
- [2026-10-10模块边界](module-boundaries.md)：保留依赖方向与扩展原则，不把建议目录当成当前结构。
- [2026-10-10文档盘点](documentation-inventory.md)：当时的清单与核对范围，不是当前文件数量。

当前已存在 recommendation 契约/规则原型、modeling 模型接口与阵容页面；实现存在不等于推荐质量或真实语义认证。状态继续由 roadmap、data-prep-progress、model-foundation 维护，结构见 modular-maintenance；此归档不扩大训练或数据用途授权。
