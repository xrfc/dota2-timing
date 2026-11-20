# 7.42补丁预案（2026-11-17，助手起草）

现在所有数据和知识都对应7.41f。外部评估提到7.42可能在2026年11–12月到（追踪站的估计，不是官方消息）。本页写补丁到来后做什么；补丁没到之前不执行。联网检查和采集每次要用户授权。

## 1. 先判断补丁有多大

| 类型 | 例子 | 影响 |
|---|---|---|
| 字母补丁（7.41g） | 数值调整 | 机制知识按流程更新；数据和模型可以继续用，注明混了补丁 |
| 数字补丁（7.42），没改地图 | 新物品、技能重做 | 机制知识更新；出装统计要重采；意识模型先在新数据上验一次再决定 |
| 数字补丁，改了地图 | 地形、野点、塔位、符点变化 | 地图知识全部重做；依赖位置的特征和规则要重验 |

## 2. 逐项清单

| 资产 | 补丁后做什么 | 命令或文档 |
|---|---|---|
| 机制知识库（事实v26、词表v15、规则v13） | 按既有流程找变化、复核、出新版本 | [补丁更新流程](mechanics-patch-update.md)，`scripts/check_patch_knowledge.py`、`scripts/patch_update.py` |
| 保命手段清单、英雄机动能力 | 从新的机制知识重新生成 | `scripts/detect_ganks.py save-means`、`scripts/build_hero_mobility.py` |
| 地图知识（区域草稿v7、定时目标、塔和野点坐标） | 没改地图：核对定时目标的时间；改了地图：重新取上游地图数据、重画区域、重新让用户确认 | `scripts/build_map_knowledge.py`，[地图知识设计](map-knowledge-design.md) |
| 解析器（gem-dota 0.10.0） | 新demo先试解析5场；失败就等解析库更新，不改采集规模 | `scripts/collect_demos.py`试采，[解析器v3设计](parser-v3-design.md) |
| demo数据（1678场，7.41f） | 保留，标明补丁；新补丁另开一个目录重采，不混在一起 | [自动采集demo](demo-collection.md) |
| 路线A的出装统计和针对装触发 | 新补丁数据到了以后重验；在那之前页面注明数据来自7.41f | [M2b触发条件](m2b-triggers.md) |
| 死亡风险基线、胜率模型 | 旧模型在新补丁的200–300场上先测一次（不重训），看平均精度和校准掉多少；掉得多再用新数据重训 | [模型卡](b2-death-risk-baseline.md) |
| 留出集规则（U133） | 不变，按比赛编号划分，新比赛自动落在固定一边 | `data.awareness_split` |

## 3. 这次补丁能学到什么

旧模型在新补丁上的表现是一次现成的“分布变了以后模型还灵不灵”的实验。先测再重训，把掉了多少记下来。

## 4. 需要用户决定的

- 补丁到了以后是否授权联网：检查补丁内容、试采、重采。
- 重采多少场（现在是1500场，约一周）。

## 2026-11-20 执行顺序

1. 已修游戏脚本跨英雄覆盖，保留旧审查包。新版差异、影响及新增对象位于 `knowledge/mechanics/reviews/patch-update-2026-11-19/revision-2/`。新增37个对象，命中事实从2299增至2331行；还须复核新命中及旧清单误归入“仅英雄级变化”的行。
2. 已在 `knowledge/hero-capabilities/versions/7.42/` 单列注册表。构建命令为 `.venv/bin/python knowledge/hero-capabilities/build_profiles.py --snapshot knowledge/hero-capabilities/snapshots/2026-11-19 --target-patch 7.42 --output <新目录>`。英雄身份对照与角色标签沿用旧版固定的 OpenDota 目录。
3. 候选构建用 `PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_overlay.py --spec knowledge/mechanics/reviews/v27-build-draft-001.json --output <新目录>`。枚举含义继承 v2，示例按新快照校验；英雄伤害、驱散、魔耗、免疫字段重建，沿用 U79 排除。候选仅纳入部分裁定；装备字段、IsBreakable、规则、词表、升级数值和技能新增仍需核对。
4. 将 A1、A2、A4、A6、A7 和盲审分歧逐项落实。补齐输入后构建正式 v27 与派生 v18，核对来源、条件和抽样英雄，再切换 current 并验证补丁。
5. 独立修复路线 B 的输入一致性、误报预算比较及树半径检验。7.42 地图坐标等待新版来源，数据与模型验收沿用原有授权。

补核清单：revision-2/fact-review-queue.json 列出 42 条新增命中或旧分类与脚本变化交叉的行；break-field-audit.json 并列 196 个技能的新 IsBreakable 字段与旧裁定，字段缺失保留未知。

### 独立修复的复核结果

- [死亡预警 PR 21](https://github.com/xrfc/dota2-timing/pull/21)：旧预测逐行与原表匹配。在约每小时 25.25 次误报下，5 秒采样战斗前预警占 30.12%，3 秒采样占 30.60%；尚未估计差异的不确定性。
- 树半径修复按原 138 场 7.41f 录像复核，选型半组最佳半径 48 在确认半组为 87.88%，整格基线 87.89%。保留默认整格模型。见[视野 PR 22](https://github.com/xrfc/dota2-timing/pull/22) 的地图设计 §10.6。

候选 004：3,292 行，接受 2,582、拒绝 710，累计归档 79。R09 已写入规则 v14 草案，沿用 U181。噬魂鬼感染和干扰者栅栏触发的其他技能按既有交叉复核入库；用户裁定和双 AI 同意分别记依据。

补核发现半人马、光之守卫、变体精灵、恐怖利刃、巨牙海民和艾欧各一条 U47 的旧拒绝与新增 IsBreakable=1 冲突。候选保留原裁定，发布前核实作用范围。
