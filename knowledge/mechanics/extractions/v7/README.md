# MK-T3 复核后事实 v7（U70）

> 已被[v8](../v8/README.md)取代，保留不改。

在v6上写入黑皇杖、末日、回光返照三处补充，并加入技能备注和规则计算结果。这是MK-T5应该读取的入口。

| 文件 | 内容 |
|---|---|
| `facts-v7.json` | 字段同v6，另有`skill_notes` |
| `rules-evaluation.json` | `rules-v1.json`每条规则算出的来源和目标 |
| `delta-vs-v3.json`、`manifest.json` | 改动明细和哈希 |

局限同v6。规则只说机制关系，不说“该出”；第12、15条要到T5才有目标，第20条的光环待定。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v7.py --output <新目录>
```
