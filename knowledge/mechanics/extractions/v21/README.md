# 复核后事实 v21（U114，MK-T6g）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

事实行和v20相同，只有17行改了依据：装备属性“+N Health Regeneration”记为治疗、原依据`two_ai`的行，依据改为`user:U114`（用户：小额被动生命恢复算治疗，对线回血，时间长了有价值）。判断本身不变；另外2行（狂战斧、臂章）原来就是用户抽查确认，不动。逐行清单在`reviews/v21-inputs-001.json`。

依据统计：`two_ai` 2373→2356，`user` 459→476。克制关系边数和“两端都确认”的边数不变（3575、149）。

未做：冻结包`patch_verified=false`；版本核对结果见`current.json`。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v21.py --output <新目录>
```
