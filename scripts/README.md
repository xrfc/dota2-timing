# 脚本职责导航

> 2026-10-27对照包增量：当前8769改为两例[支援/刷钱对照与试标草稿](../docs/decision-comparison-2026-10-27.md)，新增双方同刻可见血量、队友库存、TP到场条件拆解与草稿下载。蓝量已定位schema版本初始化导致范围65536→8192的问题，但未修正旧数据/生产者；敌方装备/CD、完整施放、合法落点/路径及数值收益仍未齐。旧包/旧结果保留，非盲评、非正式标签，不授权训练；后文旧状态按原阶段解释。

> 2026-10-27目标同步：当前主线见[总路线](../docs/roadmap.md)。replay_viewer.py仅供证据复盘，尚无保守/激进建议CLI；不能以旧训练脚本直接启动新任务。时点证据、案例、契约与模型按阶段开发，旧命令/冻结输入不变。

保留现有CLI路径，不为分类搬迁哈希绑定的生产者。正式业务模块在`src/dota_items/`；部分固定审计脚本仍包含编排实现，不声称已经全部薄CLI化。

从仓库根目录执行，复用`.venv`。一般使用`PYTHONPATH=src .venv/bin/python scripts/名称.py --help`；Windows先设置`$env:PYTHONPATH = "src"`，再用`.venv\Scripts\python.exe`。`--help`不是执行真实任务许可；少数历史批处理入口没有通用help，先阅读相应说明和脚本。

## 常用入口及前提

| 用途 | 入口 | 前提/文档 |
|---|---|---|
| 完整验收 | `check.py` | 单写者窗口；模块scope不代替all |
| 单阵容/A-B | `lineup_analysis.py` / `lineup_comparison.py` | 本地冻结模型/快照；[案例说明](../docs/lineup-comparison-review-2026-10-25.md) |
| 前瞻采集 | `collect_evaluation_cohort.py` | 冻结协议、预算与窗口；[执行方案](../docs/evaluation-execution-proposal-2026-10-23.md)；本次整理不执行run |
| 录像tick导出 | `align_replay_ticks.py` | 原始/cleaned/manifest及冻结Gem兼容目录；[质量报告](../docs/replay-quality-2026-10-26.md) |
| 大文件恢复 | `recover_large_replay_cleaning.py` | 已有缓存，512 MiB显式上限，clean-only，无样本/训练 |
| 地标重读 | `audit_replay_map_landmarks.py` | 已下载录像、收据、兼容目录，独立输出 |
| 原始通道 | `export_raw_replay_channels.py` | 与清洗导出分开，不默认消除重复tick |

录像对齐/原始导出在导入时使用Gem：`PYTHONPATH=data/replay-pilot-2026-10-22/compat-v1:src`。兼容目录是本地冻结资产，不随Git克隆；不能用任意安装版本冒充。其他生产/训练命令见[数据主文档](../docs/data-prep-progress.md)、[模型主文档](../docs/model-foundation.md)和[实验维护](../docs/experiment-maintenance.md)。

## 完整脚本目录

### 环境与检查

- [bootstrap.py](bootstrap.py)
- [check.py](check.py)

### 阵容产品原型

- [lineup_analysis.py](lineup_analysis.py)
- [lineup_comparison.py](lineup_comparison.py)

### 冻结模型与实验

- [compare_purchase_sensitivity.py](compare_purchase_sensitivity.py)
- [diagnose_purchase_baseline.py](diagnose_purchase_baseline.py)
- [diagnose_whole_log_experiment.py](diagnose_whole_log_experiment.py)
- [model_foundation.py](model_foundation.py)
- [prepare_whole_log_cohort.py](prepare_whole_log_cohort.py)
- [render_purchase_sensitivity.py](render_purchase_sensitivity.py)
- [report_whole_log_regularization.py](report_whole_log_regularization.py)
- [run_whole_log_experiment.py](run_whole_log_experiment.py)
- [run_whole_log_regularization.py](run_whole_log_regularization.py)
- [train_purchase_baseline.py](train_purchase_baseline.py)
- [verify_whole_log_handoff.py](verify_whole_log_handoff.py)
- [whole_log_experiment.py](whole_log_experiment.py)
- [whole_log_regularization.py](whole_log_regularization.py)

### 录像采集、解析与审计

- [replay_viewer.py](replay_viewer.py)：本地地图播放器；[说明](../docs/replay-viewer.md)。静态页面在`replay_viewer_assets/`。

- [accept_replays.py](accept_replays.py)
- [align_replay_ticks.py](align_replay_ticks.py)
- [audit_replay_identity.py](audit_replay_identity.py)
- [audit_replay_jump_events.py](audit_replay_jump_events.py)
- [audit_replay_map_landmarks.py](audit_replay_map_landmarks.py)
- [audit_replay_semantics.py](audit_replay_semantics.py)
- [audit_replay_tracks.py](audit_replay_tracks.py)
- [audit_saved_replays.py](audit_saved_replays.py)
- [build_replay_compat.py](build_replay_compat.py)
- [collect_replay_expansion.py](collect_replay_expansion.py)
- [export_raw_replay_channels.py](export_raw_replay_channels.py)
- [recover_large_replay_cleaning.py](recover_large_replay_cleaning.py)
- [render_replay_semantics.py](render_replay_semantics.py)
- [report_replay_identity.py](report_replay_identity.py)
- [run_replay_pilot.py](run_replay_pilot.py)
- [verify_context_replays.py](verify_context_replays.py)

