# 复核后事实 v19（U113，MK-T6b）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

事实行和v18完全相同，只换用规则v11。规则v11让每条规则的每个字段都有交代：

- 程序会算的字段照常算；
- 只记录、不计算的字段（`pairs`、`target_exempt_mechanisms`、`parameters`）必须在该规则的`not_computed`里写明字段、原因和用户决定，否则读取时报错（`data.mechanics_rules_v11.check_rule_fields`）；
- 程序不认识的字段一律报错。

目前声明不计算的只有三条，都是用户原来的决定：

| 规则 | 不计算的字段 | 原因 |
|---|---|---|
| R08 | `parameters` | 背景规则，不产生关联；“常规会出”的门槛等B1出装数据（U70、U113） |
| R09 | `target_exempt_mechanisms` | 目标是所有不能穿透的效果，不逐个列出（U68） |
| R19 | `pairs` | 只记方向，不列目标技能（U69） |

`rules-evaluation.json`里这三条带`not_computed`（含原因）；求值结果和v18相同，派生层v9的关联边和v8相同。

未做：`patch_verified=false`；只读文字，未运行游戏。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v19.py --output <新目录>
```
