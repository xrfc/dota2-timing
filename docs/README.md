# 文档索引

## 只读审查入口 — 2026-10-18

- [数据准备进度](data-prep-progress.md)：审计JSON转Markdown的API、CLI、拒绝策略和证据边界。
- [模型基础闭环](model-foundation.md)：只读inspect、支持数分母与历史实现指纹说明。
- [验证与交付](validation-and-delivery.md)：本轮串行验收和开发分支发布范围。

## 公共接口最新入口

[公共来源读取与生产者迁移](public-source-reader.md)说明public-reader/1收尾、严格默认校验和新交接目录；
[数据交接协议](handoff/purchase-data-interface.md)维护面向模型侧的接口。此前凌晨重构记录保留历史。


## 当前维护入口 — 2026-10-17

[单模块维护指南](modular-maintenance.md)维护当前架构、扩展接口、兼容边界和检查命令。
[模型基础闭环](model-foundation.md)、[交接协议](handoff/purchase-data-interface.md)维护对应语义；
[验证记录](validation-and-delivery.md)维护实际验收。下方10/16及更早进度为历史。

结构入口同步：**2026-10-16**；包版本0.4.0，共享开发分支 `feat/purchase-data-prep`。
双方向职责、依赖边界和扩展约定见[架构审查](architecture-2026-10-16.md)；
唯一工作区规则见[单目录交接](handoff/single-workspace-2026-10-16.md)。下方为分日期进度。
最新进度统一见[项目状态](project-status.md)，本次交付检查与推送见[验证记录](validation-and-delivery.md)。
2026-10-15已完成952场源日志观测任务的频率/逻辑回归基线，尚未证明线性模型整体胜出。见[首轮实验](purchase-log-baseline-2026-10-15.md)；规则推荐和实际购买语义验收仍保留边界。

2026-10-15续接：[验证集误差与分布诊断](purchase-log-diagnostics-2026-10-15.md)已完成，359项pytest通过；未重训练或重新分析测试集。

新增采集：[再收集1,000场（去重/限流/自动等待）](collection-additional-1000-2026-10-15.md)。

当前开发：[截距与正则化对照方案](purchase-log-sensitivity-plan-2026-10-15.md)已实现，真实实验待确认；不评估新增数据。

## 按任务阅读

| 你要做什么 | 文档 |
|---|---|
| 固定采样、离线诊断和补丁时间核验 | [数据可行性审计](data-feasibility.md) |
| 理解位置估算、购买汇总和成装标签限制 | [语义核验](data-semantics.md) |
| 规划首个真实ML实验与防泄漏要求 | [ML实验设计](ml-first-experiment.md) |
| 检查训练前数据处理是否就绪 | [预检与阻塞清单](pretraining-readiness.md) |
| 先判断项目做到了哪里 | [完成度与验证证据](project-status.md) |
| 运行主宰推荐、理解范围及全英雄/全位置扩展方式 | [本地阵容推荐](lineup-recommendation.md) |
| 核对阵容输入及推荐结果格式 | [推荐契约](recommendation-contracts.md) |
| 评审具体报告、补齐交互、安排未参与调参的案例验证 | [推荐质量评审流程](recommendation-quality-review.md) |
| 查看全英雄机制资料与选人评估范围 | [英雄能力知识](../knowledge/README.md) |
| 判断知识如何用于冷启动训练 | [知识与训练候选](knowledge-cold-start.md) |
| 查资料迁移、外部证据与仓库维护路径 | [知识维护与路径清单](knowledge-maintenance.md) |
| 安装、导入、标注、固定数据集、预留模型接入 | [教练工作流](coach-workflow.md) |
| 日常操作、旧命令迁移、备份、故障恢复、人工核验 | [操作指南](workflow.md) |
| 了解模块边界和数据流 | [工程设计](engineering-design.md) |
| 一份 demo 到清洗、特征、标签与训练数组 | [数据管线](data-pipeline.md) |
| 采集 7.41f 高分候选、复现真实回放验收 | [真实数据准入](real-data-acceptance.md) |
| 核对视野、装备、技能、战斗字段及教练任务缺口 | [教练字段核查](coach-field-audit.md) |
| 使用新增上下文、玩家视角与真实重解析检查 | [上下文接入](observer-context.md) |
| 核对真实训练准入及桌面交接 | [训练准入](training-admission.md) |
| 实现训练器或预测器 | [数据契约](data-contracts.md) |
| 理解技术选择和后续性能优化 | [技术选型与优化路线](long-term-roadmap.md) |
| 安排下一轮开发 | [任务清单](roadmap.md) |
| 复核已知限制与历史问题 | [风险复核](project-review.md) |
| 重现检查、区分工程验证和模型效果 | [验证与交付](validation-and-delivery.md) |
| 修改代码或文档 | [贡献指南](../CONTRIBUTING.md) |
| 查版本变化 | [变更记录](../CHANGELOG.md) |

## 文档职责

- `project-status.md` 统一回答完成度，不使用缺乏分母的完成百分比。
- `lineup-recommendation.md` 维护推荐入口、范围及扩展方法；`recommendation-contracts.md` 维护契约。
- `recommendation-quality-review.md` 维护质量评审顺序、证据要求与独立评估约束，不代替实际评审结果。
- `data-contracts.md` 描述代码当前接受和输出的格式；规划中的格式单独注明。
- `coach-workflow.md` 维护命令和适配器用法；`workflow.md` 维护运营与恢复。
- `long-term-roadmap.md` 解释选择、成本和升级条件；`roadmap.md` 维护任务状态与验收要求。
- `validation-and-delivery.md` 维护测试证据及其边界；合成数据通过不等于真实回放语义通过。

出现冲突时，先核对[实现](../src/dota_items/workflow/)和[测试](../tests/)，修正文档并注明验证范围。生成到工作区的 JSON Schema 来自代码；部分运行清单只有版本字段和程序校验，并没有对应的完整 Pydantic Schema。
