# DOTA2 AI 教练基础设施

2026-10-18续接：独立评估模块增加标签/概率/mask/分组参数校验及合成parity回归；[API和局限](docs/model-foundation.md)、[验收记录](docs/validation-and-delivery.md)。不执行真实评估或训练。

## 只读审查工具 — 2026-10-18

- [数据质量报告](docs/data-prep-progress.md)：已有队列审计JSON转Markdown，检查分母和玩家连通风险，不重算或改变研究用途。
- [模型制品检查](docs/model-foundation.md)：`model_foundation.py inspect --model PATH`展示任务、支持数与实现来源，不训练或预测。
- 当前协调者统一处理共享文档、全量验收及开发分支交付；结果见[验证记录](docs/validation-and-delivery.md)。
- 下方“本地未发布/不推送”为对应日期历史状态；本轮获准测试通过后推送`feat/purchase-data-prep`，不合并main。

## 公共数据接口收尾 — 2026-10-17

来源读取统一到data.source_io；新公共交接目录为reports/public-reader-2026-10-17/handoff/。
旧快照和模型输入语义不变，生产者兼容重建必须显式启用。API、命令及保护边界见[公共读取接口](docs/public-source-reader.md)。


## 当前结构 — 2026-10-17

模型职责已拆分，数据/来源反向依赖已清理，交接读取已独立。当前入口：[单模块维护指南](docs/modular-maintenance.md)。
使用现有.venv运行scripts/check.py --scope modeling、--scope data或--scope recommendation；集成仍须全量检查。
本轮工程与合成回归、既有审计重建不改变数据用途，不真实训练、不提交或推送。以下带日期章节保留历史。

## 双方向开发结构 — 2026-10-16

当前在同一工作区、`feat/purchase-data-prep` 分支协作：`data/` 负责数据与冻结交接，
`modeling/` 负责模型与评估，新增 `contracts/` 提供轻量共享编码接口。
架构边界、已知耦合与扩展约定见[双方向架构审查](docs/architecture-2026-10-16.md)，
操作规则见[单目录交接](docs/handoff/single-workspace-2026-10-16.md)。
本轮改动仅本地，未运行真实训练或推送；下方授权和状态均为各自日期的历史记录。

## 当前交付范围 — 2026-10-15

- 新增采集已完成：16批、1,600场处理，1,038场通过初筛、562场排除；代理采集状态为done，进程已结束。
- 加上历史952场，共1,990场初筛候选；新批次未接入训练、验证或测试，不等于正式训练准入。
- 本轮558场含`purchase_log_not_present`原因，原始数据中均为主宰购买日志字段缺失；不是未购买，不生成负标签，缓存保留。
- 旧952场日志观测基线与训练/验证诊断已完成；截距/正则化对照实现已完成，用户明确选择“实验运行前由我确认”，真实对照尚未运行。
- 用户授权将当前开发推送至`feat/lineup-contracts`，不合并main；代码、测试、文档和汇总证据纳入交付，原始数据、模型运行产物及CSV仍仅本地保存。
- 下方带日期的旧状态为历史记录；“等待冷却”“新增0场”“未推送”不代表当前状态。推送核验另见验证与交付记录。

## 2026-10-15 新增1,000场采集已安排

用户已授权恢复补采；独立批次排除2,950个历史比赛ID，旧952场不计入新目标。
后台进程已启动，等待本地冷却至今天18:21后自动请求；限额到达自动等待，当前新增0场。
368项pytest及静态检查通过。未换IP、未使用第二节点、未重训练或推送。
详见[采集规则、状态与恢复命令](docs/collection-additional-1000-2026-10-15.md)。
下方“补采暂停”为此前决定，已由本次授权替代。

## 最新进度：2026-10-15 验证集误差诊断已完成

在首轮四装备训练基础上，新增训练/验证分布、玩家组、概率分箱及逐场误差诊断；不重训练、不分析测试集。
分身斧平均预测低于验证观测7.75个百分点，是验证Brier退化主要贡献项；成因尚未确定。
359项pytest、全仓Ruff与格式检查通过，原始缓存重建及确定性重算一致。
下一步：冻结训练/验证截距与正则化对照，保留频率基线作为候选；补采暂停，未推送或接入推荐。
详见[诊断结果与复现](docs/purchase-log-diagnostics-2026-10-15.md)。以下为历史阶段记录。

## 最新进度：2026-10-15 首轮机器学习基线已完成

现有952场已完成日志观测快照及玩家隔离划分（571/191/190），并实际训练四装备逻辑回归，比较训练集频率基线。
探索性测试宏平均AP为0.4741（频率0.4539），Brier为0.0878（频率0.0844，越低越好）；尚无整体胜出证据。
BKB无正例不训练。仅预测源日志观测，不代表最优出装或完整实际购买；旧任务准入边界不变。
全项目355项测试通过；补采暂停，未推送、未合并、未接入推荐界面。
详见[实验结果与复现](docs/purchase-log-baseline-2026-10-15.md)。**以下日期段落为历史阶段，不代表当前未训练。**

## 2026-10-14 最新目标确认

