# 验证与交付

## 2026-10-16 本地报告校验增量

`PYTHONPATH=src .venv/bin/python scripts/check.py`通过：380项pytest、22项学习/知识测试、6项JavaScript测试，共408项；Ruff、289文件格式检查、JS语法检查通过。`git diff --check`通过。
新增7项回归仅为合成数据软件验证，不是模型效果评估。真实对照未运行、新增数据未评估；本轮未提交、推送、合并或上传数据。

## 2026-10-15 只读报告续接（本地）

新增敏感性结果Markdown导出与指标学习说明，不改变研究口径。
统一检查通过：373项pytest、学习10项、知识12项、JS6项，共401项；Ruff及289文件格式检查通过。
合成数据CLI冒烟及拒绝覆盖检查通过；没有读取真实比赛或运行真实对照训练。
回归验证原JSON不被修改、ΔBrier方向、来源哈希展示及拒绝测试集评估结果。
本次未推送；上轮fa6719a的GitHub Actions 38716941522已核验success。

## 2026-10-15 开发快照交付

用户明确授权维护文档并推送当前开发；目标为`xrfc/dota2-timing`的`feat/lineup-contracts`，不合并main、不创建Release。
已核验GitHub账号xrfc与仓库所有者一致；fetch后原本地分支与远程分支一致。

- 统一入口`PYTHONPATH=src .venv/bin/python scripts/check.py`通过：372项pytest、学习Python10项、知识12项、JavaScript6项，共400项；Ruff与287文件格式检查通过。
- 汇总采集收据记录新增1,038场候选；原始JSON、CSV、模型运行目录受.gitignore排除，不是本次GitHub数据备份。
- 包含旧952场观测快照/基线/诊断实现、采集预算和去重、逐场表格导出、训练/验证对照模块及测试。
- 未运行真实敏感性对照，未对新增数据建模评估；没有客户端、浏览器或真实回放重解析验证。
- 暂存JSON解析与敏感凭据模式检查通过，未发现原始玩家账号数值字段；差异空白检查仅命中上游Parse.java源码快照的6处尾空格，为保持来源哈希未改写，其他文件通过。
- 本地检查不代表远端CI通过；推送结果由交付回复提供准确提交链接。

以下为历史交付记录。

## 2026-10-15 验证集诊断（本地，未发布）

359项pytest、全仓Ruff及276文件格式检查通过；原缓存重建与确定性重算一致。
4项新增回归覆盖隔离、身份、概率、mask及分母。未重训练、未补采、未推送或合并。
见[诊断报告](purchase-log-diagnostics-2026-10-15.md)与[验收摘要](acceptance/purchase-log-diagnostics-952-2026-10-15.json)。

## 2026-10-14 玩家重叠增量（本地）

新增12项测试，全项目329项通过；Ruff/格式检查通过。固定7场重跑并精确复现，
来源哈希与诊断不输出账号检查通过。train/validation重叠9人、train/test重叠4人，
已接入阻塞而非修改原划分。未提交、推送或训练。详见[就绪清单](pretraining-readiness.md)。

## 2026-10-14 训练前预检（本地）

新增12项测试，全量317项通过（工程289、学习Python10、知识12、JS6），Ruff与格式通过。
固定10场离线预检保留7场预演、3场排除，split=5/1/1、39英雄词表、80列，全标签未知。
重复离线结果精确一致，来源/代码哈希核对通过；旧训练入口拒绝预演文件的回归通过。
固定上游解析器源码证据不等于部署版本或真实成装认证；完整待办见[训练前就绪清单](pretraining-readiness.md)。
未提交、推送或训练；以下10月13日交付仍为当时远端状态。

## 2026-10-13 整体检查与分支交付

用户明确授权检查项目、同步文档并推送。开发分支 `feat/lineup-contracts`，起点 `1a78aad`；
本轮fetch实查起点与origin同分支一致，远端main为 `c6a5e1f`。不合并main、不创建发布。

