# 版本化知识与候选监督

这里保存可追溯的公开知识快照、解释工作稿、来源核对和训练候选，不属于 `src/` 正式工程包，也不是已准入的训练集。

- **当前知识入口：`mechanics/current.json`**；被取代的旧知识登记在[`superseded.json`](superseded.json)，读取用`dota_items.data.knowledge_superseded`（MK-T6f）。
- [机制知识框架（U26）](mechanics/README.md)：里程碑MK：官方原始枚举解码与机制词表（事实层），复核后事实、机制规则和推导层（草稿）已有，当前入口和读取规则见该目录的“当前数据流”。
- [全英雄能力档案](hero-capabilities/HEROES.md)：当前官网快照，127 位英雄、734 个技能条目。
- [能力评估定义](hero-capabilities/ASSESSMENT.md)：作用对象、条件、限制和升级要求。
- [选人评估与维护命令](hero-capabilities/README.md)：双阵容证据清单，不输出强度或胜率。
- [冷启动候选清单](hero-capabilities/cold-start/manifest.json)：734 条官方说明提取候选，尚未准入训练。
- [新审计与上游语义证据](evidence/feasibility-2026-10-13/README.md)：补丁、固定采样、源码哈希和MIT许可，不含原玩家JSON。
- [公开证据元数据](evidence/7.41f-2026-10-06/README.md)：来源、哈希与历史核验收据；不含回放本体。
- [路径与维护记录](../docs/knowledge-maintenance.md)、[冷启动训练用途](../docs/knowledge-cold-start.md)。

第三方内容的来源和权利边界见[来源说明](hero-capabilities/SOURCES.md)。仓库 MIT 许可证不覆盖或重新授权第三方官网文字。个人回放、完整玩家资料、大型 ZIP、密钥、模型权重不存入本目录。
