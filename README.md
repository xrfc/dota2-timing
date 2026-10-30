# Dota 2 离线分析与机器学习实践

> 2026-10-27对照包增量：当前8769改为两例[支援/刷钱对照与试标草稿](docs/decision-comparison-2026-10-27.md)，新增双方同刻可见血量、队友库存、TP到场条件拆解与草稿下载。蓝量已定位schema版本初始化导致范围65536→8192的问题，但未修正旧数据/生产者；敌方装备/CD、完整施放、合法落点/路径及数值收益仍未齐。旧包/旧结果保留，非盲评、非正式标签，不授权训练；后文旧状态按原阶段解释。

## 当前开发计划（2026-10-30）

三个产品：赛前针对装（U13起，原“出装时间预测”结案）、赛前对线打法、赛后复盘（含按线上表现的出装时间对照）。当前可用：`scripts/coach_app.py`（8780）高分段出装节奏参照。下一步见计划§7。执行计划与唯一进度见[开发全流程计划 M0–M6](docs/development-plan-2026-10-30.md)；决策见[决策记录](docs/decisions/README.md)。

## 原开发顺序（2026-10-27，已被上节替代）

决策时点证据包 → 3–5个复盘建议案例 → 评审并冻结任务契约 → 样本与防泄漏 → 获准后的基线/模型 → 独立复盘验收。详细交付与出口只维护在[总路线](docs/roadmap.md)。回放器是支撑工具，不是最终成果；不做实战实时辅助。

目标是基于位置与当时可用装备进行离线复盘：**什么时候注意地图，什么时候保守，什么时候可以激进走位，并给出理由与具体动作。** 当前已有购买行为模型、阵容原型、回放证据工具及五个人工建议案例；正式决策建议模型尚待开发。行为预测不等于最佳决策，工程检查不等于游戏语义认证。

## 当前能力（2026-10-26）

| 方向 | 已完成 | 尚未证明 |
|---|---|---|
| 购买行为模型 | 1990场、1592/398开发划分，整局11装备频率/逻辑回归及正则化对照 | 独立泛化、装备收益与购买顺序 |
| 阵容原型 | 单阵容分析、A/B概率与贡献差、训练支持 | 机制因果、最佳建议、浏览器视觉验收 |
| 录像与地图 | 13场全知/阵营时间线、2场大文件恢复、494个建筑地标、12点底图视觉检查 | 全部地形、动态迷雾、录像训练准入 |
| 前瞻评估采集 | 协议与入口保留为历史 | 2026-10-30按用户决定取消，未采集；如需独立评估须重新设计窗口 |

当前流程与任务只维护三份主文档：[总路线](docs/roadmap.md)、[数据](docs/data-prep-progress.md)、[模型](docs/model-foundation.md)。
完整分类见[文档索引](docs/README.md)，源码/脚本定位见[结构维护](docs/modular-maintenance.md)和[脚本导航](scripts/README.md)。

## 快速开始

Python 3.11+；新环境首次安装（已有环境直接复用，不重复安装）：

```bash
python scripts/bootstrap.py --dev --data --replay
python coach.py --workspace coach-workspace/demo demo
python coach.py --workspace coach-workspace/demo doctor
python scripts/check.py
```

启动器自动选择项目`.venv`，Windows亦可执行上述命令。demo生成6场synthetic比赛、4/1/1划分和事实报告，不执行真实训练；Node.js 22用于学习区JS检查。

已有冻结本地模型和快照时，可运行阵容对比：

```bash
PYTHONPATH=src .venv/bin/python scripts/lineup_comparison.py --serve --port 8766
```

打开服务所在机器的`http://127.0.0.1:8766`。跨设备需要现有转发。Windows命令、输入要求及限制见[原型说明](docs/lineup-comparison-review-2026-10-25.md)；模型不随Git分发，干净克隆不能直接复现真实预测。

## 数据流与结构

```text
来源/录像 → sources → data清洗/审计 → 冻结快照与只读handoff
                                     ├─ modeling训练/推理/诊断 → 阵容原型
                                     └─ tick对齐 → 全知与两阵营时间线
contracts：轻量共享契约；workflow/experiments：编排；scripts：命令入口
```

- `src/dota_items/`：正式Python包；`tests/`：工程回归；`scripts/`：CLI与固定审计工具。
- `docs/`：主文档、接口、操作及日期证据；`docs/archive/`：不可变历史快照。
- `knowledge/`：带来源的公开知识；`learning/`：独立学习材料和测试；`examples/`：合成/手工案例。
- `data/`、`reports/`、`coach-workspace/`：本地数据和制品，不提交；`memory/`、凭据和环境不发布。

地图和录像交付：[质量报告](docs/replay-quality-2026-10-26.md)。文档中的data/reports链接是本地证据路径，GitHub不可直接读取，不代表公开附件或丢失。重现需原冻结输入，不能用重新下载冒充同一证据。

## 开发与边界

复用单工作目录、`main`与现有`.venv`；共享文件/全量验收由当前执行者串行处理并检查源码漂移，不再要求其他开发者停写确认。Git结构与已合并分支清理见[维护记录](docs/git-maintenance-2026-10-30.md)。专项不代替全量检查，不修改冻结产物来消除哈希失配。真实训练、采集及研究口径分别遵守授权。

[贡献指南](CONTRIBUTING.md) · [验收记录](docs/validation-and-delivery.md) · [变更记录](CHANGELOG.md) · [学习入口](learning/README.md) · [MIT许可证](LICENSE)

旧CLI和文件路径保持兼容；[整理前README](docs/archive/2026-10-26/INDEX.md)保存历史状态，不把过去“未训练/待确认”当作当前结论。包版本仍为0.4.0，未创建新发布。

2026-10-27数据侧新增：[五个决策复盘案例](docs/data-decision-cases-2026-10-27.md)，包含当时证据、人工建议与分离的事后采样。尚未通过游戏语义评审或浏览器视觉验收，不是新模型。

2026-10-27增强交付：[字段可用性清单](docs/decision-field-readiness-2026-10-27.md)与[训练任务草案](docs/decision-training-task-draft-2026-10-27.md)。案例1/2增加参团、发育、换区的条件比较及未准入来源附录，独立增强页用8769；不是新模型或已批准标签。

2026-10-27状态卡增量：[血蓝、技能CD与TP取证](docs/decision-state-card-2026-10-27.md)。已独立离线读取原两场录像，提取6条指定状态；案例1无敌斩约30.7秒CD，案例2TP约3.0秒CD，属于来源观测而非完整可施放认证。当前状态卡沿用8769，mana单位/精确到场/收益仍有缺口；未训练。

### 2026-10-27案例评审追补

案例1追加反馈已核对：大圣最后可见距当前22秒，可能转移但位置仍未知；8769更新为具体四问与修订包，旧证据保留。 详见[对照包追加反馈](docs/decision-comparison-2026-10-27.md)。

2026-10-27展示增量：8769支持点击地图英雄／名单切换，在同一面板看血量、蓝量认证状态、技能/TP CD与装备；历史采样不沿用当前状态。蓝量与其他英雄CD缺口不变。见[集中状态面板](docs/decision-comparison-2026-10-27.md#地图选中英雄与集中状态面板2026-10-27)。
