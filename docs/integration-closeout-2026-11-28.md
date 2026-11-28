# 短期总结与PR集成（2026-11-28）

用户要求整理文档和开发路线、阶段收尾并合并所有PR。本批覆盖 #30–#56 共27个开放PR；均无待处理review/thread。以 `90353ea2936a10c33b938dd28cb95f6ed9381816` 为集成基线，保留每个原PR head为祖先，通过一个集成PR的merge commit进入main；不squash、不删除分支，不改写远端历史。实际合并状态以GitHub为准，本文记录可复验的源码组合。

## 阶段成果与限制

- #30–#32：本地复盘输入、真实比赛ID、终局截断、缺失样本显式处理及本机工作流。
- #33–#40：行动后果监督研究、U191开发／冻结单次评估、新录像及三场B5复盘、地图和解释。337场已经评分；观察性预测并不证明反事实最佳动作。
- #41–#50：玩家试用记录、反馈核对、B5评分器、分类实收与营地事前可见／条件证据。1169场15005机会工程对账完成，仍不能把完整结果回填决策特征。
- #51–#53：架构评审、模型兼容迁移设计、M1标准库契约与纯推理。M2–M4未完成，真实兼容矩阵为空。
- #54–#56：精确7.42工程录像、可靠续跑／压缩存储、地图机制与原始树／viewer补证。完整树ID和有效视野来源尚缺；正式机制仍7.41f。

