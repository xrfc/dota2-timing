# MK-T3 复核后事实 v6（U65）

> 已被[v7](../v7/README.md)取代，保留不改。

v6不重新抽取已有证据，只在冻结的v3上叠加全部判断，并加入词表v6新增机制的第7轮证据。这是MK-T4、T5应该读取的入口。

优先级：用户裁定 > 用户U5抽查 > `IsBreakable`（仅可被破坏）> 两个AI一致。

| 文件 | 内容 |
|---|---|
| `facts-v6.json` | `rows`逐组判断、依据、条件和备注；`numeric_upgrades`升级只改数值的组及字段值；`retired_rows`退出装备；`deferred_rows`当前中立物品；`field_observations`字段观测 |
| `delta-vs-v3.json` | 相对Claude改判的组、新增组、退出和暂不纳入的组 |
| `manifest.json` | 输入、实现、输出的SHA-256 |

**`basis`含义：** `user:U*`用户裁定；`user_spot_check`用户抽查；`field:IsBreakable`游戏文件；`two_ai`Claude和Codex标签相同。只有`user*`算用户确认。

局限：`patch_verified=false`；未运行游戏；幻象字段19个和只在A杖、魔晶或天赋下生效的56个候选未审；退出装备按字段推断；新增机制的证据靠关键词和字段找，可能有漏；按“只改数值不记机制”只查了文字含数值变化词的41组，其余93组没有逐组看。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v6.py --output <新目录>
```
