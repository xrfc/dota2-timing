# 复核后事实 v14（U96–U98）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

已被[v15](../v15/README.md)取代。

直接读冻结的v13（`extractions/v13/facts-v13.json`），写入Astra复核查出的裁定遗漏（`reviews/v14-inputs-001.json`）和第二轮抽查新增的35条标记（`reviews/u5-spot-check-002/verdicts-2026-11-06.jsonl`）。词表`vocabulary-v13.json`，规则`rules-v7.json`。共3178行：接受2489，排除689。

| `basis` | 行数 | 程序算确认吗 |
|---|---|---|
| `two_ai` | 2437 | 不算 |
| `user` | 438 | 算 |
| `user_spot_check` | 181 | 算 |
| `user_corrected` | 2 | 算 |
| `field` | 120 | 算，但这是游戏字段依据，不是用户批准 |

- 比v13多：暗影步的眩晕改记用户确认；天光现世、星破天惊的“不算无视地形”成为明确的排除行。
- 第二轮抽查共146条：对133、错6、不确定7。
- `disputed_by_user`现在0行；`condition_notes`有2443行；`unattached_feedback`有33条，其中“这是7.41f吗”还没回答。
- 复现测试现在同时比较事实和规则求值结果。

未做：`patch_verified=false`；只读文字，未运行游戏；Astra复核的是v13。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v14.py --output <新目录>
```
