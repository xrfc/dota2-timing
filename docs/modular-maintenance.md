# 单模块维护与长期扩展（2026-10-17）

## 2026-10-28架构整理原则

保持模块化单体，不拆微服务、不按文件行数机械搬迁。当前职责分为：

| 层 | 现有位置 | 边界 |
|---|---|---|
| 来源提取 | sources | 解析实体与版本；不反向依赖data |
| 证据/投影 | data | 时序、身份、可知性、质量；不负责行动策略/训练 |
| 契约/传输 | contracts、handoff | 版本与只读包校验；不隐式执行审计/训练 |
| 学习/推理 | modeling | 消费批准快照；预测不加载训练依赖 |
| 用例编排 | workflow、experiments | 协调下层；整局实验已下沉，决策打包仍有脚本债务 |
| 展示/入口 | scripts及其assets | CLI/HTTP/展示；不把页面完成写成模型完成 |

`decision_review.py`的build与make_handler目前仍同文件，不声称已完成业务下沉。后续拆分先设计兼容导出、实现指纹清单与测试替身迁移，再迁移用例；旧包和旧哈希不回写。新代码不得继续向该脚本增加训练或策略。`data.replay_viewer`为只读证据投影，HTTP留在scripts。

模块scope现在对整个scripts目录做静态lint/格式检查（不执行脚本），避免跨模块编排漏检；pytest仍按既有归属运行，全量检查仍是最终工程门禁。
状态只在总路线/数据/模型三份主文档维护；其他长期文档不再粘贴每轮状态广播。日期证据保留原时点语义。

---


> 2026-10-27目标同步：新工作围绕位置＋装备决策复盘，但不把data.replay_viewer扩成训练或最优策略引擎。data负责可知证据与质量原因，modeling负责学习，应用层负责卡片和事后解释隔离，contracts的新增版本需先确认。任务顺序见[总路线](roadmap.md)。

2026-10-20：任务/特征默认定义移至标准库 `contracts.tasks`，`modeling.specs`
保留兼容导出与模型校验。新增 `data.task_snapshot`，不改历史 /1 生产者。
共享任务回归同时加入模块专项；接口和 /2 兼容规则见[任务契约](task-contracts.md)。
下文“仅默认规格”仍成立；新契约只登记既有任务，不接受任意研究配置。

2026-10-18续接：evaluation增加已观测二值标签、有限概率、组ID及bootstrap参数校验；不执行真实评估，合法历史数值保持parity。API及未知标签处理见[模型基础](model-foundation.md)。

## 收尾更新：公共读取接口（2026-10-17）

此前保留的私有读取耦合现已消除：公共API位于data.source_io，旧入口仅兼容包装。
当前生产者代码可以演进；旧数据/快照保持原字节。精确旧生产者复现与显式兼容重建必须区分。
登记迁移和公共交接的新入口见[公共读取接口](public-source-reader.md)。下方凌晨验收为历史阶段。


2026-10-22：整局实验脚本已拆为experiments.whole_log与modeling纯统计，
命令兼容、维护边界和验收见[实验层维护](experiment-maintenance.md)。

本文是当前工程结构入口，替代10/16架构审查中的“待拆分”描述；旧文档保留历史验收。
下列10/17重构授权与验收为历史记录；当前协作按AGENTS和并行协议执行，不再要求其他开发者停写确认。
保持单仓库、单Python包、现有环境和分支；不新增真实训练、选模、数据用途或划分授权。

## 1. 模块职责与依赖

~~~text
CLI / scripts（参数与兼容）→ experiments.whole_log（整局实验编排）
workflow（其他任务编排）
  ├─ data（清洗、证据验证、审计、冻结快照）→ sources / contracts / storage
  ├─ handoff.bundle（只读包完整性检查，标准库，无审计依赖）
  └─ modeling
       ├─ specs / batch：任务、特征约束和快照适配
       ├─ training → estimators：逐目标mask、支持数、固定参数拟合
       ├─ artifacts：严格JSON制品校验、读写
       ├─ inference：公式预测，不导入sklearn
       ├─ evaluation：指标与整玩家组bootstrap，不训练或选择split
       └─ foundation：旧导入路径兼容门面
sources → contracts / normalize / storage（不再反向导入data）
recommendation → 自有契约与规则（不调用训练模型）
contracts → 标准库（不得导入业务层）
~~~

箭头是代码调用，不是数据流。数据流仍为：来源→数据处理→冻结快照/交接包→模型→独立制品。
包读取只核验文件清单、路径、哈希和外层schema，不认证来源、训练许可或完整特征语义。
模型输入语义由batch.adapt_snapshot检查，来源重建由数据侧负责。

| 修改目的 | 首选模块 | 不应隐式执行 |
|---|---|---|
| 增加来源适配 | sources | 模型训练、自动采集 |
| 清洗或来源核对 | data、data.validation | workflow反向依赖、覆盖冻结证据 |
| 上下文格式 | contracts.replay_context | 引入Gem依赖、推断缺失通道 |
| 交接包读取 | handoff.bundle | cohort审计、训练 |
| 快照适配 | modeling.batch | 重划分、用validation/test补词表 |
| 新算法 | modeling.estimators | 数据采集、自动选模、test评估 |
| 模型加载/校验 | modeling.artifacts | 自动修复、重训、pickle |
| 阵容预测 | modeling.inference | 导入训练库、宣称最佳出装 |
| 指标/不确定性 | modeling.evaluation | 自动挑选数据、阈值或模型 |

