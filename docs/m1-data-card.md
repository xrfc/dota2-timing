# M1 数据卡：多英雄比赛级数据表

快照：`reports/m1-match-table-2026-10-30-v1/`（本地，不提交）。复算校验：

```bash
PYTHONPATH=src .venv/bin/python scripts/build_match_table.py verify --snapshot reports/m1-match-table-2026-10-30-v1
```

重新生成须用不存在的目录：`scripts/build_match_table.py snapshot --output NEWDIR`；覆盖统计：`... inventory --output NEWDIR`。代码：`src/dota_items/data/match_table.py`。

## 1. 来源与范围

| 项 | 值 |
|---|---|
| 来源 | OpenDota解析比赛JSON，`data/purchase-1000-2026-10-14/`与`data/purchase-additional-1000-2026-10-15/`，逐文件按manifest的SHA-256核验 |
| 输入 | 2551场；**1993场**10人均有完整解析字段，入表；558场（全在additional批次）无任何解析字段，排除并在manifest列出ID |
| 时间 | 2026-10-12 16:42 至 10-13 08:07 UTC（约15.5小时） |
| 补丁 | 全部patch 60（7.41） |
| 模式 | 天梯（lobby 7）全英雄（mode 22） |
| 原采集筛选（10/14–15，静态主宰任务） | 含主宰、时长≥30分钟、平均段位提示≥70 |

## 2. 表结构

`players.csv`：19930行（每场10人）。`purchases.csv`：879200行（全部购买，含开局前负时间）。`split.json`：划分。`manifest.json`：输入摘要、实现哈希、输出哈希、列可知性、规则常量。

每列都登记“何时可知”（`FIELD_AVAILABILITY`/`DERIVED_AVAILABILITY`）。**赛前产品只能用`pre_game`列作输入**，由`pre_game_view`强制并有测试：

| 可知时点 | 列 |
|---|---|
| pre_game | start_time、patch、avg_rank_tier、player_slot、is_radiant、hero_id、rank_tier |
| lane_end（10分钟） | lane、lane_role、is_roaming、lh_10、dn_10、gold_10、xp_10、kills_10、deaths_10、lane_efficiency_pct、collapsed_carry |
| minute_15 | lh_15、position |
| post_game | duration_s、win |
| 购买 | time_s、item 在购买发生时可知 |

对线窗口为[0, 600)秒：600秒整的击杀不计入。

## 3. 派生规则（用户决定）

- **位置（U8）**：同队优势路（lane_role=1）恰好2人时，15分钟补刀高者为1号位、低者为5号位；差<25刀或非2人→空。结果：1号位/5号位各3849人，覆盖96.6%队伍侧。位置是“实际承担的角色”，由赛中数据推出；赛前产品中对应用户输入的位置。只覆盖优势路，中/劣势路位置为空。
- **对线崩盘（U8）**：1号位10分钟补刀<35刀标`collapsed_carry`，209人（1号位的5.4%）。产品A训练排除，产品B保留，产品C对照用中位数与前25%。

## 4. 划分

按比赛整体划分（同一场不跨集合），按(start_time, match_id)排序，最新20%为验证：训练1595场、验证398场。

局限：全部比赛只跨约15.5小时，时间划分几乎不带来补丁或环境漂移，效果接近随机划分；**这不是独立评估**（见§5）。

## 5. 与旧实验的关系

M1的1993场＝旧`cohort-random-v2`的1990场＋3场。旧静态主宰实验已在这些比赛上训练和查看过验证结果；M1验证集中有310场是旧实验的训练比赛。因此：
- M2/M3可在M1划分上开发新模型（新任务、从头训练）。
- 不得用M1验证集比较旧冻结模型。
- 任何“效果”结论须等M4在新采集数据上的独立评估。

## 6. 已知偏差

| 偏差 | 影响 | 处理 |
|---|---|---|
| 段位：冠绝12032、超凡10739、万古2175、传奇288人次（约90%超凡+） | 节奏快于用户（传奇）常见对局 | U7：有意以高分段为标准；界面注明 |
| 只含≥30分钟比赛（中位38.5分钟） | 碾压局缺失；出装时间偏慢；对线结果偏均衡 | M4（Q5）考虑不限时长 |
| 每场都有主宰 | 其他英雄的统计都在“同局有主宰”的条件下 | M4随机抽样；模型卡注明 |
| 位置由补刀推断 | 极端局（1号位补刀不如辅助）被错分或排除（约3.4%为空） | U8；数据卡登记 |
| “补刀少”无法区分买号与被正常压制 | `collapsed_carry`含两类 | 只作发育异常标记，不称买号 |
| 时间跨度约15.5小时 | 无时间外推检验 | M4 |
| 段位缺失147人 | 少量 | 保留为空 |

## 7. 覆盖

127个英雄出现；≥200人次的45个、≥100的86个（`reports/m1-inventory-2026-10-30-v1/inventory.json`）。按1/5号位的英雄样本量在M2-T1统计，用于Q3。

## 8. 未做

未训练；未联网；未修改旧1990场快照或任何旧报告。
