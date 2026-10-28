# 日志观测建模快照与玩家分组评估

2026-10-14用户明确要求基于日志观测目标准备快照与玩家分组评估。本轮只准备，不训练。

## 固定任务

- 输入：开局双方十英雄身份，友敌分开编码；目标主宰。
- 标签：合法源purchase_log在[0,1800)内是否出现候选键。存在=1、不存在=0。
  这里0仅表示这份日志未记载，**不是证明实际没有购买**。本快照不用于最优出装或成装时间预测。
- 五候选顺序保持bfury、maelstrom、manta、black_king_bar、skadi。
- 主分析保留全部952场；946场估算carry作为预先说明的切片，不悄悄丢掉另外6场。
  不宣称所有比赛均独立验证为真实一号位或比赛当时高分；补丁仅有时间一致证据。
- 新schema为purchase-log-modeling-snapshot/1；modeling_ready只适用于该源日志代理任务。
  不改旧真实购买/成装门禁，legacy_training_allowed=false，training_executed=false。

## 玩家分组方法

用所有十名玩家的有效账号ID建立比赛连通分量；共享任意玩家的比赛，包括传递关联，归为同一组。
重新读取并校验原始缓存，不信任旧报告提供的分组。账号缺失、非法、同场重复时拒绝认证分组快照。
本批9520个槽位身份字段完整，形成305个关联组，最大组519场。
组按规模降序、seed=20261014的组哈希打破平局，再放到目标场数缺口最大的集合。
目标比例60/20/20，不使用装备标签、胜负或位置估算优化划分，不拆组、不重复尝试种子。

| 集合 | 比赛 | 玩家关联组 | 估算carry / 其他 |
|---|---:|---:|---:|
| train | 571 | 53 | 568 / 3 |
| validation | 191 | 126 | 189 / 2 |
| test | 190 | 126 | 189 / 1 |

三对集合的已知账号交集均为0。最大519场组完整进入train，约占训练集91%，有明显组规模偏斜。
零账号重叠不证明现实人物完全独立。本批数据此前已查看，test称“探索性玩家隔离留出集”，
不能称从未查看的最终独立测试集，也不再按这些类支持结果重新选划分。

## 编码与类支持

词表仅由train拟合，共126个英雄；友敌multi-hot各126列，各加一个unknown_count，共254列。
角色估算、组号、比赛ID、源哈希仅为元数据，禁止进入模型X；源购买信息仅用于y。
缺失/非法日志标签mask=false；本批952场均合法，因此源日志标签mask均true。

下表数字为源日志正观测数，不是模型效果：

| 装备 | train / 571 | validation / 191 | test / 190 |
|---|---:|---:|---:|
| 狂战斧 | 538 | 167 | 176 |
| 电锤 | 32 | 22 | 14 |
| 分身斧 | 454 | 153 | 149 |
| BKB | 0 | 0 | 0 |
| 冰眼 | 32 | 10 | 6 |

只根据train的双类别支持确定四个可建模输出；BKB保留在数据与统计里，标记constant_train_items，
不训练分类器、不计入四装备宏平均，不把恒预测0的高准确率当作学到了BKB出装。
冰眼测试正例仅6场，后续指标不宜作强结论。

## 后续评估协议（尚未执行）

1. 先做仅train拟合的每装备频率基线，再对比多标签线性基线；不直接跳到深度模型。
2. 主要报告每装备Average Precision（有正例时）及Brier score；ROC-AUC要求两类皆存在。
   AP应同时展示正例率基线，不把稀疏标签下的普通准确率当主指标。
3. 阈值、超参数只看validation，test只做固定方案的留出评估；不能因为test冰眼少而重排数据。
4. 逐项显示分母、正负数、未知数，四装备宏平均的项目由train确定；未定义指标为null，不填0。
5. 不确定性按玩家关联组整体bootstrap，不能按比赛逐行bootstrap假装独立。
6. 同时报告全队列和estimated_carry切片；角色提示不是输入，不把切片认证为真实角色。
7. 最大关联组占train约91%，训练样本数不等于独立训练组数；报告该限制。

## 产物、重验与运行

- `reports/purchase-log-snapshot-952-2026-10-14.json`：任务、来源/代码哈希、完整划分、分组检查、特征、标签、mask及评估计划。不输出玩家账号。
- `src/dota_items/data/purchase_snapshot.py`：构建与重建验证。验证重新审计原始数据、玩家分组、train词表和标签；不信任手改字段。
- `docs/acceptance/purchase-log-snapshot-952-2026-10-14.json`：脱敏汇总与快照哈希。

```bash
PYTHONPATH=src .venv/bin/python scripts/prepare_purchase_snapshot.py --summary reports/purchase-952-summary-2026-10-14.json --output reports/purchase-log-snapshot-new.json
PYTHONPATH=src .venv/bin/python scripts/prepare_purchase_snapshot.py --summary reports/purchase-952-summary-2026-10-14.json --verify reports/purchase-log-snapshot-new.json
```

构建拒绝覆盖；离线重验逐字段比较完整规范化JSON。源文件、摘要或代码变化应另存新版本，不能覆盖旧证据。
本轮新增8项测试，连同购买契约、阵容特征和玩家重叠共63项通过；Ruff与格式检查通过。
未联网采集、未训练、未推送。
