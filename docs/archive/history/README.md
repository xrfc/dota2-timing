# 历史阶段文档（2026-11-01归档）

2026-11-01按用户要求（U29）把`docs/`根目录中**已被后续文档替代的阶段记录**移到这里，减少当前入口的干扰。

- 选取规则：文件名带日期且早于2026-10-29，并且没有被代码、测试、脚本、CI或知识包引用（被引用的仍留在`docs/`，避免冻结产物与测试里的路径失效）。共34份。
- 内容不变：只移动位置，并把文中指向其他文件的相对链接与`docs/…`路径改成新位置，可用`git log --follow`查看完整历史。
- 指向`reports/`、`data/`的链接本来就不在git中（被忽略的本地产物），归档前后同样无法在仓库里打开。
- `docs/archive/2026-10-22/`、`2026-10-26/`是逐字节快照（哈希见各自manifest.json），**未改动**；其中按仓库根目录解释的旧链接仍指向原`docs/`位置。
- 当前入口：[文档目录](../../README.md) · [开发计划](../../development-plan-2026-10-30.md) · [架构](../../architecture.md)。
- 2026-11-01（U37双线重构）追加4份2026-10-10历史设计文档：`development-mainline.md`、`module-boundaries.md`、`documentation-inventory.md`、`engineering-design.md`（已被[架构](../../architecture.md)替代）；同样只移位置并改写相对链接。

## 文件清单

- [双方向架构审查（2026-10-16）](architecture-2026-10-16.md)
- [架构与分步任务审查（2026-10-28）](architecture-review-2026-10-28.md)
- [代码审查修复与复审（2026-10-18）](code-review-fixes-2026-10-18.md)
- [队列v2整组划分可行性：实际分析](cohort-v2-feasibility-2026-10-18.md)
- [1,000场购买行为候选采集任务](collection-1000-2026-10-14.md)
- [新增1,000场候选采集（2026-10-15）](collection-additional-1000-2026-10-15.md)
- [下一批主宰采集准备（2026-10-19，未启动网络采集）](collection-next-batch-plan-2026-10-19.md)
- [第一课实践：X、y与不可靠数据（2026-10-28）](data-quality-ml-lab-2026-10-28.md)
- [数据脚本审查修复（2026-10-20）](data-review-fixes-2026-10-20.md)
- [蓝量解码修复与机器学习特征准备（2026-10-28）](decision-mana-repair-2026-10-28.md)
- [决策学习任务草案（2026-10-27，待确认，不可运行）](decision-training-task-draft-2026-10-27.md)
- [历史（2026-10-10）：主线开发流程：7.41f 阵容出装推荐](development-mainline.md)
- [历史（2026-10-10）：开发文档盘点与维护职责](documentation-inventory.md)
- [工程设计：阵容推荐与回放基础设施](engineering-design.md)
- [独立评估离线可行性与采集400排查（2026-10-23）](evaluation-feasibility-2026-10-23.md)
- [独立评估来源小预算复测（2026-10-23）](evaluation-source-probe-2026-10-23.md)
- [开发分支同步检查（2026-10-20）](github-sync-2026-10-20.md)
- [较晚同补丁评估：研究口径设计（DATA-02 / MODEL-07）](independent-evaluation-design-2026-10-23.md)
- [主宰阵容分析原型（2026-10-25）](lineup-analysis-prototype-2026-10-25.md)
- [地图资料获取与地标对照（2026-10-26）](map-reference-2026-10-26.md)
- [历史（2026-10-10）：模块边界、耦合约束与扩展设计](module-boundaries.md)
- [现有952场离线处理](purchase-952-processing-2026-10-14.md)
- [新队列 v2 接入方案（2026-10-18，待研究选择确认）](purchase-cohort-v2-plan-2026-10-18.md)
- [首轮源购买日志机器学习基线（2026-10-15）](purchase-log-baseline-2026-10-15.md)
- [购买日志基线：验证集误差与分布诊断（2026-10-15）](purchase-log-diagnostics-2026-10-15.md)
- [截距与正则化对照：实现已完成，真实实验待确认](purchase-log-sensitivity-plan-2026-10-15.md)
- [v2 比赛级随机划分与模型输入（2026-10-21）](random-cohort-v2-2026-10-21.md)
- [近期开发进度与交付摘要（截至2026-10-23）](recent-progress-2026-10-23.md)
- [位置与可见性数据扩量（2026-10-26）](replay-expansion-2026-10-26.md)
- [录像坐标直接实体来源与原生地标（2026-10-22）](replay-identity-2026-10-22.md)
- [三场突跳与技能、物品、复活事件核对（2026-10-23）](replay-jump-events-2026-10-23.md)
- [原始录像轨迹与视野试点（2026-10-22）](replay-pilot-2026-10-22.md)
- [原始录像兼容修复与轨迹、视野续报（2026-10-22）](replay-pilot-compat-results-2026-10-22.md)
- [三场录像语义审计（2026-10-22）](replay-semantics-2026-10-22.md)
- [整局11装备：固定频率与阵容逻辑回归对照](whole-log-baseline-2026-10-21.md)
- [整局固定预测：校准与训练/验证差距诊断](whole-log-calibration-2026-10-21.md)
- [整局两组C真实对照（2026-10-22）](whole-log-regularization-2026-10-22.md)
- [开局阵容 → 整局11装备源日志任务（2026-10-21）](whole-log-task-2026-10-21.md)
