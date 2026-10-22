# 模型流程与开发

更新：2026-10-23。模型方向唯一持续维护的流程、现状、决策和后续任务文档。
输入以[数据流程](data-prep-progress.md)为准，优先级见[项目总路线](roadmap.md)。

## 1. 目标与输入边界

研究开局阵容能否为主宰整局11装备日志出现提供超出训练频率的预测信息。行为概率不是推荐收益、最佳装备组合或购买顺序。
冻结输入1990场、1592/398开发划分、256维、11装备；允许玩家重叠，全部至少30分钟，没有独立test。验证已反复用于开发，新对照不算独立泛化证明。

## 2. 全流程与模块职责

1. **协议**：看结果前记录数据身份、候选、固定参数、指标、停止规则及授权；实现默认值不冒称用户决定。
2. **验证**：CLI调用experiments.whole_log核验来源、收据、成员和任务；modeling.batch适配X/y/mask，modeling不依赖data生产者。
3. **拟合**：training仅接受train，按目标mask调用estimators；未知不填负例，单类别不伪造可训练模型。
4. **制品**：artifacts严格校验JSON，记录来源／实现指纹、参数、依赖、支持数和收敛；旧产物不覆盖。
5. **预测**：inference使用保存参数及相同列序；加载／预测不导入训练库，任务不匹配拒绝。
6. **评价**：逐装备／宏Brier为主，AP和AUC辅助，train/validation均报告；准确率不能替代概率评价。
7. **诊断**：只读重算保存预测；固定10等宽箱、平均偏差、概率方差及错误贡献，不在验证上拟合校准器后报告同集提升。
8. **结论**：保留全部候选、检验假设，不自动选线上模型；组合、顺序和推荐质量另行验收。

## 3. 已完成实验与结论

2026-10-21获准并完成frequency＋C=1对照及后续只读诊断。2026-10-22用户明确授权后，C=0.1、0.01真实对照与只读复算已完成，见§11。
固定L2、liblinear、max_iter=2000、random_state=0、class_weight=None；频率取train有效标签正例比例。

| split／指标 | frequency | C=1 logistic |
|---|---:|---:|
| train宏Brier↓ | 0.138313 | 0.108708 |
| validation宏Brier↓ | 0.136269 | 0.142712 |
| validation宏AP↑ | 0.390818 | 0.448987 |
| validation宏AUC↑ | 0.500000 | 0.590995 |

只有分身斧、金箍棒验证Brier改善；排序提高不等于概率更准，不能宣称整体胜过频率，也不能断言阵容无价值。
A杖预测75.3%的57场实际49.1%；冰眼预测5.2%的169场实际14.2%。平均偏差不大但分段偏差明显。跳刀、A杖、冰眼的概率方差未获得足够标签协方差抵消，支持“概率区分过强／估计不稳定”的待检验假设，不证明唯一成因。
精确恒等式：Brier=Var(p)+bias²−2Cov(p,y)+Var(y)，分母均为n；分箱ECE不是精确Brier分解。

证据：[固定实验](whole-log-baseline-2026-10-21.md)、[诊断](whole-log-calibration-2026-10-21.md)；本地产物reports/whole-log-fixed-baseline-2026-10-21/及reports/whole-log-calibration-2026-10-21/。本次文档整理未复算历史实验。

## 4. 当前接口与复用边界

- fit_model已接受C=0.01、0.1、1、10；软件能力不等于这些实验均已授权。
- scripts/run_whole_log_experiment.py保持旧C=1命令协议；run_whole_log_regularization.py独立承载两个C。实现迁至experiments.whole_log；旧导入路径保留兼容。
- scripts/diagnose_whole_log_experiment.py继续严格读取whole-log-fixed-experiment/1；新report_whole_log_regularization.py使用独立whole-log-regularization/1，并调用旧基线校验，不放松旧校验。
- modeling.whole_log_diagnostics／whole_log_comparison负责纯统计；experiments.whole_log负责I/O、收据与发布；scripts只保留CLI及兼容导出，foundation保持兼容门面。
- 旧purchase_sensitivity包含两个solver、四个C及逐装备选模，不能直接作为本轮两个C方案。

