# v2 比赛级随机划分与模型输入（2026-10-21）

> 2026-10-22文档整理：本页为已执行的数据生成记录，保留原文，不再维护当前开发路线。最新流程及任务统一见[数据](data-prep-progress.md)、[模型](model-foundation.md)、[总路线](roadmap.md)。下方“当前／下一步／未训练”均按原记录日期解释。

## 授权与研究范围

用户于10:21明确授权来源/去重/标签核验、固定seed=42的80/20比赛级随机划分、生成模型输入及支持数报告。不授权真实训练、网络采集、依赖安装、提交或推送。允许玩家重叠，严格玩家隔离延后；本方案替代旧整组件target20建议，不覆盖任何v1产物。

目标仍是7.41f主宰在游戏时间[0,1800)五种装备的有效源购买日志出现情况，顺序bfury、maelstrom、manta、black_king_bar、skadi。位置1是请求口径，并非独立验证。负例表示合法日志未记录，不代表实际未购买；缺失保留null/false mask，不从终局装备回填。

## 确定性随机协议

实现选择：复用项目的哈希随机排序方式，按SHA256(json_bytes([42, match_id]))升序、match_id打破并列。前floor(N/5)场归验证，其余训练；清单内部按ID排序保存。不是Python shuffle或sklearn随机划分，因此同一个seed不意味着与它们成员相同。

规则在首次读取本轮划分支持数前确定；无标签分层，无换seed找成绩。N=1990时为1592/398。旧已查看留出进入新开发队列，没有独立最终测试，test清单为空。只报告玩家重叠，不要求整组件隔离；group_id保留扩展身份图真实组件含义，不伪造独立组。

## 生产入口与边界

- 纯数据构造：data.random_cohort_snapshot.random_split / assemble_snapshot。后者只接收生产入口已核验的行，不声称独立验证来源。
- CLI：scripts/prepare_random_cohort.py。复用build_audit重放旧952快照、批次计划/收据和新批预检，并通过已登记生产者迁移严格比较冻结审计，非实现字段不得漂移。
- 逐候选检查来源哈希、唯一ID、目标英雄和补丁时间，重算源日志标签；旧952标签/mask保持逐行一致，两批标签汇总与重建审计一致。
- assemble_snapshot仅从训练行拟合阵容词表。每侧英雄multi-hot加unknown_count，不含账号、赛后状态或标签派生特征。
- 两个split均通过既有modeling.batch.adapt_snapshot读取为X/y/mask，不调用fit_model。
- 所有data/reports旧文件运行前后比对SHA256，输出目录已存在则拒绝；complete.json最后写入。失败的目录不自动删除或覆盖。
- 旧排除原始文件有缺失，只能查历史收据；不把这部分称作原始数据完整重放。来源时间一致不是客户端补丁认证。

## 命令

在仓库根目录使用现有.venv，生成命令的输出目录必须不存在：

~~~bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/prepare_random_cohort.py \
  --old-root data/purchase-1000-2026-10-14 \
  --new-root data/purchase-additional-1000-2026-10-15 \
  --summary reports/purchase-952-summary-2026-10-14.json \
  --snapshot reports/purchase-log-snapshot-952-2026-10-14.json \
  --audit reports/public-reader-2026-10-17/cohort-audit.json \
  --output reports/cohort-random-v2-2026-10-21
~~~

同一命令增加--verify可从源重建并比较已保存载荷及完成收据哈希；不重写输出、不训练。

产物：snapshot.json（含任务契约、词表、编码、标签/mask、支持数）、split.json（规则及成员）、sources.json、source-audit.json、report.json、protection.json、complete.json。逐场数据和成员清单仅保留在ignored reports，不发布。

## 验证状态

实际生成reports/cohort-random-v2-2026-10-21/，1990场均保留，唯一比赛1990，无训练/验证比赛ID重叠。训练1592、验证398、test为空。

- 训练词表127英雄，特征256列（双方各127英雄+1未知计数）；验证未出现词表外英雄。X为1592×256 / 398×256，y与mask为1592×5 / 398×5，两个split均通过实际消费者适配。
- 成员SHA256：5810a1a97ce12d3c07bad99ede29c8b4d107ea430e2e145291e480ac50c77dd8。
- 完成收据SHA256：c2652a0da639a150de7e35573af613eb7607a66eb4e0e990b08ae501450a2032。
- 7862项既有data/reports文件前后哈希一致；旧952标签及mask逐行保持一致。
- 审计重放仅接受已登记的data/producer_migration.py实现指纹变化，非实现字段不变。不是跳过哈希校验，也不冒充精确旧源码重放。
- 训练/验证共享683个已知玩家，其中44个账号两侧都作为目标主宰出现；按已批准规则保留，不认证账号背后的人类身份。

| 装备 | 训练正/负/未知 | 验证正/负/未知 |
|---|---:|---:|
| 狂战斧 | 1445/147/0 | 372/26/0 |
| 电锤 | 134/1458/0 | 25/373/0 |
| 分身斧 | 1268/324/0 | 324/74/0 |
| BKB | 2/1590/0 | 0/398/0 |
| 冰眼 | 74/1518/0 | 12/386/0 |

五项目标训练侧机械上都具备双类别，但BKB仅2正例不代表适合稳定建模。建议主模型比较用其余四项；BKB保留标签和描述，不用于正类识别能力结论，具体训练目标在训练授权时确定。BKB验证无正例，ROC-AUC不可定义，AP无正类排序解释；可以计算全负例Brier，但不代表识别购买的能力。冰眼验证仅12正例，估计不稳定，不以一次分数做强结论。

本轮相关专项344项通过，包含19项新增回归；新增三份Python文件Ruff lint/格式通过。覆盖排序/标签无关性、同组件可跨split、重复与非法ID、train-only词表、未知mask、消费者读取、现有输出拒绝、来源失败不创建目录和保护文件变更拒绝。
未做串行全库验收（本轮未申请全仓停写窗口），专项不冒充全量。未联网采集、真实训练、安装依赖、提交或推送。第二次完整来源重放已成功（退出码0）：重新从源生成的五份核心载荷逐字节一致，全部完成收据载荷哈希通过；未重复生成或覆盖产物。
