# 机制知识库：补丁更新流程（MK-T6e，U113）

新补丁出来后照这个流程走：先找出变了什么，再只复核受影响的部分，最后出新版本。**任何一步都不覆盖旧文件**，旧版本保留用于复现。所有联网步骤只读公开数据；每次联网仍按Q7单独获得用户同意。

## 0. 有没有新补丁（联网，1次请求）

```bash
python scripts/patch_update.py status --output knowledge/mechanics/reviews/patch-update-<日期>/status.json
```

对比Valve官方补丁列表的最新补丁和`knowledge/mechanics/current.json`里的`patch.name`。`update_needed=false`就到此为止；也可以定期跑第1–3步，看有没有不出补丁说明的热更新。

## 1. 抓新快照（联网）

| 来源 | 命令 | 新目录 |
|---|---|---|
| Valve英雄数据（中英文） | `python scripts/refresh_hero_datafeed.py fetch --output <目录>` | `knowledge/hero-capabilities/snapshots/<日期>/` |
| Valve英文装备数据 | `PYTHONPATH=src python scripts/check_patch_knowledge.py fetch-items --output <目录>` | `knowledge/items/sources/itemdata-english-<日期>/` |
| 游戏脚本（第三方镜像，固定提交） | 先用`gh api repos/SteamDatabase/GameTracking-Dota2/commits`找最新提交，再`python scripts/fetch_game_files_snapshot.py --commit <完整SHA> --out <目录>`；装备脚本加`--only scripts/npc/items.txt` | `knowledge/game-files/snapshots/<日期>/` |

## 2. 找出变化（离线）

```bash
python scripts/refresh_hero_datafeed.py diff --old <旧英雄快照>/sources --new <新英雄快照>/sources --output <英雄差异.json>
python scripts/patch_update.py item-diff --old <旧装备目录> --new <新装备目录> --output <装备差异.json>
python scripts/patch_update.py game-diff --old <旧游戏快照> --new <新游戏快照> --output <游戏差异.json>
```

- 英雄差异：英雄/技能的增删，文字字段（说明、A杖、魔晶、备注）和数据字段（冷却、驱散、免疫等）的变化。
- 装备差异：装备增删，说明、备注、属性数值的变化。
- 游戏差异：按技能或物品块比对，不按文件比，所以能看到哪个技能的哪个键变了。

## 3. 影响范围（离线）

```bash
PYTHONPATH=src python scripts/patch_update.py impact --hero-diff <英雄差异.json> \
    --item-diff <装备差异.json> --game-diff <游戏差异.json> --output <影响.json>
```

输出：每个变化的对象和原因（英雄级变化——命石、天赋、英雄删除——按英雄注册表展开到该英雄的全部技能，原因里标“hero-level”；新英雄展开不了，列在`manual_review`里要人工看，U124）；要复核的事实行（含已排除的行）；涉及的数值升级；碰到的规则；受影响的装备关联边数；变了但知识库里没有的对象（可能是新技能、新装备，要考虑补抽取）。**这只是复核范围，不是判断。**

## 4. 复核

- 只复核`impact`列出的行，用和MK-T3一样的方式：AI审查＋用户裁定；数值变化只影响`numeric_upgrades`时，看是否仍是“只改数值”。
- 新技能、新装备：按词表抽取候选，再审查。
- 删除的技能、装备：事实行移到`retired_rows`，装备在`retired-items`里标`obsolete`。
- 用户裁定写进`docs/decisions/`。

## 5. 出新版本

1. 新事实版本：在上一版冻结包上叠加（像v14以后那样），复核结果放`reviews/`里的新输入文件；词表或规则要改就先出新版本。
2. 重新求值规则，重建派生层（新`derived-v*`）。
3. 改`scripts/build_mechanics_current.py`里的列表，把`PATCH`改成新补丁并设`verified=false`，运行生成`current.json`。
4. 跑版本核对：`scripts/check_patch_knowledge.py check`，逐条看标记，写`review.json`和`README.md`；都核对完再把`PATCH.verified`设为`true`。
5. 全量检查：`scripts/check.py --scope all`。

## 6. 文档

同步`knowledge/mechanics/README.md`、各版本README、`docs/knowledge-framework.md`、计划§7、交接文档、`CHANGELOG.md`；用户决定写`docs/decisions/`。

## 试跑记录

`knowledge/mechanics/reviews/patch-update-dryrun-001/`：2026-11-06用真实数据试跑——`status`显示仍是7.41f，不需要更新；用10-09到11-01的英雄差异（7处中文文字修订）跑`impact`，列出7个对象、29行事实、12条规则、20条装备关联要复核。这次只是演示流程，没有据此改知识库（当时是翻译修订，U36已看过）。试跑用的是英雄级展开之前的版本，所以齐天大圣的英雄字段变化只列在“知识库里没有”；现在会展开到他的技能。
