# 并行开发与串行集成协议


更新：2026-10-28，用户取消其他开发者停写确认门禁；下方历史授权记录不恢复该要求。保持一个工作区、共享分支和现有环境；不拆仓库或 worktree。

## 文件所有权

| 范围 | 写入者 | 并行条件 |
|---|---|---|
| src/dota_items/data/、sources/ | 数据开发 | 文件未被他人占用；冻结实现另遵守证据兼容约束 |
| src/dota_items/modeling/ | 模型开发 | 不修改数据侧实现或快照 |
| scripts/、tests/、examples/、docs/ 内明确属于某侧的文件 | 对应开发者 | 开始前列出本轮具体文件；不按共享目录整体认领 |
| contracts/、handoff/、storage.py、domain.py、normalize.py、workflow/、recommendation/ | 串行协调 | 当前执行者评估接口与影响，串行修改 |
| AGENTS.md、README、docs/README、架构/交接协议、pyproject、依赖锁文件、CI、scripts/check.py、tests/test_architecture.py、tests/test_modular_maintenance.py、tests/test_check_scopes.py、其他公共配置 | 串行协调 | 单写者操作，完成后通知双方重新读取 |
| .venv、Git index/分支状态 | 串行协调 | 依赖变更与Git写操作不得并行 |
| 原始缓存、冻结快照、历史报告/制品 | 不可变证据 | 不覆盖；获准的新产物写各自独立目录 |

数据专属文件示例：scripts/audit_purchase_cohorts.py、scripts/package_purchase_handoff.py、
tests/test_cohort_handoff.py、tests/test_package_purchase_handoff.py、docs/data-prep-progress.md。
模型专属文件示例：scripts/model_foundation.py、tests/test_model_foundation.py、
examples/model-foundation-lineup.json、docs/model-foundation.md。
这些只是示例，不授予覆盖已有未提交修改的权限；未明确归属的文件默认共享，先协调。

## 并行阶段

1. 每侧先读 AGENTS、本文及当前 git status，向协调者声明本轮文件范围和输出目录。
2. 各自修改专属文件并运行专项测试；只格式化自己的文件。测试必须使用独立临时目录，
   不共享可写缓存/固定产物路径。专项通过不等于全库验收通过。
3. 发现共享文件需求，记录路径、修改理由、接口/证据影响、验证方式；当前执行者串行处理，不等待其他开发者确认；实际冲突另行处理。

## 串行协调流程

当前任务执行者负责授权范围内的串行集成，无需另行请求停写确认；不因此取得其他任务的指挥权。
协调记录通过当前任务对话或可用的跨会话消息交接；不同会话不会自动共享上下文。

1. 记录：列出共享文件、执行者、影响范围、预期验证及恢复办法。
2. 检查：读取最新文件及工作区状态，保护已有改动；不以其他开发者回复或停写确认为准入条件。发现实际冲突时暂停受影响文件并说明冲突，其余工作继续。
3. 执行：单一执行者重新检查工作区和文件，合并而非覆盖已有修改；只操作已约定范围。
4. 发布结果：说明修改与验证结果；双方重新读取共享接口后恢复专属开发。

依赖安装/更新前，两侧停止使用该环境的任务；先检查现有依赖与可复用方案，
依赖修改仍需遵守当前授权，不能把本协议当作安装许可。完成后检查依赖一致性并通知双方。
提交、切分支、清理、发布仍遵守原授权边界；“串行”不意味着这些操作已获准。

## 最终全量验收窗口

1. 当前执行者汇总文件清单、专项结果和已知问题；无需先取得其他开发者停写确认。
2. 当前执行者串行验收，检查可见写进程，不擅自终止；记录 HEAD、工作区状态及本轮文件指纹。
   仅 git diff 不足以记录未跟踪文件，必须将它们纳入范围。
3. 运行 .venv/bin/python scripts/check.py，并核对冻结证据和接口兼容性。
4. 比较验收前后源文件状态/指纹；出现外部修改则该次结果不作为最终验收，重新安排窗口。
5. 输出各套测试、lint、格式检查、失败/跳过及日志路径；确认源码未漂移后结束窗口。
   修复任一问题后按影响补专项回归，并在稳定窗口重跑全量检查。

最终验收不要求自动提交；旧的454项结果只是历史基线，不是以后每轮的保证。
本协议是协作约束，不是文件系统互斥锁；不声称能强制阻止不遵守规则的进程。

## 研究边界不变

数据用途、标签、划分、真实训练、选模及旧 test 使用仍需既有或新增明确授权。
新增1,038场不能因为工程集成而自动进入训练或评估；不得覆盖冻结证据。

## 2026-10-17补充

用户确认本轮仅一个执行者，允许顺序处理跨模块重构；这不是以后永久独占授权。当前接口与专项检查见[维护指南](../modular-maintenance.md)，模块scope不代替全量窗口。

## 2026-10-22整局实验模块补充

`src/dota_items/experiments/`为跨模块编排，按共享范围串行协调；`modeling/whole_log_comparison.py`为模型专属纯计算。整局实验脚本只保留CLI／兼容导出。用户已确认本轮无其他开发者，由当前执行者串行整理；此确认不构成未来永久独占授权。入口与专项范围见[实验层维护](../experiment-maintenance.md)。

## 2026-10-27状态卡文件归属补充

本轮新增sources/decision_state_capture.py、data/decision_state.py、scripts/probe_decision_state.py、scripts/build_decision_state_cards.py及对应decision_state测试为数据侧专属；既有gem_capture/2和冻结compat副本保持原字节。应用页面、公共导航/API/验收和本协议修改沿用本轮已获确认的串行停写窗口，不构成未来永久独占。新raw探针、旧包和生产者实现各自保留指纹；正常开发不得覆盖历史capture或把后一个tick送入当前卡。完整接口和验收入口见[状态卡交付](../decision-state-card-2026-10-27.md)。

本轮数据侧新增`data/decision_comparison.py`、`scripts/build_decision_comparisons.py`、`scripts/audit_decision_mana.py`及对应测试；页面/样式、全部相关文档、最终全量验收由当前执行者串行集成。已封存旧解析器与probe源码不修改，新产物独立留存。

### 2026-10-27案例评审追补

新增scripts/revise_decision_review.py及对应测试为数据侧；examples修订规格、页面/文档/服务切换由当前执行者沿用本轮停写授权串行集成。 详见[对照包追加反馈](../decision-comparison-2026-10-27.md)。

### 2026-10-27英雄集中面板

当前执行者沿用本轮已确认的串行停写授权，仅修改评审页三份资源、页面专项测试与入口/状态/协作/验收文档；无新依赖或共享数据契约变更。8769重新加载页面、8768保留。当前UI证据与复现入口见[集中面板](../decision-comparison-2026-10-27.md#地图选中英雄与集中状态面板2026-10-27)；旧封存包不更新指纹，当前页面身份由新验收收据绑定。