已有固定输入只读核验（占位output须不存在；--verify-only不写输出、不fit）：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_whole_log_experiment.py --parent reports/cohort-random-v2-2026-10-21 --cohort reports/cohort-whole-log-11-2026-10-21 --output reports/verify-only-unused-placeholder --verify-only
```

历史执行命令见实验记录，不为文档整理重跑。详细API、inspect和制品兼容见[整理前技术记录](archive/2026-10-22/model-foundation.md)、[模块维护](modular-maintenance.md)。

## 5. 任务状态（工程完成不等于真实训练授权）

| ID | 前置 | 工作与交付 | 验收标准 |
|---|---|---|---|
| MODEL-01 **已完成** | DATA-01已完成 | 在本文固定两个C的实验协议 | 只新增0.1、0.01；其余设置不变，复用frequency/C=1，不自动选模或扩大搜索 |
| MODEL-02 **已完成** | MODEL-01 **已完成** | 扩展脚本编排和候选身份 | 协议先写、complete最后写、独立输出；来源失败不拟合，旧入口兼容 |
| MODEL-03 **已完成** | MODEL-02 **已完成** | 多候选只读比较报告 | 四组完整对齐；逐装备／宏指标、系数范数、截距、概率波动与固定分箱；篡改拒绝 |
| MODEL-04 **已完成** | MODEL-02/03 | 合成回归及运行准入核查 | 只train拟合；修改验证标签不改固定模型；拒绝覆盖／失败发布；收敛警告致失败 |
| MODEL-05 **已完成** | MODEL-04及运行确认 | 一次执行两组真实C | 新22个二分类拟合，不重训旧基线；保存资源、指纹，不追加搜索／校准 |
| MODEL-06 **已完成** | MODEL-05 **已完成** | 只读复算与假设复盘 | 预测／指标一致，对比两个基线，保留全部候选，不逐装备拼赢家，更新L14–L16练习 |
| MODEL-07 | MODEL-06及DATA-02 | 独立评估及后续模型方案 | 明确时间／补丁／重叠和新数据用途；不把开发改善当推荐有效 |

主看验证Brier；差距仅因训练变差而缩小不算成功。C越小L2越强，系数不保证按倍数缩小。liblinear也惩罚截距合成特征，须检查平均偏差，不能保证概率向训练频率收缩。
仅优于C=1不如frequency，只说明收缩有帮助；两者都优于才支持当前开发集概率收益。两个候选均无改善则停止继续试C，先审查特征与支持；深度模型不是自动下一步。

## 6. 学习与更新规则

L13频率 → L14逻辑回归／正则化 → L15概率和排序 → L16诊断与假设 → L17建议质量。
[个人任务](../learning/docs/roadmap.md)、[基线练习](../learning/docs/whole-log-baseline-lab.md)、[诊断练习](../learning/docs/calibration-lab.md)记录理解，不复制工程进度、不自动勾选。
以后协议摘要、结果和MODEL任务只更新本文，长实验报告作为证据引用，不另开开发路线。

## 7. 当前交接入口（2026-10-22）

DATA-01已交付只读输入保护，命令、产物及边界统一见[数据主文档](data-prep-progress.md)。scripts/verify_whole_log_handoff.py复用来源重放及旧基线预测／指标复算，固定输入身份，记录training_executed=false。
MODEL-02必须在新候选拟合前及发布完成收据前调用read_handoff，并将交接记录哈希及identity_sha256绑定新协议；现已接入新训练入口：拟合前、候选间和完成收据发布前校验；默认只核验输入，本轮MODEL-05已获用户明确授权并完成；未来新增实验仍需相应授权。read_handoff检查文件未漂移，不是文件系统锁；候选仍只能用已验证的train批次。
MODEL-01至06已完成；下一步为MODEL-07／DATA-02独立评估方案决策，不重训旧基线。DATA-01历史68项专项及Ruff通过；本轮验证见§9，不等于全库验收。

## 8. 固定正则化协议（MODEL-01，2026-10-22）

本节在新候选结果产生前固定：最初仅授权MODEL-01～04工程开发；2026-10-22用户追加明确授权两组真实C对照，按本协议完成MODEL-05／06。

- 唯一新增候选：logistic_c0_1（C=0.1）、logistic_c0_01（C=0.01），每个候选11装备独立二分类；完整保留两组，不按装备拼接赢家。
- 原frequency和C=1制品只读复用、不重训。冻结1990场、1592/398、256维、11装备、原行序／标签／mask，未设置独立test。续采数据不进入本轮。
- L2、liblinear、max_iter=2000、random_state=0、class_weight=None，沿用现有默认fit_intercept=True、intercept_scaling=1；liblinear截距受惩罚。无标准化／重采样／校准器／额外特征。
- 主指标validation宏平均Brier（等权、越低越好）；并列报告train及逐装备Brier、AP、ROC-AUC、支持数和未定义项。固定10等宽校准箱，报告概率标准差、平均偏差、系数L2范数及截距。
- 两候选结束即停；收敛警告或输入漂移致失败，不发布complete。未知标签不补零；单类无模型，保留null与支持数，不静默缩小比较范围。
- 两组都不改善则停止试C；只胜C=1未胜frequency仅说明收缩有帮助；同时胜过两基线仅支持当前开发集收益，不宣称独立泛化或推荐质量。
- 拟合前／候选间／发布前核验交接；协议绑定handoff文件哈希和identity_sha256。真实运行需额外显式启用，不由工程开发自动触发。

## 9. MODEL-02～04实现、命令与验证（2026-10-22）

新增文件（旧实现／旧基线不改写）：

- experiments.whole_log.regularization：输入重放、协议、候选编排及严格结果复验；四组统计委托modeling.whole_log_comparison。scripts/whole_log_regularization.py为兼容导出，不新增依赖。
- scripts/run_whole_log_regularization.py：默认只读准入；只有显式--execute才进入拟合分支。
- scripts/report_whole_log_regularization.py：对已有两组候选及旧两基线只读复算，不调用fit或校准。
- tests/test_whole_log_regularization.py：合成数据贯穿协议→候选→结果→独立报告及故障注入。

### 默认只读准入（已执行，不创建output）

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_whole_log_regularization.py --parent reports/cohort-random-v2-2026-10-21 --cohort reports/cohort-whole-log-11-2026-10-21 --baseline reports/whole-log-fixed-baseline-2026-10-21 --handoff reports/whole-log-input-handoff-2026-10-22 --output reports/regularization-verify-only-unused
```