用户最新确认首个学习基线：**开局阵容→一号位主宰前30分钟装备购买行为**（2026-10-14，将此前20分钟改为30分钟）；下一件完成装备为后续目标。同批50场离线重跑：8场预览、42场排除、0场训练准入；20分钟计划及结果保留为历史。见[训练前清单](docs/pretraining-readiness.md)。标签覆盖与范围证据仍待验证，未训练。

## 2026-10-14 续接

2026-10-14新增[训练前数据预检](docs/pretraining-readiness.md)：阵容特征白名单、比赛级划分、train-only词表及全mask预演已实现；真实标签/范围证据未齐，仍禁止训练。后续v2已发现跨split玩家重叠（train/validation 9人、train/test 4人），已接入阻塞检查。

## 当前进度（2026-10-13）

已有回放数据管线、一号位主宰规则推荐闭环和数据可行性/语义审计CLI；**还没有训练好的模型**。

- 规则引擎 `lineup-rules/2`：完成首轮内部报告审查、条件传递与未知覆盖展示修正；独立质量验收仍待做。
- 审计器 `purchase-feasibility/3`：固定采样、补丁时间证据、离线审计及位置/购买字段一致性检查。
- 累计13场真实公开JSON，7场同时满足补丁时间一致与30分钟时长覆盖；7场位置均为估算、均缺库存日志，0场获准训练。
- 本地全量305项测试通过；详细交付、分支推送与CI状态见[验证记录](docs/validation-and-delivery.md)。不合并main、不创建发布。

下一步追踪解析器成装事件来源、补独立位置证据，再冻结标签与样本契约，进入频率/线性基线和Embedding/MLP。
参见[项目状态](docs/project-status.md)、[审计使用](docs/data-feasibility.md)、[语义核验](docs/data-semantics.md)、[ML设计](docs/ml-first-experiment.md)。
下方带日期段落是历史交付背景，旧测试数字与当时的“未推送”不代表最新状态。

## 已有本地主线：7.41f 阵容装备建议

2026-10-11 已实现**一号位主宰的实验规则闭环**：十英雄输入、来源校验、阵容需求、
候选排序与 JSON/文本/HTML 报告。全英雄/全位置通过范围配置扩展，不代表当前均已支持。
尚未通过独立推荐质量验收；真实训练仍未准入。以下回放部分保留为已有基础设施。

```bash
python recommend.py examples/recommendation/baseline.json --format text
```

使用、来源边界及扩展方式见[本地阵容推荐](docs/lineup-recommendation.md)。

