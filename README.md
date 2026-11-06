# Dota 2 离线分析与机器学习实践

只做**赛前准备**和**赛后复盘**，不做实战实时辅助。这个项目也是用户学习机器学习的实践：数据、标签、划分、模型和指标的关键选择都写在文档里。

**入口**：[开发计划](docs/development-plan-2026-10-30.md)（唯一进度：§7）· [架构](docs/architecture.md) · [决策记录](docs/decisions/README.md) · [文档索引](docs/README.md) · [变更记录](CHANGELOG.md)

## 项目结构：共享底座＋两条线（U37，2026-11-01）

| 线 | 做什么 | 当前状态 |
|---|---|---|
| **共享底座** | 来源读取与采集预算、存储与哈希、契约、录像解析与清洗、**MK机制知识**（官方原文→机制规则→推导）、通用评估 | MK进行中（MK-T3机制事实复核） |
| **路线A 推荐** | 机器学习相关的阵容、出装、针对装、对线推荐；复盘里“同线上表现的出装时间对照”（U13） | M1数据底座完成；M2出装时间预测已结案；M2b针对装暂停，MK后恢复 |
| **路线B 意识决策** | 差异化方向：防被抓、是否参团、集合抓人，只用当时可知的信息评价决策 | 设计草案（[路线B](docs/awareness-track.md)），待定义（Q14–Q16） |

产品C（赛后复盘）由两线合并展示，但两线的模型、数据和验收各自独立。用户主玩1号位和5号位、优势路，传奇段位；参照节奏以超凡以上为准（U7）。

## 当前可用

| 入口 | 线 | 内容 | 限制 |
|---|---|---|---|
| `scripts/coach_app.py`（8780） | A | “出装节奏参照”和“赛前·针对装”两页，高分段基线 | 无阵容输入；阵容影响未证实（M2b模型未通过） |
| `scripts/replay_viewer.py` | B | 13场录像的全知/天辉/夜魇回放 | 证据浏览工具，不给建议 |
| `scripts/decision_review.py`（8768–8770） | B | R1两个支援/刷钱案例的评审包 | 人工案例，非训练标签 |
| `knowledge/mechanics/` | 共享 | 机制词表v13、复核后事实v20、规则v11、派生层v11（档案、克制关系候选，草稿），统一入口`current.json`、交叉复核记录 | 规则层（MK-T4）已结束，推导层（MK-T5）进行中 |

模型和冻结数据不随Git分发（`data/`、`reports/`是本地证据），干净克隆不能直接复现真实预测。

## 快速开始

Python 3.11+。新环境首次安装（已有`.venv`直接复用，不重复安装）：

```bash
python scripts/bootstrap.py --dev --data --replay
```

```bash
python coach.py --workspace coach-workspace/demo demo
```

```bash
python scripts/check.py
```

`demo`生成6场synthetic比赛与事实报告，不执行真实训练；Node.js 22用于前端与学习区的JS检查。已有本地冻结产物时启动8780：

```bash
PYTHONPATH=src .venv/bin/python scripts/coach_app.py --port 8780
```

其他命令见[脚本导航](scripts/README.md)；Windows用`.venv\Scripts\python.exe`并先设`$env:PYTHONPATH = "src"`。

## 代码组织

```text
src/dota_items/
  sources/      外部来源（OpenDota、Gem录像解析）           ┐
  data/         证据、清洗、可知性、快照、MK机制知识          │ 每个模块在 architecture.py
  contracts/    标准库契约   handoff/  只读交接包             │ 登记“线”（共享/A/B）与状态
  modeling/     训练、估计器、制品、推理、评估               │ （active / maintenance）
  experiments/  整局实验编排（仅维护）  workflow/ coach工作区  │
  recommendation/ 7.41f规则原型（仅维护）                    ┘
scripts/  命令入口与本地页面     tests/  工程回归     knowledge/  带来源的公开知识
learning/ 学习材料与练习         examples/  合成/手工案例     docs/  文档（archive/为历史）
```

依赖规则：层之间沿用原有约束（如data不导入modeling，contracts只用标准库）；线之间**共享底座不导入任一线，A、B两线互不导入**。两者都由`tests/test_architecture.py`强制。冻结产物的指纹记录源码路径，所以重构采用原地归类、不搬文件，详见[架构](docs/architecture.md)§5。

## 开发边界

- 真实训练、联网采集、新数据用途、划分变更、新增依赖，每次都须用户单独授权（计划§2 Q7）。
- 产物写入新的带日期目录，不覆盖旧产物；哈希失配不能忽略，生产者迁移须显式登记。
- 行为预测不等于最佳决策；工程检查通过不等于游戏语义认证；证据不足时写“未知”。
- 协作规则见[AGENTS.md](AGENTS.md)与[贡献指南](CONTRIBUTING.md)；临时环境中的AI按[临时分支契约](docs/handoff/ai-temp-branch-contract.md)工作。

[学习入口](learning/README.md) · [MIT许可证](LICENSE)

包版本仍为0.4.0。2026-11-01之前的README（含10/26–10/27逐轮增量说明）可用`git log -p README.md`查看，[2026-10-26整理前README](docs/archive/2026-10-26/INDEX.md)另有逐字节快照。