源重放、旧基线预测／指标、交接身份及保护文件核验通过，training_executed=false；身份仍为2ccbe366afacb9462605038605389739c409c550a516b66960febb97d56a3d83。没有创建上述占位输出目录。

### 真实运行（2026-10-22已授权并执行，结果见§11）

在上述命令中将output改为全新独立reports目录并显式加入--execute；没有可变C网格、solver或自动选模参数。必须先取得MODEL-05真实运行授权。
程序先写protocol.json，再拟合两个候选；每组保存model、train/validation逐行预测；report.json含四组全部指标、支持数、校准箱、系数范数、截距和相对两基线的差值。complete.json最后发布并绑定所有载荷哈希。
单类／无观测保留未训练状态及null；宏指标明确included_items，不允许四组定义域不一致后静默比较。失败目录留存、不自动覆盖；无complete不是成功实验，重试须用新目录。

### 真实结果产生后的只读报告（2026-10-22真实复验通过）

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/report_whole_log_regularization.py --parent reports/cohort-random-v2-2026-10-21 --cohort reports/cohort-whole-log-11-2026-10-21 --baseline reports/whole-log-fixed-baseline-2026-10-21 --handoff reports/whole-log-input-handoff-2026-10-22 --experiment reports/REPLACE_WITH_COMPLETED_REGULARIZATION --output reports/REPLACE_WITH_NEW_COMPARISON
```

报告核验候选C／solver、训练支持数、来源与输入身份、收据、逐行预测及全部统计；即使重写外层哈希，参数、预测或指标与固定协议不一致也拒绝。报告输出为JSON，便于复算与后续展示，当前未新增图形页面。
完整源码哈希和依赖版本绑定协议；旧实验仍按旧schema读取，未引入隐式迁移。哈希保护不是防并发写入的文件锁，也不能证明日志完整或推荐质量。

### 工程准备阶段的历史验证范围

当时仅合成训练，真实输入仅只读准入。覆盖默认不拟合、只有train参与拟合、验证标签扰动不改变模型、模型保存重读、两个C参数、四组报告复算、旧基线不写入、未知／单类、损坏输入／收据／参数／预测／指标拒绝、收敛告警致失败及发布前漂移阻断。
采集继续写独立data目录，未动采集器或共享环境，因此本轮专项结果不等于停写窗口下的全库验收。未真实训练、未提交、未推送。

本轮最终专项：87项通过（新增19项＋旧整局实验／诊断／交接／快照68项）；4个新增文件Ruff lint与格式检查、两入口--help及git diff --check通过。专项命令：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_whole_log_regularization.py tests/test_whole_log_experiment.py tests/test_whole_log_diagnostics.py tests/test_whole_log_handoff.py tests/test_whole_log_snapshot.py
```