短期下一步按[计划§7](development-plan-2026-10-30.md#7-状态表唯一进度来源)：完整原生树映射与有效视野 → 剩余机制／阶段条件 → B5后果验证与明确实验 → 模型M2–M4。新独立验收数据与研究变化另定。路线A继续暂停。

## 集成中的实际冲突

U191冻结26个来源文件，其中7个与较早的本地复盘改进／较新的bundle消费重叠。直接选任一分支会丢功能或破坏冻结SHA。因此保留26个旧源码的路径与逐字节身份；新增7个版本化工程入口，当前工作流显式调用它们。没有放宽旧SHA检查，也没有把旧回执重标为新生产者。

[入口迁移登记](acceptance/review-entrypoint-transition-20261128.json)绑定精确旧SHA与新SHA，仅允许新输出，**不授权复用旧回执或转换真实模型**。当前命令 `scripts/lane_decision_review_v2.py` 同时支持本机材料和 `--bundle-reference`；`decision_review_handoff.py`已转接。`extract_creeps_review_v2.py`、v2捕获模块保留真实ID检查；`extract_state_v3.py`显式使用v2捕获。旧 `lane_decision_review.py` 留作U191历史复现，不是当前bundle入口。

这是为冻结路径兼容所需的有限重复，不宣称低耦合工作全部结束。新模型数值实现已在modeling，当前复盘CLI仍有编排债务；后续按M2–M4演进，禁止就地抽公共函数使冻结源码变动。共享底座不导入A/B，A/B互不导入，来源不依赖data、data不依赖workflow，注册与静态无环测试继续执行。

## 验证口径

组合验收包括全库Ruff／格式、pytest、学习与知识unittest、Node页面测试；新增冻结26源码与7入口登记回归，并覆盖终局截断、缺失extras和bundle输入。`scripts/check.py`同时保留架构评审的混合模型scope和B5试用页Node检查。最终运行前后核验包含未跟踪源码的文件指纹，日志保存在本机 `reports/integration-closeout-20261128/`，不覆盖旧验收证据。结果记录在[验收清单](acceptance/integration-closeout-20261128.json)。

本轮只做集成与工程测试，不运行真实训练、重评337场、采集新demo或切换正式知识。历史各分支测试数不是本次组合验收数。

## 原PR固定输入

| PR | 主题 | 固定head |
|---|---|---|
| [#30](https://github.com/xrfc/dota2-timing/pull/30) | 从本地录像生成复盘报告，自动核验并汇总待判断片段 | `0a582e49da1edffb698dd1f047cd70d475f9f2fe` |
| [#31](https://github.com/xrfc/dota2-timing/pull/31) | 路线 B：核验本地三场 7.41f 复盘并修复过期邀请提示 | `57cd407d6a19aad10f6ac03d68ebd7c6ea78bc01` |
| [#32](https://github.com/xrfc/dota2-timing/pull/32) | 路线 B 改为单人本机评审，移除邀请和公网访问流程 | `f21a2e7809c664126cf1d4209cefb39d014d599a` |
| [#33](https://github.com/xrfc/dota2-timing/pull/33) | 路线 B：完成一号位补刀前三阶段真实开发集实验 | `6a8c504578f4ba5c4810a83f9d3ffda29a69cc2a` |
| [#34](https://github.com/xrfc/dota2-timing/pull/34) | 路线 B：用录像后果比较收线、打野与支援决策（U191） | `7ca2ae3d14edae67042634f820a9456827d78ce1` |
| [#35](https://github.com/xrfc/dota2-timing/pull/35) | B5：按比赛导出一号位收线、打野和支援复盘 | `0df42a6b1c707b96623ffac7be97d5a553cf660b` |
| [#36](https://github.com/xrfc/dota2-timing/pull/36) | B5：从独立 Steam 录像生成冻结模型复盘 | `cfa6162d3e315f5302ee45676cb0dfe2dd4ccd1d` |
| [#37](https://github.com/xrfc/dota2-timing/pull/37) | B5 三场独立录像试用：核对比赛身份、输入覆盖与报告依据 | `2ccf823ce503ab03d6f404c61c440945674c4f18` |
| [#38](https://github.com/xrfc/dota2-timing/pull/38) | B5 本机复盘工作台：按比赛和片段查看实况与双动作估计 | `81e023e350ef2bd9dc82b7fa4f14286064e2a5ef` |
| [#39](https://github.com/xrfc/dota2-timing/pull/39) | B5 战术地图：按复盘英雄的阵营展示当前局势与最后露头 | `123f1c23ed9d2e7099f31da36d040dd04e805636` |
| [#40](https://github.com/xrfc/dota2-timing/pull/40) | B5 试用反馈：说明每个片段能比较什么、为何只能展示实况 | `171e42dea59254d1dd774b027962425f6d172fd7` |
| [#41](https://github.com/xrfc/dota2-timing/pull/41) | B5 玩家试用：按原报告片段保存反馈并导出 | `6ee5a538317cfd6c510d48f1e91d4abba18e932c` |
| [#42](https://github.com/xrfc/dota2-timing/pull/42) | B5 玩家反馈：离线核对原报告版本并定位片段行号 | `36479807fcd4afd693ad6387c7f3d36770fa1d5b` |
| [#43](https://github.com/xrfc/dota2-timing/pull/43) | 路线 B：登记决策自评口径和六步开发计划 | `fe38810b3ea3977957b0f708ac62f42e4be61006` |
| [#44](https://github.com/xrfc/dota2-timing/pull/44) | B5 决策自评：冻结评分口径并复核三场景开发集基线 | `5cc726716229dec72725effa22584907d20fdda3` |
| [#45](https://github.com/xrfc/dota2-timing/pull/45) | B5：按走位复核收线与转野，比较 30 秒及 20 秒实收金币 | `a392ff0e638441c6681e2ca4b88e391c39057f9b` |
| [#46](https://github.com/xrfc/dota2-timing/pull/46) | B5：统一当前路线，盘点动作覆盖并诊断未知原因 | `408e0225d026a6ee300d4fb4144253a92ac10d55` |
| [#47](https://github.com/xrfc/dota2-timing/pull/47) | B5：完成分类实收提取与独立对账 | `8065f8ff4110c6cd8a09743ae671daeb74d03d7b` |
| [#48](https://github.com/xrfc/dota2-timing/pull/48) | 文档：核实 7.42 上游地图更新与仍缺的几何资产 | `4d8a8233729ab2714dc066c69c2dc9202d657389` |
| [#49](https://github.com/xrfc/dota2-timing/pull/49) | B5：补齐 1169 场营地事前可见证据并完成独立验收 | `d9f78fc849b7d22b2b4a9968b7158816c75dc3c2` |
| [#50](https://github.com/xrfc/dota2-timing/pull/50) | B5：核验营地条件与静态连通，明确模型可信度缺口 | `e020268cfa6100f16ef308b49ebdbd4ff918a45e` |
| [#51](https://github.com/xrfc/dota2-timing/pull/51) | 阶段总结与架构评审：统一当前文档并补依赖护栏 | `ef9c898b1e37dc4d14b035c973e3ebd7a1db6ee2` |
| [#52](https://github.com/xrfc/dota2-timing/pull/52) | 设计：行动模型兼容迁移与模型、编排、CLI 分离 | `f4407fb2359ad3e2980274dfa86d21125ce85402` |
| [#53](https://github.com/xrfc/dota2-timing/pull/53) | 实现 M1：版本契约与行动模型纯推理 | `87b1de5aa99f1e8fc42b4be53526062a1fa701b2` |
| [#54](https://github.com/xrfc/dota2-timing/pull/54) | 记录 7.42 五场 demo 试采、解析核验与改进路线 | `fe7237e8218f71de59991722fab63bae01355b81` |
| [#55](https://github.com/xrfc/dota2-timing/pull/55) | 固定录像版本，单次压缩解析并接通可复验的复盘输入 | `3f1de6ba6b3b1e93b391c2b93938f8e9e09138be` |
| [#56](https://github.com/xrfc/dota2-timing/pull/56) | 建立 7.42 候选地图、机制准入与决策时证据 | `018bf1db957f7688b25a3c3709799374afafbb24` |
