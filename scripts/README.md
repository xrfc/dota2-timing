# 脚本职责导航

**2026-11-26 检查入口整理**：`check.py --scope modeling` 与 `--scope data` 共同包含 8 套模型/跨层测试；未知测试仍保守归 data，显式导入 modeling/experiments 的套件由回归检查要求进入 modeling。最终必须 `--scope all`；架构护栏覆盖脚本导入与静态循环，动态装载/文件交接的限制见[阶段评审](../docs/reviews/2026-11-26-stage-and-architecture.md)。