## 10. 实验层结构整理（2026-10-22）

当前实现与职责见[实验层维护](experiment-maintenance.md)。本轮用户确认没有其他开发者，
允许单一执行者串行修改共享编排层、检查入口和架构文档；不扩大真实训练权限。

- `experiments.whole_log.inputs`：来源重放；`handoff`：身份绑定与只读交接。
- `baseline`：既有C=1协议；`regularization`：两个C的固定协议和执行／复验。
- `diagnostics`：旧基线只读复算；`io`：哈希保护、严格比较及独占JSON写入。
- `modeling.whole_log_comparison`：`rows_for`、`evaluate`、
  `compare(snapshot, models, *, candidates, rules)`；纯计算，不写文件或拟合。

CLI命令、schema、数据口径、参数、指标和完成收据的发布顺序保持不变。
旧脚本仍可导入公开函数；故障注入／monkeypatch应针对实际实现模块，不依赖脚本全局变量。
模型模块不得反向依赖experiments；新代码不得导入scripts。
旧产物原字节不变，新运行记录当前模块指纹，不能声称新源码等于旧源码。

迁移前四组合成模型的新旧比较统计完全相同。完整本轮结果见[实验层维护](experiment-maintenance.md)。
以上为结构整理阶段记录，当时未训练；随后用户授权的真实对照见§11。

## 11. 两组真实C结果（2026-10-22，MODEL-05／06完成）

用户明确授权“继续下一步，做两组C真实对照”；固定协议无变更，新22个二分类均完成。
旧frequency／C=1未重训，续采数据未进入本轮。完整逐装备、校准、系数／截距及命令见
[真实对照报告](whole-log-regularization-2026-10-22.md)。

| 模型 | train宏Brier | validation宏Brier↓ | validation宏AP↑ | validation宏AUC↑ |
|---|---:|---:|---:|---:|
| frequency | 0.138313 | 0.136269 | 0.390818 | 0.500000 |
| C=1 | 0.108708 | 0.142712 | 0.448987 | 0.590995 |
| C=0.1 | 0.120245 | 0.133160 | 0.449501 | 0.597017 |
| C=0.01 | 0.134652 | 0.136090 | 0.439617 | 0.580216 |

C=0.1验证宏Brier较frequency下降2.28%、较C=1下降6.69%；11项均胜C=1，5项胜frequency。
C=0.01仅比frequency下降0.13%，进一步收缩并未取得更好整体结果。
收缩有助于当前开发集概率预测，但不是越强越好；截距惩罚和平均偏差仍需区分，未做截距因果对照。
没有独立test、置信区间或显著性结论；不宣称推荐／胜率收益，不自动选模或逐装备拼赢家。

独立只读报告已复算一致，2014份保护文件及执行实现指纹不变；complete均已核验。
产物：reports/whole-log-regularization-2026-10-22/；
复验：reports/whole-log-regularization-comparison-2026-10-22/；
资源／执行源码／验收：reports/whole-log-regularization-evidence-2026-10-22/。
本轮无代码修改，因此不重复此前1071项工程验收；本次验证为真实执行、全结果复算与哈希检查。
学习练习已补充，不代用户完成个人学习验收。

下一步建议MODEL-07／DATA-02，先决定独立评估的时间／补丁／玩家重叠及用途；本轮不追加C、校准器或深度模型。


## 12. 本轮交付边界（2026-10-23）

本轮汇总既有实验与实现，不重训或重算选择新模型。C=0.1仍只是开发集候选，MODEL-07待决策。
新增采集和录像审计数据未进入模型输入；整批工程验收与GitHub交付以[交付记录](validation-and-delivery.md)为准。
