# 主宰位置与装备标签语义核验

日期：2026-10-13；审计器 `purchase-feasibility/3`，语义输出 `purchase-semantics/1`。
本轮在固定扩展10场中，对上轮已确定的7场“7.41f时间一致且时长覆盖30分钟”作深入核验，
不是新独立评估集。全10场仍保存在报告，短局与区间外比赛未删除。

## 结论

| 字段/目标 | 已核实的含义 | 本轮决定 |
|---|---|---|
| `lane_role=1` | 上游根据位置桶判断优势路，不区分carry/support | 不认证一号位 |
| `position_est=1` | 队内第10–12分钟经济/补刀排序、眼与分路启发式估计 | 7/7有此线索；保留estimated，不作为赛前输入 |
| `purchase_time[key]` | 该物品各条购买记录的时间总和 | 不能作为首次/完成时间；可超过比赛时长 |
| `first_purchase_time[key]` | 上游按日志顺序记录首次值 | 本工具与最早有效事件比较，不盲信字段 |
| `item_usage[key]` | 购买日志中出现即置1 | 不是主动使用次数；区别于 `item_uses` |
| `rank_tier` | 当前源码从玩家查询结果rating填入 | 不证明比赛当时段位；不自动认证高分样本 |
| 下一件成装完成/送达 | 购买日志与这些派生字段不能独立证明 | 本轮不生成此标签 |

7场共243个“比赛—物品键”组合，三个汇总字段各243/243与有效日志一致，共729次字段比较。
这不是729个独立观测或243场比赛；也不是装备推荐准确率。7/7没有 `inventory_log`，
因此不能由这些字段验证连续库存、成装完成或送达。训练准入仍为0。

## 上游来源证据

保存了OpenDota当前 `master` 的源码文本、获取时间、URL与SHA-256：
[来源清单](../knowledge/evidence/feasibility-2026-10-13/semantic-sources.json)。
快照来自工具提取文本，并非Git提交锁定，也没有确认与本批比赛部署的解析器相同。
源码仅用于解释与核对字段计算，不执行，不据此声称所有历史比赛都使用相同实现。

- [computeMatchData / estimatePositions / getLaneFromPosData](../knowledge/evidence/feasibility-2026-10-13/opendota-compute.ts.txt)：
  购买汇总约175–207行，位置估算约254–336行，分路约441行起。
- [buildMatch / getPlayerDetails](../knowledge/evidence/feasibility-2026-10-13/opendota-buildMatch.ts.txt)：
  玩家段位填充约173–201行；调用位置估算约296行。
- [上游MIT许可](../knowledge/evidence/feasibility-2026-10-13/OPENDOTA-LICENSE.txt)。

源码还展示了两个值得防范的细节：

1. API投影会过滤 `recipe_` 和 `ward_dispenser`；因此输出中没配方不能自动当作漏采。
2. `if (!pm.first_purchase_time[k])` 会把0视为尚未设置，后一次购买可能覆盖0秒首次值。
   新测试复现此语义风险；本批7场没有发现首次字段不一致，不宣称线上已发生或已修复上游。

网络搜索摘要曾把 `lane_role=1` 解释为carry；此解释没有采用，以上游实际源码为准。

## 已实现的核验

[semantic_review.py](../src/dota_items/data/semantic_review.py) 复用既有购买规范化：

- 返回目标与队内分路/位置估计线索，只保留slot和hero_id，不输出账号或姓名。
- 逐物品重算时间总和、最早观察时间与出现标记，保留事件引用。
- 区分consistent/inconsistent/missing/invalid；存在非法事件时不把部分日志比较称为一致。
- 标明无有效事件却存在的汇总键、缺失/未经验证库存、每个候选的标签不可用原因。
- 不用最终六格替代历史库存，不从未知购买生成负标签，不改旧训练门禁。

所有可检查比赛自动增加 `semantic_review` 字段，不需新采集器或新命令。
离线复现（输出路径必须未存在）：

```bash
python3 audit_data.py --plan knowledge/evidence/feasibility-2026-10-13/expansion-plan.json --discovery data/feasibility-2026-10-13/discovery-response.json --offline --cache data/feasibility-2026-10-13/matches --patch-receipt knowledge/evidence/feasibility-2026-10-13/receipt.json --output reports/semantic-review-new.json
```

原JSON仍在本地忽略目录；异机需提供原快照。完整10场和7场聚焦分母、代码/来源哈希见
[机器记录](acceptance/data-semantics-2026-10-13.json)。历史v2报告保留，不回写成v3。

## 下一步：验证标签来源，而不是扩大样本掩盖问题

1. 追踪上游解析器购买事件的实际生成点，明确成装键代表购买、合成还是获取；
   锁定对应源码/版本，并挑出可对照的原回放事件。不得用汇总字段自证。
2. 对这7场逐场补充独立位置证据，或单独定义并验证“估算位置”队列；
   不能把赛后估算悄悄换成已知赛前一号位，也不能把该估算值作为开局特征。
3. 若只能支持“日志中出现的购买行为”，以独立版本明确此实验目标与覆盖/未知策略，
   再冻结标签、样本契约和划分。它不等同于“下一件最佳成装”，后者继续需要库存/合成证据。

不要求无关历史字段问题阻止所有未来实验，但本轮证据还不足以解除本任务的标签限制。

## 工程验证

新增15项语义回归测试，专项59项通过；统一 `scripts/check.py` 全部通过：工程277项、
学习Python 10项、知识12项、JS 6项，合计 **305项**。Ruff、格式、差异空白检查、
代码/输入/来源哈希与新增文档链接检查通过。没有远端CI、客户端核验或真实模型训练。
