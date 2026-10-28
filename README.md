# Dota 2 离线分析与机器学习实践

以真实对局学习数据处理、机器学习和离线复盘。已有主宰购买日志模型、阵容分析原型及录像时间线；**行为预测不等于最佳出装，工程检查不等于游戏语义认证**。

## 当前能力（2026-10-26）

| 方向 | 已完成 | 尚未证明 |
|---|---|---|
| 购买行为模型 | 1990场、1592/398开发划分，整局11装备频率/逻辑回归及正则化对照 | 独立泛化、装备收益与购买顺序 |
| 阵容原型 | 单阵容分析、A/B概率与贡献差、训练支持 | 机制因果、最佳建议、浏览器视觉验收 |
| 录像与地图 | 13场全知/阵营时间线、2场大文件恢复、494个建筑地标、12点底图视觉检查 | 全部地形、动态迷雾、录像训练准入 |
| 前瞻评估采集 | 协议与预算已冻结，入口就绪 | 未采集500场；计划10/31 08:00（北京时间）窗口封口后恢复 |

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

复用单工作目录与现有`.venv`；共享文件/全量验收先协调停写。专项不代替全量检查，不修改冻结产物来消除哈希失配。真实训练、采集及研究口径分别遵守授权。

[贡献指南](CONTRIBUTING.md) · [验收记录](docs/validation-and-delivery.md) · [变更记录](CHANGELOG.md) · [学习入口](learning/README.md) · [MIT许可证](LICENSE)

旧CLI和文件路径保持兼容；[整理前README](docs/archive/2026-10-26/INDEX.md)保存历史状态，不把过去“未训练/待确认”当作当前结论。包版本仍为0.4.0，未创建新发布。
