# 复核后事实 v24（U119）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

在v23上加一行：**干扰者·动能栅栏记“减速”**（需魔晶，依据`user:U119`）。用户说明：和动能力场（萨尔框）一样，游戏里不是加地形，而是把碰到的敌人减速到0。官方说明和数值里没写减速，这是用户按游戏实现给的裁定。动能力场在U98已记减速。

动能栅栏因此成为R11、R21（状态抗性、减速抗性）的目标；装备到英雄的关联边数不变（3568，干扰者原来就因为动能力场在这两条里）。行数3178→3179，接受2481→2482。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v24.py --output <新目录>
```
