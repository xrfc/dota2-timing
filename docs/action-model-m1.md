# 行动模型 M1：版本契约与纯推理

2026-11-26。用户要求先补齐多版本设计，再继续M1并自行校验。前置[设计PR #52](https://github.com/xrfc/dota2-timing/pull/52)已更新至`f4407fb2359ad3e2980274dfa86d21125ce85402`；[固定设计文本](https://github.com/xrfc/dota2-timing/blob/f4407fb2359ad3e2980274dfa86d21125ce85402/docs/action-model-migration-design.md)§5.4定义版本身份、兼容矩阵和支持周期。本实现分支从`origin/main 90353ea`独立建立，不包含其他未合并PR，不把分支单独通过当作合并后组合验收。

M1范围：契约、已拟合状态及无拟合预测、行动估计、按身份合并的事后评价。新库使用合成样本对照固定旧源码；真实模型反序列化/转换、训练编排、制品加载器和应用接入分别留到M2–M4。真实兼容矩阵为空，没有宣布任何新补丁模型有效。

## 1. 模块与边界

| 模块 | 归属 | 公开职责 |
|---|---|---|
| `contracts.artifact_versions` | 共享、标准库 | 不可变版本身份、兼容记录、`validate_matrix`、`resolve`；无I/O |
| `contracts.action_outcomes` | B线、标准库 | `task_spec`、`DecisionKey/DecisionInput/ObservedOutcome`、输入维度与观察字段校验 |
| `modeling.awareness.action_features` | B线 | 固定特征编码、已学缩放、序列输入与窗口构造；没有fit |
| `modeling.awareness.action_models` | B线 | ActionMeans/TreeOutcome/BehaviorReference/SequenceOutcome状态、导出/重建、`predict_outcomes/predict_behavior` |
| `modeling.awareness.action_values` | B线 | 三domain的已拟合行动价值状态、`estimate_actions`、支持原因与取舍 |
| `modeling.awareness.action_evaluation` | B线 | keyed join、事实指标与分组汇总、参考模型评价；未来结果仅在本层加入 |

方向为features → contracts，models/values → features，evaluation消费预测与独立观察。新包不导入scripts/data/sources/experiments/workflow，不提供拟合入口；共享包`__init__`不重新导出B线。树与Pipeline的预测可使用已有sklearn后端，纯序列路径不加载`scipy.optimize`。这不是独立发行的无sklearn推理环境。

## 2. 版本身份与兼容判断

`ArtifactIdentity`保留schema、manifest/载荷、模型家族、原生产者源码/环境、task/features/labels/split契约及来源游戏上下文。`RuntimeIdentity`另记消费者源码/环境和读取契约；代码升级不回写旧身份。`GameContext`分别保存patch/build证据等级及解析器、地图、机制摘要；日期推断是`time-inferred`，不能变成`build-confirmed`。

矩阵中的每条`CompatibilityRecord`只批准一个完整`CompatibilityRequest`，包含精确工件、运行时、目标上下文和能力。调用方提供可信矩阵及显式带时区的`as_of`，`resolve`不读系统时钟、不寻找latest、不自动迁移或回退。

| 能力/状态 | 允许条件 |
|---|---|
| `historical-reproduction` | 目标上下文与原上下文完全相同；可保留原先未知版本身份，不把它认证成已确认 |
| `research-prediction` | 目标版本不能unknown，可显式time-inferred；另有目标验证证据，保留其证据等级 |
| `product-advice` | 目标须build-confirmed，且有对应目标验证证据；结构等价不足以批准产品建议 |
| `supported` | 仍须validated、请求能力对应、未撤销且在有效期内 |
| `reproduction-only` | 仅历史复现 |
| `retired` | 停止运行，保留记录 |

支持区间为`[starts_at, review_by)`，边界到期即拒绝；没有默认年限或“最近N补丁”的承诺。未知组合、重复ID/重复请求、未验证、撤销、到期、环境/语义/消费者摘要不匹配均拒绝。新消费者可另加精确兼容记录，原工件保持原身份；不能仅凭schema相同放行。矩阵更新保留历史快照，在新矩阵内不容纳多个竞争条目。

**边界：** 本模块只能校验结构、摘要格式和精确匹配，无法证明摘要所指证据真实。M3读取层核对实际载荷、源码、环境与证据字节后才能提交可信矩阵；不能相信工件自报validated。`REAL_COMPATIBILITY_MATRIX=()`，合成测试不会注册真实支持。低层数值API不承担发布授权，后续应用必须显式执行兼容判断。

## 3. 输入与研究语义

| 项目 | 固定内容 |
|---|---|
| 动作 | wave：farm/retreat；jungle：continue_jungle/leave_camp；support：approach/stay |
| 特征 | wave静态7列、其余10列；序列每帧7列；保留原列序及缺失规则 |
| 历史 | t−10、t−5、t；末帧模型兼容前两帧为空，序列模型仍拒绝不齐的三帧 |
| 窗口 | 原动作(0,6]秒、结果(6,20]秒；gold是现金余额t+20−t+6 |
| 结果 | hits/death/gold/xp/dead_seconds，support另有arrival；不改为B5分类实收 |
| 划分 | lane-study-v1整场五折；真正fold归属、人口和留出核验仍由后续读取层负责 |

`DecisionInput`只含`DecisionKey(match,hero,t,domain)`、static和sequence。`to_features()`只导出数值白名单，match/hero/t/domain不自动加入数值特征。候选动作由`predict_outcomes`显式提供，行为预测不接受观察动作。`ObservedOutcome`另存fold、观察动作、结果及评价分组信息；构造合法不代表来源或真实fold已核验。

正式typed入口执行登记任务的维度校验；低层模型`.predict(rows)`为兼容数值测试保留小维度白名单字典接口，不作为制品/数据可信校验。未知动作、空输入和常量分支按旧家族保留，不统一成新行为。新状态校验拒绝不合法形状和非原三步Pipeline；FeatureScale显式拒绝错误维度广播。这些是损坏/错配输入的拒绝，不修改有效旧状态数值。

预测生成时绑定四元身份；评价join拒绝重复、缺失、多余和错域键，不按观察表位置匹配。同场fold需一致，但不在此重新划分。训练侧mean是模型统计，可随预测绑定；实际未来收益只在join后参与指标。观察性行动比较仍不等于因果效果或已验证推荐。

## 4. 验证与复现

[来源基线](acceptance/action-m1-baseline.json)记录设计与旧来源身份；本轮重新核验7个固定head共182个来源条目，零失配。旧来源固定为PR #34的`7ca2ae3d14edae67042634f820a9456827d78ce1`。`tests/fixtures/action_legacy/`保存完整源码文本及摘要清单，CI不依赖旧Git对象或网络；测试独立子进程执行原预测代码。values文件因含读写/训练入口，仅从已验证完整文本原样提取纯函数，不能以新实现充当旧基准。

仅手工构造合成状态和后端；测试准备和推理都不调用fit/minimize。树/Pipeline手工设置的可预测属性与序列参数用于验证本环境运行路径，不能代替真实旧工件的类型核验。固定环境下比较状态dtype/shape、预测数值、NaN/None、未知/支持原因及边界错误；不以容差放宽掩盖迁移差异。

专项命令：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_artifact_versions.py tests/test_action_outcomes_contract.py \
  tests/test_model_action_models.py tests/test_model_action_values.py \
  tests/test_model_action_architecture.py tests/test_architecture.py tests/test_check_scopes.py
```

版本/任务契约测试同时纳入data、modeling、recommendation三个scope；旧baseline/sequence/outcome_values的后继测试明确归modeling。最终仍串行执行`scripts/check.py --scope all`，含未跟踪源码的前后指纹必须一致。验收日志目录`reports/action-m1-20261126/`；最终结果随实现PR提供。独立复核记录为`reports/action-m1-20261126/review.json`，绑定两契约和四模型源码；185项核心专项独立复跑通过，发现并修复NumPy预测标量到评价接口的衔接问题，另验证缩放宽度和固定Pipeline拒绝边界。六项M1交付已完成，后续真实准入仍不激活。

## 5. 后续

M2实现训练与编排、已登记样本读取，仅执行合成拟合回归；M3实现制品核验与显式转换，补实际旧类型、来源/环境和本次预测等价；M4接应用并执行兼容门禁。按比赛选择历史地图/机制组合及支持周期的运营登记仍未接入现有页面。

新游戏补丁要分别检查解析、输入覆盖及模型效果。是否跨补丁合并训练、重训或改标签仍是研究决定，不由本次结构迁移默认批准。旧模型、冻结来源及一次性评估标记不改；原337场已评分，不能再充当新的独立验收。
