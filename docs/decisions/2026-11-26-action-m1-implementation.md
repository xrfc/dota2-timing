# 多版本设计后继续M1（2026-11-26）

用户原话：“按你的建议，先把版本身份、兼容矩阵和支持周期补进设计并同步文档，再继续 M1 开发，自己校验。”

前置设计及授权已记录于[PR #52固定版本](https://github.com/xrfc/dota2-timing/blob/f4407fb2359ad3e2980274dfa86d21125ce85402/docs/decisions/2026-11-26-action-model-multiversion-m1.md)。先完成设计更新、文档同步和全量校验，再从origin/main建立独立M1主题分支。

本轮执行标准库版本/任务契约、五类状态纯推理、三domain估计和keyed评价、合成基准与架构回归。测试不调用fit/minimize，不读真实模型/留出、不改原任务/标签/划分，不注册真实跨补丁支持。详细工程API是助手实现选择。

交付：[M1说明](../action-model-m1.md)。M2及以后继续按计划分步推进，不擅自真实训练或迁移；合并PR、推main、删分支仍需用户决定。
