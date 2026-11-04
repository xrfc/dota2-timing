# 复核后事实 v9（U79）

在v8上写入MK-T5读档案时发现的纠正（`reviews/t5-corrections-001.jsonl`）：召唤物只算有血量的单位、破坏标记残留、主宰和巫医的细节。规则用`rules-v3.json`，结果在`rules-evaluation.json`。文件结构和局限同v8。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v9.py --output <新目录>
```
