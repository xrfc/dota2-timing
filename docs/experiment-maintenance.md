# 整局实验层维护（2026-10-22）

本轮为结构整理，不改变1990场、原划分、256维、11装备、C候选或指标。
研究协议继续以[模型主文档](model-foundation.md)为准。

## 结构和API

```text
scripts：参数解析／兼容导出
  → experiments.whole_log：来源重放、协议、执行、复验、发布
      → data：来源和冻结快照读取
      → modeling：适配、拟合、预测、比较统计
      → experiments.whole_log.io：保护、独占写入、严格比较
```

| 模块 | 主要API | 边界 |
|---|---|---|
| experiments.whole_log.inputs | verify_inputs(parent, cohort) | 只读来源重放，不导入训练入口 |
| experiments.whole_log.handoff | verify、read_handoff、run | 身份和基线绑定，run只发布新交接记录 |
| experiments.whole_log.baseline | run_experiment、fit_comparison | 旧固定C=1协议；默认行为与旧入口相同 |
| experiments.whole_log.diagnostics | verify、run | 旧基线预测与指标只读复算 |
| experiments.whole_log.regularization | prepare、run、verify_result、report_run | 默认只核验；显式execute才拟合两个候选 |
| experiments.whole_log.io | load、check_unchanged、assert_equal、write_exclusive | 复用机制；不代替各流程的schema校验或收据发布顺序 |
| modeling.whole_log_comparison | rows_for、evaluate、compare | 纯计算；无I/O、拟合、数据模块或编排依赖 |

`compare`显式接收candidates和rules，生产调用仍只有原固定两个C，不增加CLI可调参数。
`load`沿用交接入口的重复键／非有限JSON拒绝及data.source_io；旧来源读取与诊断读取语义保持不变。
输入哈希保护和独占JSON写入复用同一实现；各schema的严格字段检查与complete最后写仍由各流程负责，
不强行合并成可接受任意收据的“万能验证器”。

## 当前和历史命令

所有命令仍从仓库根目录使用现有`.venv`执行，无新增依赖。完整参数见[模型主文档](model-foundation.md#9-model-0204实现命令与验证2026-10-22)。

| scripts入口 | 定位／默认行为 |
|---|---|
| run_whole_log_regularization.py | 当前下一步入口；默认只核验，真实训练仍须授权及--execute |
| report_whole_log_regularization.py | 当前两候选结果的只读复验与独立报告 |
| verify_whole_log_handoff.py | 当前输入交接保护；只读核验旧输入、独立发布交接记录 |
| run_whole_log_experiment.py | 历史C=1基线入口；默认会拟合，检查时必须--verify-only |
| diagnose_whole_log_experiment.py | 历史基线只读诊断，继续支持原schema |
| whole_log_experiment.py、whole_log_regularization.py | 旧Python导入兼容门面，不是新业务实现位置 |

旧命令参数、报告字段、schema和错误退出语义不变；旧公开函数导入仍指向同一实现。
模块全局变量注入不是兼容API，测试应patch实际实现模块。
不改更早30分钟／敏感性入口，不将它们当成当前整局任务命令。

## 证据与验证

源码迁移前归档位于`reports/experiment-refactor-2026-10-22/before.tar.gz`。
恢复时在独立目录解包并逐文件核对，不覆盖其他未提交工作。
`protected-before.json`记录旧输入、旧基线、交接文件共2014份指纹。
新运行的实现清单覆盖src下真实模块；历史协议内的源码指纹保留，读取历史结果不要求当前源码相同。
没有修改模型制品的实现清单格式或放宽哈希校验，也没有迁移／重写历史产物。

迁移前已验证四组合成模型的新旧比较结果完全相同；专项测试继续覆盖验证标签扰动不影响拟合、
训练集限定、拒绝篡改、收敛失败、输入漂移、失败不发布complete以及只读报告。
新增测试覆盖旧导入函数身份、5个CLI帮助、脚本反向依赖、实现指纹覆盖、只读交接不加载训练模块。

检查命令：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/check.py --scope modeling
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/check.py
```

模型scope已登记整局实验测试及experiments源码；最终全量仍需单写者和验收前后指纹一致。
本轮最终全量验收：1043项pytest、22项学习／知识测试、6项JS测试，合计1071项通过；
Ruff通过，406个Python文件格式检查通过。验收前后865份源码／文档文件指纹完全相同，
2014份旧输入／交接文件指纹完全相同。真实输入只读准入通过，training_executed=false，
identity_sha256仍为2ccbe366afacb9462605038605389739c409c550a516b66960febb97d56a3d83。

首轮全量仅发现既存tests/test_purchase_until_daily.py格式问题，随后仅格式化该测试文件，
AST比较确认语义未改；采集器未修改。最终重跑退出码0。
日志：reports/experiment-refactor-2026-10-22/final-check.log；
机器可读结果：同目录verification.json；真实只读结果：real-verify.json。
验收后仅补写本节、历史文档迁移说明及验证记录，并再次检查链接与代码指纹。
未进行真实训练、提交或推送。
