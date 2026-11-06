# 复核后事实 v17（U104）

直接读冻结的v16，事实行不变，新增`condition_exceptions`（`reviews/v17-inputs-001.json`），规则v9按条件计算。

- **`condition_exceptions`**：某个升级会让机制不成立。现在2条：巨浪、阴邪凝视有A杖时不算单体指向（U102）。和被排除的升级行分开记，因为那种行多半只表示“升级没加新东西”。
- **`rules-evaluation.json`**：每条规则多了`source_conditions`和`target_conditions`。R12的条件例外（食人魔魔法师、冥魂大帝有A杖时）也变成`unless: scepter`。
- 读法见`knowledge/mechanics/README.md`“当前数据流”。

未做：`patch_verified=false`；只读文字，未运行游戏。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v17.py --output <新目录>
```
