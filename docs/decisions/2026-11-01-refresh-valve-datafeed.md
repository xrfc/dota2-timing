# U36 授权重新抓取当前Valve英雄数据，用于版本对照

- 背景：U5抽查发现部分技能说明与当前游戏不符。A杖/魔晶部分已由Valve的“是否有该升级”标记识别并在MK-T3 v3中去掉；技能基础描述没有类似标记，只能重新抓取当前接口对照。
- 决定：用户同意（“可以”）重新抓取Valve官网datafeed：`herolist`与127位英雄的`herodata`，英文与简体中文各一份。
- 范围与用途：只用于和2026-10-09快照逐条对比，标出改动过的技能，供机制证据和复核使用。不授权训练，不改变数据划分，也不扩大其他数据用途（Q7不变）。
- 产物规则：新快照放新目录，旧快照`knowledge/hero-capabilities/sources/`及其清单不覆盖；接口仍不带补丁号，新快照照样记`patch_verified=false`。
- 状态：云端环境的网络策略拒绝连接`www.dota2.com`（代理返回403）。需要用户在环境设置的网络访问里放行该域名，或在本地OpenClaw工作区运行抓取。
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