2026-10-11进入[推荐质量评审阶段](docs/recommendation-quality-review.md)：先评审具体报告，
补齐控制／驱散／免疫交互，再冻结策略并用未参与调参的案例验证。现有6个案例属于开发集，
242项测试通过不能代替这一质量出口。实现位于本地 `feat/lineup-contracts / 47b8f7f`，
尚未进入远端main；本轮用户已授权整体检查后推送该分支，不合并main。
本次交付检查见[验证记录](docs/validation-and-delivery.md#github推送前整体检查2026-10-11)。

## 已有回放与训练基础设施

从职业或高分回放中准备训练数据，用自己的深度学习模型复盘出装与路线决策。当前版本 **0.4.0** 已实现 demo 清洗、历史特征/未来标签、训练集预处理和模型执行接口；实际网络、训练算法和效果评估将在下一阶段实现。

历史主干整合：2026-10-09 当时的三个开发分支合入 `main`（代码基线 `725f35c`），包含上下文、训练准入及缓存/身份追踪修复；不包含10月11日本地推荐器。包版本仍为0.4.0，未创建新发布。最新验证与剩余任务见[项目状态](docs/project-status.md)。

2026-10-10 新增[全英雄能力知识](knowledge/README.md)、[单事件追踪课程](learning/exercises/event-lineage/9031371970/README.md)与[冷启动候选](docs/knowledge-cold-start.md)。先学习当前官网快照，再补历史版本；资料覆盖和训练候选不等于最佳出装监督或训练准入。规范路径与后续维护约定见[路径清单](docs/knowledge-maintenance.md)。

## 当前能做什么

- 独立运行一号位主宰的实验规则推荐，输出有来源、有条件和未知边界的装备方向；见上方入口。
- 批量导入 `.dem`、压缩回放或比赛 JSON，记录购买、位置和自身经济时序。
- 已接入视野/战斗、库存与英雄状态采样，以及 `observe` 玩家视角查询；详见[上下文接入](docs/observer-context.md)。新通道语义仍待核验。
- 一条 `prepare` 命令生成特征、标签、缺失掩码和清洗报告；`build-samples` 输出训练数组。
- 校验证据、按比赛去重、人工标注参考选手，固定按比赛划分的数据集。
- 调用你实现的训练/推理程序，保存配置、日志、状态和模型产物。
- 在没有模型时生成购买事实报告；接入模型后展示候选出装/路线及引用的观测记录。
- 用合成样本离线验证基础设施。Linux Python 3.11/3.12 和 Windows Python 3.12 已通过 CI。
- 独立采集指定补丁的公开高分候选回放，保存来源与逐场管线审计；[真实数据验收](docs/real-data-acceptance.md)说明准入边界和复现方法。

当前没有网页上传、自动获取职业回放、可用模型权重或“决策正确率”。已完成一批 7.41f 真实回放的采集与管线审计；坐标和经济字段的游戏语义核验仍未全部完成。完整边界见[完成度与验证证据](docs/project-status.md)。

## 快速开始

需要 Python 3.11+。在仓库根目录运行，Windows 也可使用这些命令：

```bash
python scripts/bootstrap.py --dev
python coach.py demo
python coach.py doctor
python coach.py status
```

安装需要网络；以上 demo 在安装后可以离线执行。它生成 6 场带 synthetic 标识的比赛、4/1/1 划分的数据集和购买事实 HTML，不执行模型训练。输出 JSON 中的 `report` 是报告路径。

解析真实回放时安装可选依赖：

```bash
python scripts/bootstrap.py --replay --data --dev
python coach.py --workspace coach-workspace/real init
python coach.py --workspace coach-workspace/real prepare /path/to/replays
```

将 `/path/to/replays` 换成自己的目录。然后标注补丁、角色、参考玩家与职业/高分来源，再构建数据集。完整操作见[数据管线](docs/data-pipeline.md)和[教练工作流](docs/coach-workflow.md)。

`coach.py` 自动使用项目的 `.venv`；安装后的等价入口为 `dota-coach`。工作区默认是当前目录的 `coach-workspace/`，也可通过 `DOTA_COACH_WORKSPACE` 设置。项目不自动读取 `.env`。

## 技术选型

| 选择 | 当前用途与理由 | 主要代价 |
|---|---|---|
| Python 3.11+ | 数据处理、CLI 和未来 PyTorch 模型共用语言 | 大文件处理和并行解析需要额外设计 |
| Gem（可选） | 复用 Dota 2 回放解析能力，项目负责语义适配 | 依赖解析器及游戏版本，需要真实样本核验 |
| pandas + scikit-learn（data 可选依赖） | 向后时间对齐、填补/标准化/类别编码 | 目前整 split 在内存处理，依赖真实语义验收 |
| Pydantic 2 | 配置、模型产物、预测接口校验并导出 Schema | 格式通过不代表游戏语义或模型结论正确 |
| JSON/JSONL + SHA-256 | 可检查、可搬迁的数据包和固定快照 | 全量读取与复制占内存、磁盘；无签名或物理只读保证 |
| SQLite | 旧回放解析缓存的索引 | 尚未统一成新工作区的任务/元数据数据库 |
| Python 子进程 + 静态 HTML | 模型框架独立、日志可追踪，结果可离线查看 | 依赖仍共用环境，没有队列、GPU 调度和完整进程树管理 |

取舍、替代方案及升级条件见[技术选型与优化路线](docs/long-term-roadmap.md)。当前无需 PyTorch、CUDA、外部语言模型 API 或常驻服务器。

## 数据流

```text
回放 / 比赛 JSON
  → Gem 解析与证据校验
  → 工作区数据包 + 人工标签
  → 按比赛划分的固定数据集
  → 清洗、历史特征与未来标签 → 仅 train 拟合预处理 → NumPy 数组
  → 自定义训练器（待实现）→ 运行记录 → 模型登记
  → 自定义预测器（待实现）→ 事实 + 候选决策报告
```

观察快照保留整场数据；`build-samples` 生成与其绑定的独立样本快照。训练时必须使用任务 mask 排除未知/截尾标签，推理复用保存的预处理参数。报告中的时间引用检查无法替代模型内部的数据泄漏审计。

## 文档与开发

- [文档索引](docs/README.md)：各文档职责与建议阅读顺序。
- [项目完成度](docs/project-status.md)：已实现、已验证、待补足。
- [训练准入与桌面核验](docs/training-admission.md)：真实训练默认 held，两个账号的工程/客户端分工及交接契约。
- [架构](docs/engineering-design.md)与[数据契约](docs/data-contracts.md)：代码边界和真实接口。
- [日常操作与恢复](docs/workflow.md)、[验证与交付](docs/validation-and-delivery.md)。
- [任务清单](docs/roadmap.md)、[风险复核](docs/project-review.md)。
- [独立学习区](learning/README.md)：组件地图、技术选型、交互实验和 L01–L12 实践计划。运行 `python learning/build.py`，打开 `learning/output/index.html`。
- [贡献指南](CONTRIBUTING.md)、[变更记录](CHANGELOG.md)。

旧入口 `dota-items fetch / ingest-demo / data-status / report` 保留，可继续生成购买事实报告；它的缓存和校验边界见[操作指南](docs/workflow.md)。新工作区的去重、快照和证据校验不能反推成旧入口也具有同等保障。

开发检查：

```bash
python scripts/bootstrap.py --dev --replay --data
python scripts/check.py
```

检查入口自动使用项目 `.venv`，Linux、macOS 和 Windows 使用同一命令。安装 Node.js 22+ 可执行学习区的 JavaScript 检查。测试中的模型程序是接口桩，不能作为训练效果证据。许可证：[MIT](LICENSE)。
