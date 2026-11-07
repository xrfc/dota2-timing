# 复核后事实 v10（U80）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

在v9上补第4轮跳过的7条幻象（`reviews/t5-corrections-002.jsonl`）：娜迦海妖·镜像、幻影斧、恐怖利刃·倒影、百戏大王·哈哈镜、幽鬼·鬼影重重、幽鬼·如影随形、黑暗贤者·普通一拳。规则是`rules-v4.json`（第20条不再以恐怖利刃·倒影为目标，U81），词表仍是`vocabulary-v9.json`。

**已知局限：漏记。** 官方说明不用关键词的技能大量没有记录（如莱恩·妖术没有“妖术”，风暴之灵·球状闪电没有“自身位移”），见`reviews/recall-check-001/`。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v10.py --output <新目录>
```