共享接口仍按[协作协议](handoff/parallel-development.md)串行修改。
可单模块维护指职责、直接导入和专项检查，不意味着Git index/环境物理隔离，或拆为多个发行包。

## 2. 已落地拆分

- foundation.py原527行，拆为batch、specs、training、estimators、artifacts、inference、provenance及局部标量校验。
  foundation保留旧公开入口，fit_model延迟调用训练。
- training仅接受train，逐装备mask过滤，单类别/全未知保持untrained；两模型使用fit_parameters协议。
  逻辑回归C网格、solver、收敛失败、随机状态和无class_weight语义未变。
- 预测保留原NumPy公式，加载/预测不导入sklearn；环境仍共用原extra，未提供独立推理安装包。
- workflow.validation是兼容导出；实际来源验证在data.validation。
  data.pipeline/acceptance不再依赖workflow。
- 上下文格式、导出和纯校验下沉contracts.replay_context，有限数检查在contracts.numeric。
  data.context保留清洗/外部证据核验；sources不再导入data。
- cohort_handoff保留审计和旧读取名称的兼容导出；读取实现在handoff.bundle。
  新调用者直接导入后者，旧cohort导入仍会加载审计依赖。
- evaluation独立提供指标与分组bootstrap；历史purchase_baseline字节保持不变。
  旧run_experiment包含训练、验证选参和test评估，不是新训练入口；指标兼容副本有parity测试。

## 3. 有边界的扩展接口

TaskSpec固定记录当前英雄、标签语义、装备顺序、时间窗；FeatureSpec记录编码版本、train拟合和unknown规则。
当前仅启用默认规格，不是允许任意配置切换任务的框架；未知任务、模型或schema明确报错。

新增模型流程：
1. 在estimators实现fit_parameters(x, y, c=..., solver=...)；该协议覆盖已有两种表格模型，
   不承诺神经网络无需扩展参数或批处理协议。
2. 在显式选择器声明family，不做动态扫描、外部插件或隐式回退。
3. 同时扩展训练参数、制品校验和推理分发；复杂权重采用显式新schema和读取器，
   不强塞进逻辑回归系数字段，不开放任意对象反序列化。
4. 用合成fixture验证mask、未训练状态、保存加载、独立进程预测及失败无写入；保留频率对照。
5. 研究协议确认后才能真实训练/选模；软件支持不等于模型效果验证。

新增英雄、装备、窗口或标签：先确认研究选择，再发布任务/快照和适配器版本。
新增embedding：版本化词表、列序和unknown，训练/预测同源，不改写旧multi-hot含义。
暂不引入微服务、数据库服务、插件系统或通用深度学习调度器。

## 4. 兼容与证据

### 模型

继续使用purchase-foundation-model/1，JSON预测语义未变。实现清单接受两个明确集合：
历史四文件清单、新模块化清单，定义在modeling.provenance。缺少两项扩展字段的早期制品仍可读；
不完整/额外清单、部分字段或摘要失配仍拒绝。新制品使用新清单，旧implementation_sha256仍对应foundation，
不能单凭该门面哈希判断新实现身份，应核对完整bundle。
加载只核对记录内部一致性，不要求历史源码等于当前源码；哈希不是签名或真实性证明。
升级后向后读取兼容不等于双向兼容：旧读取器不一定接受新清单。

### 数据与回放

凌晨重构时旧952快照绑定的13项实现哈希不变；上午公共读取迁移后，当前实现已变化，旧快照内的历史哈希不改写。标签、词表、split和样本均不变。
本轮重建已有队列审计，新旧差异仅cohort生产者哈希；统计、类型、顺序及研究边界完全一致。
旧包保持原字节，新包写独立目录；不生成新增1,038场建模快照。
回放适配器升级gem-adapter/3.1，指纹覆盖下沉后的context/numeric，清洗接受3.0和3.1。
旧缓存不能冒充新实现结果；新解析使用独立输出。本轮仅合成回放回归，未真实demo重解析或客户端核验。

### 明确保留的兼容债务

- 凌晨保留的feasibility私有读取依赖已在上午收尾消除，当前使用source_io；
  旧实现记录通过public-reader/1显式迁移校验，详见顶部说明。
- 冻结编码/指标与新模块存在少量兼容副本，由parity测试约束，不能各自任意演进。
- 依赖尚未完整锁定，data extra仍含模型依赖；本轮不安装/重建环境或改变发行接口。

## 5. 独立维护与验证

