# 数据接口交接（2026-10-16）

2026-10-20：新增独立的[任务绑定 /2 快照接口](../task-contracts.md)，经显式
`--task-id` 生成并由模型适配器检查。现有 handoff/1 包继续使用冻结 /1 快照，
不自动迁移、补写范围声明或放宽来源指纹检查。

## 当前公共接口：public-reader/1迁移（2026-10-17收尾）

当前交接目录更新为reports/public-reader-2026-10-17/handoff/。读取入口仍为dota_items.handoff.bundle.verify_bundle。
新增公共来源读取API及完整操作命令见[公共读取接口](../public-source-reader.md)。采样/玩家关联不再引用审计私有读取。
新包的snapshot.json和summary.json仍复制旧952场原字节；模型字段、254维特征、571/191/190划分、mask语义全部不变。
manifest与cohort-audit增加可选producer_migration=public-reader/1，必须一致；旧包两处均无此字段仍可读。
现行代码重建旧产物须显式--allow-producer-migration；默认严格校验继续拒绝旧源码哈希。
兼容重建仅容许登记的实现元数据变化，不是旧生产者精确复现，不放松来源/内容检查，也不授权训练。
新审计路径：reports/public-reader-2026-10-17/cohort-audit.json；包内INTERFACE为打包时冻结副本。
以下10/16及凌晨refactor路径、无迁移参数的命令属于旧生产者历史，不是当前默认重建命令。


## 当前读取与生产者 — 2026-10-17

独立读取使用dota_items.handoff.bundle.verify_bundle，不加载cohort审计；旧data.cohort_handoff导入兼容。完整语义由modeling.batch检查。
本轮审计：reports/refactor-2026-10-17/cohort-audit.json；新包输出：reports/refactor-2026-10-17/handoff/。新旧审计仅cohort生产者哈希变化，统计、类型、顺序、研究边界一致。
重新打包必须使用当前实现匹配的新审计，不跳过哈希。旧包保持只读；新包仍复制旧952快照，不生成新增1,038场建模快照。见[指南](../modular-maintenance.md)。
下方10/16路径和指纹为历史；冻结包内INTERFACE是当时说明快照，不随本页变化。

## 当前加固版本（同日集成更新）

当前可复现交接包为 `reports/purchase-cohort-compatibility-2026-10-16/handoff/`；
旧包仍保持原字节且可只读加载。新旧审计仅cohort生产者哈希不同，统计/队列/研究边界完全一致。
旧生产者精确字节保存在 `reports/purchase-cohort-producer-archive-2026-10-16/`。
不能用当前生产者直接重新打包旧审计：哈希失配必须报错，不能改写旧证据或跳过检查。

当前读取器要求固定五载荷，拒绝重复JSON键、非有限数、错误schema/声明、非法哈希、
缺项/额外清单项、路径别名/越界、包根/manifest/载荷符号链接。
这仍不是完整语义校验、真实性认证或训练授权；模型适配器另外校验列序/编码/mask等语义。
打包先捕获并校验来源字节，复核落盘载荷后最后写manifest；失败保留现场，用全新目录重试。
包内INTERFACE.md是打包时的说明快照，不会随本文更新；不得修改它破坏包身份。

## 用途边界

本包只复制旧952场冻结快照，附新增数据审计；不产生新增1,038场建模快照，
不改变旧split、标签、词表或研究用途，不授权任何真实训练/截距对照。
模型侧只读消费，结果写独立目录；不建立指向数据侧可变目录的共享写入链接。
包仅本地保存，没有复制到模型worktree，也未发布。

## 文件与身份

- manifest.json：purchase-data-handoff/1，固定文件清单、SHA-256、原来源绝对路径。
- snapshot.json：旧purchase-log-modeling-snapshot/1原字节副本，952场，571/191/190。
- summary.json：旧来源摘要原字节副本；原始缓存不包含在包中。
- cohort-audit.json：离线分布、连通组、排除记录和证据哈希，不是模型评估。
- synthetic-reader-example.json：纯人工单行读取样例，22维，含masked null；
  不是完整来源重建快照，没有可用验证/测试集，不可训练。
- INTERFACE.md：本文。

哈希只验证文件身份，不认证内容真实或研究授权。manifest自身的哈希应从独立交付记录比对。
verify_bundle仅检查清单、路径边界、字节哈希和schema；不是完整语义加载器。
完整旧快照重验须在数据侧使用verify_snapshot(snapshot, summary)，需要原始路径、缓存、
知识证据及对应实现；复制本包不能实现异机完整来源重放。打包器会先重建旧快照并验证审计证据哈希，
但不会重新计算审计统计；初次和兼容收尾分别完成审计重建与比较，详见数据进度说明。

## 字段与顺序

- task.candidate_items固定为bfury、maelstrom、manta、black_king_bar、skadi。
- task.window=[0,1800)，1800秒不含。1=合法源日志出现；0=该日志未记录，不证明实际未购买。
- samples[].labels和label_mask逐装备对齐；mask=false时必须排除该标签，不能把null转0。
- X仅samples[].encoded_features；列名与顺序来自preprocessing.columns。
  原快照126英雄、254列；读取器必须从元数据获得维度，合成例故意不是254维。
- 两侧multi-hot分别按preprocessing.vocabulary顺序编码，各随后附unknown_count。
  未知英雄不能扩充已冻结词表；词表只由train拟合。
- features.ally_hero_ids / enemy_hero_ids是阵容身份；不使用装备信息构造X。
- match_id、group_id、source_sha256、role_hint仅元数据，不进X；账号不在快照输出。
- split沿用快照；不得随机重划分。group_id用于整组抽样，不把单场当独立样本。
- train_model_items由训练集双类别支持决定。旧BKB常量未训练；新增2个BKB正例不改变旧输出资格。
- 旧test已经用于探索性分析，不能称未查看的最终测试集，也不能用于新一轮选模。

## 只读加载（不训练）

在本数据仓库根目录：

```python
from pathlib import Path
from dota_items.handoff.bundle import verify_bundle

bundle = Path("reports/public-reader-2026-10-17/handoff")
snapshot = verify_bundle(bundle)
columns = snapshot["preprocessing"]["columns"]
items = snapshot["task"]["candidate_items"]
rows = [r for r in snapshot["samples"] if r["split"] == "train"]
assert all(len(r["encoded_features"]) == len(columns) for r in rows)
assert all(len(r["labels"]) == len(r["label_mask"]) == len(items) for r in rows)
# 仅装载；此处不调用fit、评估或选模。
```

## 历史打包命令（当前命令见顶部公共读取接口）

先按 [数据进度中的可重现命令](../data-prep-progress.md) 运行audit与逐项比较，
确认统计/队列/边界不变。下例使用已完成该验证的当前生产者审计；如果实现再次变化，
必须重新生成新审计并比较，不可跳过来源哈希。输出必须是新的不存在目录。

```bash
PYTHONPATH=src .venv/bin/python scripts/package_purchase_handoff.py \
  --summary reports/purchase-952-summary-2026-10-14.json \
  --snapshot reports/purchase-log-snapshot-952-2026-10-14.json \
  --audit reports/purchase-cohort-compatibility-2026-10-16/cohort-audit.json \
  --interface docs/handoff/purchase-data-interface.md \
  --output reports/purchase-data-handoff-replay-REPLACE-WITH-UNIQUE-NAME
```

失败可能留下未完成目录，缺manifest不算完成；保留现场，另用新目录重试。
