# 脚本职责导航

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
