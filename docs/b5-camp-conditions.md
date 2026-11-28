# B5 营地条件：从可见单位到可确认范围

2026-11-26。按[本轮要求](decisions/2026-11-26-model-trust-and-camp-conditions.md)，接续[已验收的营地公开证据](https://github.com/xrfc/dota2-timing/pull/49)。本主题核验现有证据能否支持营地存量、路径和清营结论；不改变动作、目标、划分，不训练。

## 公开证据的条件分析

`data.camp_conditions.summarize_camp_evidence(document)` 严格接收 `camp-evidence/1` 白名单，输出 `camp-conditions/1`，用途固定为 `evidence_audit_only`。不导入未合并的生产者，不接收全知 raw、owner、未来动作或额外字段。

- life_state=0 且 HP>0 才记为观测到存活；1/2 记为非存活，其他值或缺失保留未知，state=0 但 HP≤0 单列冲突。不能用 active 实体数量代替存活数量。
- 单位阵营 4、己方、敌方及其他/未知分别统计。中立阵营不证明自然刷新、敌对关系或能刷；名称含 neutral 也不作为归属判据。
- 缺帧或缺观察者时 `facts=null`；已取得观察且没有可见单位时可见计数为 0，但 `empty_confirmed=null`。
- `alive_neutral_team_visible_health_sum` 只是当前可见、观测存活且 team=4 单位的血量之和，不是营地总血量、清营工作量或收益标签。同一单位跨帧重复出现，汇总观察数不能解释为独立单位数。
- 可见性是己方全队视角，记录并不限于英雄附近。本层没有按距离挑“附近可刷单位”，也不采用新的经验半径。
- 成员归属、库存、实际可通行及清营能力四项分别保存 `unconfirmed`、null 和缺失证据列表。当前输入没有整营范围/视野、可信成员关系、实际路径或英雄战斗属性，所以不产生“可以刷”或“不可以刷”的结论。

## 静态地图能够回答的部分

`data.static_map_connectivity` 新增严格四邻接连通分量诊断。`load_static_map(gridnav_path, elevation_path, patch_family="7.41")` 只接收登记的上游提交 `f793787ecf402f52c9e698da260b02f041256898` 和两份原始文件摘要。来源声明为 7.41，本地已有 7.41f 坐标对齐证据，不等于官方逐补丁认证；不得挪用于 7.42。

坐标为原生 replay cell space（世界坐标加 16,384），64 单位格，按最近格心、Python round 的 ties-to-even 约定映射，外界采用半开范围。接口不会把落在障碍中的点吸附到附近可走格，也不会自动添加斜边。

- `point_facts(position)` 区分缺位置、离网格、地图外、blocked、open，返回格坐标、高度与分量。
- `connection(start, end)` 给出两端事实和 `static_grid_connected`；仅两端均 open 时给布尔值，其余为 null。直线距离仅指传入的两个固定点，不是距离营地边界或攻击范围。
- 图中不含树、动态障碍、单位碰撞体、移动能力，`real_route_traversable` 与 `eta_seconds` 始终为 null。不同分量不证明英雄无法抵达，同分量也不证明当前路线可走或安全。本版不输出路径长度。

这层用于发现坐标和静态障碍问题，不承担行动排序。原 `map_api.region_at` 的附近格吸附用于区域显示，不复用作可通行认证。

## 固定交接与命令

沿用原 1,169 场/15,005 机会及 plan SHA `8ad71d1e60b251360b9e96a4afc0c4a599443ddaa1c88abdb012b060cba7f3ad`。批次 manifest 固定为 `7e196e7f1c149d790ebd5132ba6f070f30d4dc2da492019383cf41f62f124318`；已验收公开快照 SHA 为 `46caa3fff31a0cb0ba5dbcdab921c35a77c27432c024b4e48f2b02eaec391582`。快照内逐场 receipt/evidence 的摘要也必须匹配，改值后重新签名不能绕过。

CLI 只消费公开 evidence 和收据，按原 action/fold/观察阵营汇总条件事实；原动作和 fold 只放审计元数据，不放进公开事实。输出新目录，包含逐帧结果、汇总和前后输入/实现摘要，不覆盖旧结果。它不重新读取原始录像，不应扩大为全量再次重放的声明。

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/audit_b5_camp_conditions.py \
  --plan reports/b5-farm-income-20261125/plan.json \
  --batch reports/b5-camp-evidence-20261126/batch-v1 \
  --snapshot reports/b5-camp-evidence-quality-20261126/final/snapshot.json \
  --out reports/b5-camp-conditions-20261126/full-1
```

上述完整运行已结束，命令退出 0；再次运行须换新输出目录，已有 `full-1` 不覆盖。2,341 个输入和五份实际导入的生产者文件前后摘要一致。

| 全集观察分类 | 数量 |
|---|---:|
| 固定比赛／机会 | 1,169／15,005 |
| 可见单位观察 | 179,149 |
| 观测存活／非存活 | 151,755／27,394 |
| 存活中立阵营／存活玩家阵营 | 148,470／3,285 |
| 生命未知／矛盾 | 0／0 |
| 有至少一个可见活 team4 单位的帧 | 12,117 |
| 有可见单位但无活 team4 的帧 | 449 |
| 零可见帧 | 2,439 |

这些数是重复观察而非库存，四项条件各 15,005 帧仍为 unconfirmed/null，不是已证实不满足。6,235 个收线、1,176 个朝野区移动、7,594 个未知动作全部保留，唯一 t==duration 的机会也保留。`summary.json` SHA256 为 `8aa0e3b9b076f6adcb67720089da0dbd8e3195377f60f97c2891c8df238704d9`。

独立验收 `reports/b5-camp-conditions-review-20261126/verify_conditions.py` 不导入生产分类函数，直接从原公开数值重建每帧生命、阵营、条件、分组和固定人口；全部一致。报告为 `full-1/report.json`，SHA256 `676382fbd588c0bd9d06f70b1b08f664720d43ddd2771eef92da8bf11b67295d`。输入、当前生产者及独立脚本前后摘要一致，没有重读原始录像或全知 raw。

## 生成器字段的独立探针

仅在原固定开发计划的 9080976703 和 9090682276 两场，按原机会的首 tick-start 读取 `m_hNeutralSpawner`、实体 index/serial、生成器位置及发送字段，同时保存同一观察英雄的出发点。所有新增原始信息只用于来源语义审计，不自动升级公开归属。

正式 v2 共 25 帧、5,044 条原始单位记录，5,033 条生成器引用有效、11 条 NULL。受控或离中心很远的单位仍可能保留生成器关联；中立分裂泥土傀儡也可能没有引用，因此两个方向都不能据此判断当前营地成员。两个场景的 28 个生成器中心一致，与既有地图按原整数 round 约定全部对应；浮点到整数的最大量化偏差 0.6412 单位。完整发送表的 33 个 leaf 未读到区域边界，不表述为游戏中不存在区域。

证据为 `reports/b5-camp-spawner-probe-20261126/REPORT.md` 和 `summary.json`，不覆盖旧 camp-evidence/1。完整解析、最终时钟、原冻结 capture 可比字段及输入/compat/探针源码摘要均通过。少量定向回归只证明这些场景，不估计全集成功率。

静态地图实测在 `reports/b5-static-connectivity-20261126/`：59,606 个地图内非 blocked 格分为 25 个分量，主分量 59,505 格；28 营地中心均在主分量。原两场 25 个同首 tick 出发点 × 28 营地构成 700 次查询，全部静态连通；独立 union-find 与原始 cell/vec 坐标重建、输入/实现前后哈希均通过。这个小集的几何条件不能区分营地优劣，不代表全 15,005 个机会的路线都已核验。

## 本轮验收与剩余项

三组专项 93 项通过，覆盖未知与零、尸体、阵营、同名召唤物、矛盾生命状态、未来帧非干扰、严格白名单、快照三件套重签、缺场/重复以及静态网格边界。交叉审查发现的同帧 index 冲突已修复：同一帧只能有一个当前实体，跨帧可换 serial；全集无同帧冲突，跨帧复用完整保留。

收尾按项目规则串行运行 `scripts/check.py --scope all`，日志及含未跟踪源码的前后指纹位于 `reports/b5-camp-conditions-20261126/check-final*`；只有检查退出 0 且指纹一致才提交本轮结案。

库存、实际可通行和清营能力未获得正向证据时继续保留未知。后续应补足以改变具体条件判断的证据，如营地范围与整营可见性、对动态碰撞有效的路径或英雄战斗就绪条件；不能用更多工程测试替代这些证据，也不自动据此改标签或训练。
