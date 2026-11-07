# MK-T3 复核后事实 v4（U54）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

> 已被[v5](../v5/README.md)取代，保留不改。

v4不重新抽取，只在冻结的v3证据上叠加全部判断，是MK-T4、T5应该读取的入口。

优先级：用户裁定 > 用户U5抽查 > `IsBreakable`（仅可被破坏）> 两个AI一致 > 只有Claude。

| 文件 | 内容 |
|---|---|
| `facts-v4.json` | `rows`逐组判断、依据、条件和备注；`retired_rows`退出装备；`deferred_rows`当前中立物品（U27范围外，U55暂不纳入，以后直接用）；`field_observations`字段观测 |
| `delta-vs-v3.json` | 相对Claude改判的组、新增组、退出和暂不纳入的组 |
| `manifest.json` | 输入、实现、输出的SHA-256 |

**`basis`含义：** `user:U*`用户裁定；`user_spot_check`用户抽查；`field:IsBreakable`游戏文件；`two_ai`Claude和Codex标签相同；`claude_only`只有Claude审过。只有`user*`算用户确认，`two_ai`和`claude_only`不是。

局限：`patch_verified=false`；未运行游戏；幻象字段19个和只在A杖、魔晶或天赋下生效的56个候选未审；退出装备按字段推断；`claude_only`的组尚未被第二方看过。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v4.py --output <新目录>
```