### 购买数据、评估采集与审计

- [analyze_cohort_splits.py](analyze_cohort_splits.py)
- [audit_evaluation_feasibility.py](audit_evaluation_feasibility.py)
- [audit_purchase_cohorts.py](audit_purchase_cohorts.py)
- [audit_purchase_observations.py](audit_purchase_observations.py)
- [collect_evaluation_cohort.py](collect_evaluation_cohort.py)
- [collect_purchase_additional.py](collect_purchase_additional.py)
- [collect_purchase_candidates.py](collect_purchase_candidates.py)
- [collect_purchase_guarded.py](collect_purchase_guarded.py)
- [collect_purchase_latest.py](collect_purchase_latest.py)
- [collect_purchase_until_daily.py](collect_purchase_until_daily.py)
- [export_collection_table.py](export_collection_table.py)
- [package_purchase_handoff.py](package_purchase_handoff.py)
- [prepare_purchase_preview.py](prepare_purchase_preview.py)
- [prepare_purchase_snapshot.py](prepare_purchase_snapshot.py)
- [prepare_random_cohort.py](prepare_random_cohort.py)
- [probe_evaluation_sources.py](probe_evaluation_sources.py)
- [report_purchase_cohorts.py](report_purchase_cohorts.py)
- [run_purchase_additional.py](run_purchase_additional.py)
- [summarize_purchase_collection.py](summarize_purchase_collection.py)

### 人工决策复盘案例（2026-10-27）

`PYTHONPATH=src .venv/bin/python scripts/decision_review.py --output reports/decision-review-2026-10-27-v2 --serve --port 8768`。生成新包须加`--build`并使用不存在的目录，不覆盖冻结证据。提供时点证据和人工建议/独立事后对照，不训练。Windows及字段限制见[数据侧说明](../docs/data-decision-cases-2026-10-27.md)。

### 两例增强与字段来源核查（2026-10-27）

`scripts/enhance_decision_cases.py --output reports/decision-enhanced-new`复用原包/反馈，生成新目录；不覆盖、不采集或训练。查看最终包：`PYTHONPATH=src .venv/bin/python scripts/decision_review.py --output reports/decision-enhanced-2026-10-27-v3 --serve --port 8769`。原五例仍在8768。字段/分母/Windows操作见[字段清单](../docs/decision-field-readiness-2026-10-27.md)。

### 决策状态探针与状态卡（2026-10-27）

- scripts/probe_decision_state.py：--freeze-plan FILE冻结原两场，或--plan FILE --match ID --output NEWDIR独立离线读取；仅允许固定ID和tick，禁止覆盖，源码/输入变化拒绝执行。
- scripts/build_decision_state_cards.py --output NEWDIR：只读完整探针收据和增强v3，保持原decision_input及历史后续文件。
- 当前页面：`PYTHONPATH=src .venv/bin/python scripts/decision_review.py --output reports/decision-state-cards-2026-10-27-v1 --serve --port 8769`。

示例、Windows、来源边界与恢复见[状态卡说明](../docs/decision-state-card-2026-10-27.md)。未扩大为任意比赛解析或训练入口。

## 2026-10-27评审追补

`scripts/revise_decision_review.py --revision examples/decision-review-followup-2026-10-27.json --output reports/decision-review-followup-new`在新目录应用绑定基础包的文本/具体问题修订，拒绝改身份和不实最后可见断言。命令前加`PYTHONPATH=src .venv/bin/python`，Windows沿用既有解释器说明。当前8769服务包为`reports/decision-review-followup-2026-10-27-v1`，不改原始输入/后续/空白模板，不训练。见[案例追补](../docs/decision-comparison-2026-10-27.md)。

### 英雄集中状态展示（2026-10-27）

`decision_review_assets`已加入地图点选／名单切换及集中状态面板；仍用上节followup-v1启动命令及8769，无新HTTP字段、采集或依赖。修改静态页须重启本地评审服务后刷新；先下载内存草稿。专项沿用`node --test tests/test_decision_review_ui.cjs`。见[面板与验证](../docs/decision-comparison-2026-10-27.md#地图选中英雄与集中状态面板2026-10-27)。

### 修复蓝量接入（2026-10-30，R1）

`scripts/attach_decision_mana.py --base reports/decision-review-followup-2026-10-27-v1 --repair reports/decision-mana-repair-2026-10-28-v1 --output NEWDIR`只替换状态卡决策时点蓝量，生成新目录，基础包不变。当前页面：`PYTHONPATH=src .venv/bin/python scripts/decision_review.py --output reports/decision-review-mana-2026-10-30-v2 --serve --port 8770`，替代8769的followup-v1。见[接入记录](../docs/decision-mana-integration-2026-10-30.md)。

全队状态（方案A）：`scripts/probe_team_state.py --freeze-plan FILE`后`--plan FILE --match ID --output NEWDIR`离线抓两场10名英雄决策时点状态；`scripts/attach_team_state.py --base reports/decision-review-mana-2026-10-30-v2 --probe reports/decision-team-state-2026-10-30-v1 --output NEWDIR`生成新包。当前8770服务包为`reports/decision-review-team-2026-10-30-v2`。