复用现有环境，在根目录运行：
~~~bash
.venv/bin/python scripts/check.py --scope modeling
.venv/bin/python scripts/check.py --scope data
.venv/bin/python scripts/check.py --scope recommendation
.venv/bin/python scripts/check.py
~~~
Windows使用.venv/Scripts/python.exe。
模块scope包含对应源码/测试的lint、格式检查、pytest及架构测试；data包含回放/workflow集成。
脚本和公共文件的完整检查仍以all为准。测试归属维护于scripts/check.py，新增测试应检查所属scope。
专项不是全量验收；全量串行执行并比较源码（含未跟踪文件）前后指纹，不需其他开发者停写确认。
架构检查覆盖绝对、相对、函数内import；独立进程阻断验证推理不加载训练库、读取不加载审计。
静态检查不能识别任意动态导入，模块测试也不能代替集成验证。

## 6. 文档和恢复

结构与维护以本文为准；语义见[模型基础闭环](model-foundation.md)、[数据交接协议](handoff/purchase-data-interface.md)。
[项目状态](project-status.md)、[验证交付](validation-and-delivery.md)只记录实际结果。
带日期历史验收保留并标明替代关系，不改写冻结reports中的INTERFACE快照。
起始源码/文档归档：reports/refactor-2026-10-17/source-before.tar.gz及source-before.json；
学习开发指南原文另存learning-development-before.md；既存data/reports指纹：protected-before.json。恢复时先解到独立暂存位置核对，再逐文件合并；
禁止整库覆盖或git reset丢弃原有未提交开发。本轮不提交、推送或远端合并，本地归档不等于远端备份。

## 7. 本轮验收

全量679项通过，模块scope分别data388/modeling186/recommendation115（含重复公共测试）。
7,656项旧产物不变，新旧合成模型一致，文档链接检查0失效；完整边界见[验证记录](validation-and-delivery.md)。

## 8. 整局实验编排（2026-10-22）

experiments位于data/modeling之上，可协调两者；data、modeling、sources、contracts、handoff、recommendation均不得反向依赖experiments。scripts只提供整局实验CLI及旧导入兼容，业务实现不回调scripts。通用I/O辅助不统一不同任务的收据schema，完成顺序仍由各流程严格控制。

新整局实验测试归入modeling scope，纯统计、编排源码及架构回归同查；最终仍以串行全量检查为准。旧§7的679项是历史记录，不代表本轮结果。

## 9. 当前维护入口（2026-10-26）

- `data.tick_alignment`：纯tick关联，保守输出全知与阵营行；不读文件、不训练。
- `modeling.lineup_analysis` / `lineup_comparison`：只读冻结模型分析与A/B贡献；HTTP/HTML命令在scripts，不改推理或训练协议。
- [脚本导航](../scripts/README.md)：现有入口按用途分组，保持路径兼容；固定审计脚本暂保留其证据编排，不为目录美观搬迁哈希绑定实现。
- 新增两个阵容测试归入modeling scope，避免默认落入data。公共检查和最终集成仍运行all。
- [全部文档分类](README.md)：主流程、接口、操作、日期证据、历史快照分层；旧源码/文档路径不批量移动，不触碰冻结输入。

本轮只有文档导航、归属和忽略规则整理；不声称完成所有脚本业务下沉。复杂脚本后续如重构，应单独处理兼容入口与生产者指纹迁移。

### 数据侧地图回放器

`data.replay_viewer`只读校验及视角隔离帧投影；`scripts/replay_viewer.py`为HTTP入口，`scripts/replay_viewer_assets/`为前端。依赖现有data.source_io，不依赖workflow/modeling。API与局限见[回放器说明](replay-viewer.md)。

### 数据侧决策案例证据（2026-10-27）

data.replay_status为纯展示分类；data.decision_evidence提供只读同tick、同身份友方库存与阵营位置证据，不含行动策略或训练。scripts/decision_review.py及decision_review_assets消费固定人工案例并提供独立本地评审页，后续文件仅主动展开。接口、命令、专项和未完成验收见[交付说明](data-decision-cases-2026-10-27.md)；新Python测试按既有默认归属data，新Node检查在统一检查集成补丁中登记。

### 增强案例来源附录（2026-10-27）

data.decision_context为纯投影，不读文件或实现行动策略，严格排除未来事件、敌方隐藏眼/雾和完整团战结果。scripts/enhance_decision_cases.py复用公共读取及DecisionEvidenceStore，校验来源/旧包/时钟字节，把未认证附录与原decision_input隔离。行动条件来自独立人工修订，不进入data策略；增强页复用兼容的decision_review_assets。新测试按既有默认归data；不改共享contracts/handoff。操作、API边界及研究未决项见[字段清单](decision-field-readiness-2026-10-27.md)与[任务草案](decision-training-task-draft-2026-10-27.md)。

### 独立现场探针与状态卡（2026-10-27）

sources.decision_state_capture只依赖标准库和传入的解析器实体；不依赖data/workflow，不修改历史gem_capture或默认缓存键。data.decision_state为纯投影，按唯一原生tick和实体身份对照旧raw，丢弃未来样本；sources不反向依赖它。scripts/probe_decision_state负责冻结原两场计划、fresh-process兼容解析器与完整收据，scripts/build_decision_state_cards负责只读打包。专用/1 schema不是共享contracts或ML task_id，未改数据/模型交接协议。完整API、操作和验证见[状态卡交付](decision-state-card-2026-10-27.md)。
