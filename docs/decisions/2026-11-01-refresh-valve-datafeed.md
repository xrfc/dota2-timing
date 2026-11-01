# U36 授权重新抓取当前Valve英雄数据，用于版本对照

- 背景：U5抽查发现部分技能说明与当前游戏不符。A杖/魔晶部分已由Valve的“是否有该升级”标记识别并在MK-T3 v3中去掉；技能基础描述没有类似标记，只能重新抓取当前接口对照。
- 决定：用户同意（“可以”）重新抓取Valve官网datafeed：`herolist`与127位英雄的`herodata`，英文与简体中文各一份。
- 范围与用途：只用于和2026-10-09快照逐条对比，标出改动过的技能，供机制证据和复核使用。不授权训练，不改变数据划分，也不扩大其他数据用途（Q7不变）。
- 产物规则：新快照放新目录，旧快照`knowledge/hero-capabilities/sources/`及其清单不覆盖；接口仍不带补丁号，新快照照样记`patch_verified=false`。
- 状态：起初云端网络拒绝`www.dota2.com`（403）；用户改为完全访问后完成，见下文“结果”。
- 来源：2026-11-01用户消息“可以，你现在获取方式是怎么获取的？”，回复的是助手的问题“要不要我重新抓一次当前的Valve英雄数据，和现在的版本逐条对比？”

## 运行方法（`scripts/refresh_hero_datafeed.py`）

```bash
# 1. 抓取（联网；云端须放行 www.dota2.com，或在本地工作区运行）
python scripts/refresh_hero_datafeed.py fetch --output knowledge/hero-capabilities/snapshots/2026-11-01
# 2. 与10-09快照对比（离线）
python scripts/refresh_hero_datafeed.py diff \
    --old knowledge/hero-capabilities/sources \
    --new knowledge/hero-capabilities/snapshots/2026-11-01/sources \
    --output knowledge/hero-capabilities/snapshots/2026-11-01/diff-vs-2026-10-09.json
```

- `fetch`：目录已存在就拒绝；保存原始字节、SHA-256与抓取时间，校验每个回复的英雄编号，中英文英雄列表必须一致。
- `diff`：逐英雄、逐语言列出新增/删除的技能，以及改动的文字字段（描述、附注、A杖/魔晶、命石）和其他字段（升级标记、枚举、冷却、蓝耗、数值）。用旧快照自比应为零改动（有测试）。
- 抓到后：Claude按改动清单重算受影响的证据组，另出新版本，旧版本不覆盖。

## 结果（2026-11-01）

- 用户把云端网络改为完全访问后抓取成功：`knowledge/hero-capabilities/snapshots/2026-11-01/`（127位英雄×中英文＋英雄列表，`manifest.json`记哈希与时间）。另取Valve补丁列表`patchnoteslist`仅用于判断版本（`patch-check.json`）。
- **英文：与10-09快照零改动。** 中文：7处翻译修订，不涉及机制——齐天大圣“棒击大地”改名“擎天一击”（名称、魔晶、如意棒法附注随之改），风暴之灵·残影与莱恩·死亡之指补上“多样施法”字样并理顺语句，敌法师闪烁A杖补“下一次”，沉默术士魔晶删一个空格。明细`diff-vs-2026-10-09.json`。
- **版本推断：** 补丁列表最新为7.41f（2026-09-15），两次快照都在其后且英文内容一致，所以技能文字很可能对应7.41f。接口仍无补丁字段，保持`patch_verified=false`。
- 含义：除已由v3去掉的过时A杖/魔晶文字外，技能说明就是Valve官网当前文本；与游戏内表现不符之处（如越界“物理吸血视为技能吸血”、破晓辰星魔晶自减速）不是快照过期，需以游戏内实测为准并逐条记录。机制证据不需重算；中文名称修订留到下次重建登记表时吸收。