- 全量 `PYTHONPATH=src python3 scripts/check.py` 通过：工程277、学习Python 10、知识12、JS 6，共305项；Ruff和格式检查通过。
- 六个推荐开发案例复跑：四例正常输出，两例不支持范围返回3；仍不是M06独立质量验收。
- 新隔离工作区demo/doctor通过：6场合成比赛，doctor.errors为空；pip check通过。
- 学习页面重建成功（12项学习任务仍0项验收）；全仓169份Markdown本地链接检查通过。
- 暂存检查仅有3份上游来源文本的末尾空行提示，保留原快照与哈希；排除blank-at-eof后差异空白检查通过。
- 文档统一最新范围、累计13场/聚焦7场、语义限制与下一步；不覆盖历史验收收据，不改学习任务验收状态。
- 新增公开源码快照保留来源/时间/哈希与MIT许可；原比赛JSON、账号、回放、reports、工作区和密钥不提交。
- 本轮没有重解析真实回放、客户端验证、浏览器视觉验收或训练模型。历史CI通过不代表本次远端CI。

交付包含此前本地未提交的报告修正、审计v1–v3、测试、脱敏证据与文档同步。
代码与文档提交 [`9e1a067`](https://github.com/xrfc/dota2-timing/commit/9e1a067) 已成功推送至开发分支。
首次Git缺少凭据助手；使用托管xrfc身份与单命令gh凭据助手完成，未修改全局配置。
本段为推送后收据；本次远端CI未在本地测试结果中冒充通过。
下方各轮“未推送”仅描述该轮历史状态。

## 数据可行性审计检查（2026-10-13，后续轮次）

新增审计CLI、只读诊断模块及23项专项测试。`PYTHONPATH=src python3 scripts/check.py`
通过：工程241、学习Python 10、知识12、JavaScript 6，共269项；Ruff/237文件格式通过。
实际获取公开主宰列表后固定前三场，3次详情获取均成功；真实审计中3场均有日志且均不足30分钟。
来源/选择/文件哈希见[机器记录](acceptance/data-feasibility-2026-10-13.json)，
可运行命令和语义边界见[使用说明](data-feasibility.md)。
首次网络读取遇到环境NO_PROXY的IPv6条目解析问题，仅对子进程设置
`NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1` 后重试成功，未修改全局配置。
未训练、未客户端核验、未推送/合并或运行远端CI；原数据准入保持held。

## 本地报告修正检查（2026-10-13）

起点 `feat/lineup-contracts / 1a78aad`；仅本地修改，无提交、推送或合并。
先复现原版本全量242项通过；新增4条条件传递/报告回归在修复前失败，修复后通过。
最终运行 `PYTHONPATH=src python3 scripts/check.py`，工程218、学习Python 10、
知识12、JavaScript 6，共246项通过；Ruff与233个文件的格式检查通过。
本环境没有 `python` 命令，且已有venv未提供可用的项目可编辑导入，故使用
`python3` 和显式 `PYTHONPATH=src`；启动器本身能够加载src，无需为本轮修改全局环境。

六个开发案例与Git起点引擎逐字段比较，仅 `engine_version` 变化；知识和策略未修改。
18份报告存于 `reports/review-2026-10-13/`，身份/哈希见
[机器记录](acceptance/lineup-review-2026-10-13.json)，发现与处理见
[内部审查](acceptance/recommendation-review-2026-10-13.md)。
不构成M06独立质量验证；未做浏览器视觉检查、真实回放重解析、训练或远端CI。

## GitHub推送前整体检查（2026-10-11）

用户授权整体检查后推送GitHub；目标为 `xrfc/dota2-timing` 的 `feat/lineup-contracts`，
不合并main、不发布版本。检查起点 `05ef781`，包含契约 `112056a`、规则闭环 `47b8f7f`
及文档同步；后续只补交付记录，不修改代码、知识或策略。

- 远端main仍为 `c6a5e1f`；[PR #6](https://github.com/xrfc/dota2-timing/pull/6)仍是另一个文档分支，不是本次推荐实现。
- `python3 scripts/check.py`：214项工程、10项学习Python、12项知识、6项JavaScript，共242项通过；Ruff检查和231个文件格式检查通过。
- 6个推荐输入的退出码、支持状态及候选顺序与原收据一致；11项代码/知识/规则哈希未变。
- 164份Markdown的2005处本地链接目标均存在；外链与锚点未在此项检查中验证。
- 学习页面重建、依赖 `pip check`、独立合成工作区的demo及doctor通过；6场合成数据机械验证通过，没有真实解析或训练。
- 静态复核推荐契约、文件加载、规则核心、报告及CLI边界和对应引擎测试，未发现阻塞本次分支推送的问题；不是全库逐行审计或机制质量认证。
- 推送前差异为64个文件，最大文件约123KB；未包含回放、模型、环境或凭据文件。未改动两项真实回放workflow的配置触发路径。

本地检查结论：可作为**实验规则分支**交付。远端CI以推送后精确提交的
[Actions记录](https://github.com/xrfc/dota2-timing/actions?query=branch%3Afeat%2Flineup-contracts)为准，
不借用PR #6的通过结果。客户端机制核验、推荐HTML视觉检查、独立案例质量评审仍未完成。
下方“未推送”等措辞描述各历史检查轮次，不覆盖本次明确授权。

## 推荐质量阶段文档维护检查（2026-10-11）

本轮仅修改13份Markdown文档，基于本地实现 `47b8f7f` 同步状态与质量评审流程：

- 扫描164份已跟踪或新增Markdown，检查2005处本地链接目标，无缺失；57处外部链接和3处锚点未在本次链接检查中验证。
- 核对原推荐验收记录中的9个代码/测试文件及知识、策略文件，共11项SHA-256全部匹配；未修改旧收据。
- 重建 `learning/output/index.html` 及清单；执行 `python3 scripts/check.py --scope learning`，10项学习Python、12项知识和6项JavaScript测试全部通过。
- 冒烟执行质量评审页列出的4个文本报告命令，均返回0并生成非空报告；这只证明命令可用，不是报告质量评审。
- `git diff --check` 通过。本轮未重跑全量工程测试、浏览器验收或游戏客户端核验；下方242项是上一轮记录。

生成的学习页面仍独立维护学习任务，不将M阶段或流程计划计为个人学习完成。

## 本地推荐实现与证据归属（2026-10-11）

实现位于本地 `feat/lineup-contracts / 47b8f7f582c6ca81de8baf53fbf0b6cf01082983`，
未推送或合并。该实现上一轮运行的统一检查为214项工程、10项学习Python、12项知识、
6项JavaScript测试，共242项，另有Ruff、demo/doctor、安装入口和依赖检查。
结果及文件身份见[固定验收记录](acceptance/lineup-2026-10-11.json)；本次文档维护不冒充重新执行全量工程测试。

该收据的 `base_commit=112056a…` 是验收时未提交改动的父提交；逐文件哈希对应最终
`47b8f7f`，应同时检查文件身份，不能仅凭base_commit认为当时只有契约实现。
6个已运行案例属于开发回归；HTML生成与转义已检查，浏览器视觉检查、客户端机制核验和
独立推荐质量评估尚未完成。下一阶段出口以[质量评审流程](recommendation-quality-review.md)为准。

本日只读核对：远端main为 `c6a5e1ff5eaa597d6c68567ef00f3acc973a64c9`；
[PR #6](https://github.com/xrfc/dota2-timing/pull/6)仍开放，base为main，head为
`f4feae798d7d660755c37f1f192dbaf652f4e5a3`（`docs/741f-development-mainline`）。
其[检查](https://github.com/xrfc/dota2-timing/actions/runs/38065310259)成功，
但对象是该文档PR，不包含本地推荐器，不能用作本地提交的远程CI证明。

推荐入口复现见[使用说明](lineup-recommendation.md)；以下按日期保留原基础设施证据。

## 知识迁入与冷启动候选检查（2026-10-10）

本轮检出基线 `d0be282`；以下属于迁移后的本地检查，不冒充远端 CI 或真实语义核验：

- 统一检查通过：122 项工程 pytest、10 项学习生成器测试、12 项知识边界测试、6 项 JavaScript 测试；Ruff 检查和格式检查通过。
- 127 位英雄、734 个技能、中英文详情共254份；原始来源与迁移前工作稿逐字节一致；候选导出734条，均未准入训练。
- 迁移后的事件脚本使用显式外部路径重新执行，18 项核对通过；读取保存的 Gem JSON，不重解析二进制，也不覆盖已提交的历史结果。
- 已初始化的空临时工作区 doctor 通过，验证比赛数为0；这不是八场回放审计。
- 学习页面重新生成；相对路径检查通过。精确计数和来源范围见[本轮记录](../knowledge/maintenance-verification.json)。

本轮改动不触碰新比赛采集／固定回放回归的配置触发路径。远端合并结果与 CI 以本轮 [PR #5](https://github.com/xrfc/dota2-timing/pull/5) 及精确提交的 Actions 为准；知识说明和训练用途见[冷启动文档](knowledge-cold-start.md)。

## 历史主干验证（2026-10-09）

代码基线：[main / 725f35c](https://github.com/xrfc/dota2-timing/commit/725f35c25d74243a8ca52b17e7956107fd9dfa40)。PR #2 → #1 → [#3](https://github.com/xrfc/dota2-timing/pull/3) 依次合并，主干文件树与已验证的修复提交 `942ebfd` 一致；包版本仍为 0.4.0。

| 验证 | 结果与证据 | 边界 |
|---|---|---|
| 本地完整检查 | `python scripts/check.py`：122 项 pytest、10 项学习 Python、6 项 JS 全通过，Ruff 检查/格式通过 | 测试中的训练器是协议桩，不是实际模型 |
| 本地工作区 | doctor 检查 6 场 synthetic 比赛通过；4/1/1 观察快照，无模型或训练运行 | 合成闭环，不证明真实语义 |
| main 工程 CI | [37926671655](https://github.com/xrfc/dota2-timing/actions/runs/37926671655)：Linux Python 3.11/3.12、Chromium 浏览器检查、Windows portable 全通过 | Windows 不含真实 Gem 解析 |
| main 保存回放回归 | [37926671611](https://github.com/xrfc/dota2-timing/actions/runs/37926671611) 成功并保存回归制品 | 复用原 raw 导出，不是二进制重解析；绿色不解除训练 held |
| 固定证据留存 | 4 个原始制品 SHA-256/大小/ZIP CRC，8 场 demo 与 raw 哈希核验通过；8 场保存结果通过新身份校验 | 本地副本，不是异机备份；[留存清单](acceptance/7.41f-2026-10-06-preservation.json) |
| 合并触发的新比赛采集 | [37926671670](https://github.com/xrfc/dota2-timing/actions/runs/37926671670) 已主动取消 | 不属于本次分支整合验收，不用其结果代替固定样本 |

缓存修复先增加回归用例，最初 12 项中的 10 项在修复前失败；最终新增 18 项检查，覆盖 normalized 改动、清单缺失/旧版本、来源返回、跨玩家引用及合法/伪造英雄别名。更广的来源合并、迁移、资源管理并未因此完成。

真实数据仍为原固定批次 3 场机械审计通过、5 场隔离，完整训练准入保持 held；游戏画面对照和实际模型未完成。下一步是当前 main 对八场原 demo 在新工作区重解析并比较，再进行人工语义核验。以下 47、66、75、87 等数量及旧环境描述仅属于其注明日期的历史验证，不能当作当前结果。

## 1. 历史基线证据

| 层级 | 已有结果 | 结论范围 |
|---|---|---|
| 工程测试 | 全量 47 项通过，其中工作流 22 项 | 测试覆盖的契约、失败路径与文件操作通过 |
| 静态检查 | Ruff check、format --check 通过 | 风格与静态规则通过 |
| Linux CI | Python 3.11 / 3.12，安装 dev + replay，pytest、两个报告路径及 doctor 通过 | 这些环境可安装并运行现有测试/合成示例 |
| Windows CI | Python 3.12，安装 dev，工作流测试和 demo 通过 | 不含真实 Gem 回放解析或 GPU |
| 安装产物 | 本地 wheel 和 CLI 冒烟已通过 | 包入口可运行 |
| 历史真实回放 | v0.2 的 8822520406：10 玩家、362 购买事件及引用核对 | 历史购买解析证据，非本次重新解析 |
| 新位置/经济语义 | 尚未完成真实对照 | 不宣称新时序已通过真实数据验收 |
| 模型效果 | 尚无模型和独立评估 | 不报告准确率、胜率或决策改善 |

工程基线：[364d9ad](https://github.com/xrfc/dota2-item-timing/commit/364d9adf07373e925c9d420b5804403f866c432e)，[成功 CI](https://github.com/xrfc/dota2-item-timing/actions/runs/36997970952)。这是原基础设施基线的验证记录；后续修改的验证单独列出。

2026-10-02 文档核验：14 份 Markdown、99 个仓库相对链接、7 个 JSON 契约示例通过检查；24 次 CLI 调用通过，覆盖帮助、重复 demo、doctor/status、数据集构建、JSON 导入/去重/标注/事实复盘和旧报告入口。检查在临时工作区使用现有 Python 依赖执行，没有重新安装 Gem 或解析真实 demo。当时运行代码与上述基线一致。

2026-10-03 仓库整理核验：共享存储模块迁移后，工程 47 项测试及 Ruff 检查通过；学习生成器 10 项标准库测试和教学/个人记录规则 6 项 JavaScript 测试通过。所有当前 Markdown 相对链接与组件源码路径存在，正式包不包含学习代码。学习测试详见 [learning/](../learning/README.md)；该次云端环境禁止浏览器所需的进程通信，本地未完成真实浏览器核验；独立 Chromium 检查由 Ubuntu CI 执行，其结果以当次工作流为准。

## 2. 开发者复现命令

仓库根目录，Python 3.11+：

```bash
python scripts/bootstrap.py --replay --data --dev
python scripts/check.py
.venv/bin/python -m dota_items.cli report examples/match.synthetic.json --player-slot 0 --output reports/smoke
python coach.py --workspace coach-workspace/validation demo
python coach.py --workspace coach-workspace/validation doctor
python coach.py --workspace coach-workspace/validation status
```

Windows 的解释器路径为 `.venv/Scripts/python.exe`。只核对 JSON 工作流可省略 --replay；真实 demo 测试另需 Gem 和合法可用的回放文件。

期望结果：pytest 无失败；demo 的 dataset.split_matches 为 train=4、validation=1、test=1，report 路径存在，doctor.ok 为 true。重复 demo 应复用相同数据集 ID 并生成新的报告。实际源码与 CI 配置发生变化时，以当次检查为准。

## 3. 自动测试覆盖

| 测试文件 | 主要覆盖 | 没有证明的内容 |
|---|---|---|
| [test_pipeline.py](../tests/test_pipeline.py) | 首次购买、重复/赛前事件、缺失与非法值、HTML 转义、事实指纹 | 装备实际可用时间、统计建议质量 |
| [test_source.py](../tests/test_source.py) | 原响应缓存、错误 match_id、重试等待、错误不暴露 key | OpenDota 实时可用性和缓存完整性策略 |
| [test_replay_ingestion.py](../tests/test_replay_ingestion.py) | 压缩/头部/zip、购买适配、索引、缓存、批次继续 | 全补丁的真实 Gem 语义与解析性能 |
| [test_coach_workflow.py](../tests/test_coach_workflow.py) | 合成闭环、标签/筛选/比赛划分、去重冲突、搬迁/损坏、写锁、时序与证据、训练/登记/预测协议、超时/失败、未来引用拒绝 | 真正训练、全流程故障恢复、模型内部无未来泄漏 |

新增工程测试范围：

- [推荐契约](../tests/test_recommendation_contracts.py)及[推荐引擎](../tests/test_recommendation_engine.py)：输入与引用、支持范围、阵容替换、知识损坏、离线运行、报告转义；不证明独立推荐质量。
- [缓存与身份](../tests/test_cache_identity.py)：双输出完整性、热缓存来源、新 catalog 追踪、raw 玩家与别名绑定。
- [数据准备](../tests/test_data_preparation.py)：清洗、缺失与任务 mask、样本快照和 train-only 预处理。
- [真实验收](../tests/test_real_acceptance.py)：采集/审计规则与隔离；不能替代独立游戏画面对照。
- [观察上下文](../tests/test_observer_context.py)：上下文引用、可见性与截止时间边界。
- [训练准入](../tests/test_training_admission.py)：默认 held、样本/玩家/特征/任务绑定及拒绝路径。

模型测试通过临时脚本生成受控产物和预测，仅用于验证协议。没有深度学习训练，也不能把接口桩指标用于报告效果。当前自动测试不能替代真实 demo 的固定回归集。

## 4. 真实回放验收矩阵

每个样本至少记录原文件/demo/raw/normalized 哈希、parser/adapter/代码版本、补丁、平台、角色来源、核验记录。此矩阵区分“有导出”与“已人工确认语义”：

| 能力 | 当前状态 | 所需证据 |
|---|---|---|
| 购买 key/tick/引用 | 8 场 raw 引用审计；一场 346 条与 OpenDota 完全一致 | 其他比赛事件对照和人工游戏事件核验 |
| 购买漏检/合成/送达 | 未完成 | 独立人工事件集合，误检/漏检分母与语义分类 |
| 暂停感知时钟 | 真实导出与 Gem 转换一致；发现暂停边界状态冲突 | 暂停前/中/后的游戏画面核验及冲突处理规则 |
| 位置与坐标语义 | 导出/受控测试通过；真实待验 | 坐标、时间、死亡/复活与采样覆盖对照 |
| gold / net_worth / 补刀反补 / xp_progress | 已有真实分钟对照，存在数值差异与 XP 语义冲突 | 采样边界、游戏 UI、XP 语义及缺失片段 |
| 截断/不完整回放 | 部分提示；资格规则未实现 | 完整/缺失/截断样本和训练排除结果 |
| 跨补丁/平台 Gem 能力 | 未形成矩阵 | 精确版本和范围逐项记录 |
| 真实模型复盘 | 未实现 | 独立评估、错误案例与适用范围 |

模板见[操作指南](workflow.md)。先选择有权使用的少量固定回放发现问题，再扩样本；“看了 20 条没有异常”不能作为总体准确率或完整性结论。

## 5. 交付验收

2026-10-03 新增的数据准备学习任务见 [L01–L12](../learning/docs/roadmap.md)，逐场/逐样本的正反例要求见[开发流程验收矩阵](../learning/docs/development-workflow.md)。这些是学习任务的完成条件，不包含在历史 47 项或当前 122 项工程测试通过的声明中；填写模板也不代表执行了验收。

### 当前基础设施交付

- 快速开始在干净环境能复现，输出明确标为 synthetic。
- 导入失败保留逐文件结果，重复比赛不增加新工作区逻辑样本数。
- 固定数据集保持比赛级 split 与文件指纹；修改源标签不改变旧快照。
- 训练/预测未实现时模板失败并说明原因；不能伪造成功产物。
- 运行失败保留配置/日志，失败 run 不允许登记。
- 预测引用不得来自另一玩家、整局汇总或决策之后。
- 文档标明 doctor、旧缓存和模型适用性检查的边界。

### 下一轮可靠性出口

还需完成：真实字段验收、质量覆盖与完整性状态、完整来源/环境清单、解析限额、故障注入、陈旧任务识别、备份恢复演练。细化任务见 D01–D11、V01–V04。

### 模型阶段出口

定义任务和数据窗口后，保存同一快照上的基线比较、独立测试、校准/缺失子组表现和按比赛计算的不确定性。模型产物登记成功不能代替这一出口。

## 6. 文档和变更检查

纯文档变更核对以下内容即可，不为文字增加镜像实现的测试：

1. 所有仓库相对链接和代码路径存在；历史外部链接明确版本。
2. 非占位命令在临时工作区运行，预期输出字段与退出码正确。
3. JSON 格式示例与 Pydantic 契约或导入校验器一致。
4. 标清真实数据、适配器路径、dataset/run/model ID 等必须替换的占位值。
5. 完成度、任务状态、接口版本、CI 证据保持一致；已知缺口不写成已实现。

运行行为变更时按相关风险增加有意义的正反例测试，并执行项目要求的静态/自动检查。数据/schema 变化需说明迁移与回退；提交到开发分支，不把 CI 通过等同自动发布或合并。
