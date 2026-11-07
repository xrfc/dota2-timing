# 复核后事实 v23（U118）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

英雄特性抽查后的调整（用户“按我标的先全部做调整”）：

- **狼人·召狼的“闪避”改为排除**（`user:U118`）：魔晶让精灵狼获得闪避，不是狼人自身闪避，不符合词表“闪避”的定义。克制关系里依赖这一行的7条装备关联随之去掉（3575→3568）。
- 神谕者加入魔法爆发名单在特性映射v5里（`knowledge/hero-traits/trait-mapping-v5.json`），不在事实里。
- 涤罪之焰的魔法伤害本来就记在官方伤害类型字段里，事实不改；抽查页补显示伤害类型。

接受2482→2481，排除696→697。清单见`reviews/v23-inputs-001.json`；抽查标记见`reviews/traits-check-001/verdicts-2026-11-07.jsonl`。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v23.py --output <新目录>
```
