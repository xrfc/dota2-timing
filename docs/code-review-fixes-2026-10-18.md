# 代码审查修复与复审（2026-10-18）

基线为1d81dd3，用户要求修复四项P2并再次审查。本轮只处理工程正确性，不运行真实训练，不改变研究标签口径、正式划分或旧数据；新增队列分析的既有未提交文件保留。

## 修复行为

1. `cleaning`给确定发生购买事件隔离的玩家保留`purchase_log_quarantined=true`，质量报告包含`supervision_held`。`features`在此状态下不生成购买监督，原因`invalid_purchase_log`；路线标签独立。完好但覆盖未知的日志仍可生成下一观测事件标签。prepare→import→clean→build-samples保留状态，旧导入只有嵌套cleaning_audit的情况也能识别。旧文件不自动重写；新生成产物的代码指纹不同。
2. `workflow.processes.run_adapter`集中管理适配器执行范围。POSIX使用独立session/process group，退出、超时或取消后进行TERM→限时KILL；Windows在Job Object分配前保持新进程挂起，分配后恢复主线程，关闭Job清理后代。正常退出的适配器也不能遗留后台worker。保留退出码、日志以及原有异常状态记录。
3. `load_timeline`若有外部证据声明，要求路径与SHA成对，拒绝越界、符号链接、缺失和哈希不符。无外部证据时计算输入文件实际SHA。文件一致性校验不等于真实来源认证或完整回放语义验收。
4. 敏感性实验JSON记录执行时Python、NumPy、scikit-learn版本及Git revision/dirty状态。Git信息不可用时明确为null，不编造revision；现有输入和实现哈希继续保存。

## 兼容性

严格重建仍默认开启，旧产物保持原字节。public-reader/1显式迁移仅新增已审查的normalize.py及producer_migration.py历史哈希；当前哈希必须与实际源码一致，所有非实现字段逐字节一致。该扩展不授权训练、不允许任意历史哈希。旧952快照须以显式兼容入口核验，不冒充原源码精确复现。

## 验证与复审方法

- 新回归覆盖：已知坏事件及未知时间、重复清洗、旧审计、prepare/import/build-samples完整链路；独立CLI损坏证据拒绝；报告实际版本；进程超时、取消及正常退出后的后代清理。
- Windows使用本机Python实际运行Job Object分支；Linux使用仓库pytest实际运行POSIX分支。测试包括忽略普通TERM的后代。
- Windows CI已纳入进程树与报告证据测试。
- 复审重点：损坏状态能否跨导入丢失、挂起进程失败是否泄漏、后代在父进程结束后是否存活、修复能否导致旧快照静默失效。
- 最终检查数字和指纹核验以本轮交付回复为准，不沿用历史测试计数。

## 实际限制

POSIX进程组用于可信适配器的资源管理，主动setsid脱离的程序不属于此机制的安全隔离保证。Python之外的模型效果、购买完成语义及独立推荐质量验收仍需各自证据。本轮未重跑真实训练或改变旧实验结果。
