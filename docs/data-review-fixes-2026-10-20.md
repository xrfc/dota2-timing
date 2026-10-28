# 数据脚本审查修复（2026-10-20）

本轮针对 Windows 副本、`feat/purchase-data-prep`、HEAD `1d81dd3` 之上的未提交文件。
用户授权修复前轮发现的两项问题；保留其他未提交修改，不改变研究范围或冻结产物。
此记录不是 WSL 唯一工作目录的集成验收，也不替代现有协作协议。

## 修复

1. `scripts/analyze_cohort_splits.py` 将迁移清单中的实现相对路径转换为
   `as_posix()`。Windows 路径原先包含反斜杠，无法匹配已有迁移登记；
   不放宽历史哈希或非实现字段检查，也不增加迁移白名单。
2. `scripts/collect_purchase_latest.py` 在收到 HTTP 401、403、5xx 后，
   先记录比赛 ID、HTTP 状态、请求已预留及失败类型，再保留原来的停止异常。
   原始响应和 manifest 仍保存，不重试，不请求后续比赛。
   `attempted_results` 继续表示结果清单行数；请求发送情况仍须结合
   `requests` 和 `request_reserved` 判断，尤其是发送前预算暂停。

## 验证

- 最新采集、分组分析及生产者迁移专项：49 项通过。
- 架构依赖与模块维护专项：30 项通过。
- 新回归模拟 401、403、500、503，确认记录一次失败、统计一致、保留响应、
  不重试且不请求计划中的下一场；全部使用离线 MockTransport。
- 迁移测试额外断言回执路径采用 `/`，原有非法哈希及非实现字段拒绝测试保留。
- 使用本机 Python 3.12 和现有依赖，通过 PYTHONPATH 指定当前源码，
  禁用字节码与 pytest 缓存；副本中的 `.venv` 是 Linux 布局。
- 本机 Python 未安装 Ruff，lint/格式检查未完成；未安装或修改依赖。
- 未执行正式全量验收、真实采集或真实训练；未提交或推送。

专项命令（运行前将当前 `src` 加入 PYTHONPATH）：

```text
python -m pytest -q -p no:cacheprovider tests/test_latest_purchase_collection.py tests/test_cohort_split_feasibility.py tests/test_producer_migration.py
python -m pytest -q -p no:cacheprovider tests/test_architecture.py tests/test_modular_maintenance.py
```
