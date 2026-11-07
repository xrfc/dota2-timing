# 知识读取接口（U124第②步，2026-11-07）

路线A、路线B读取机制知识都通过`dota_items.data.mechanics_api.Knowledge`，不直接解析知识库内部的JSON。内部文件格式以后可以变，这个接口的含义不变（`API_VERSION = "mechanics-api/1"`）。

```python
from dota_items.data.mechanics_api import Knowledge

kb = Knowledge()  # 读current.json并校验全部版本
kb.version  # 补丁、是否已核对、读了哪些文件及哈希
kb.team_trait_sum([1, 29, 33], "disables")  # 赛前用：基础数合计
kb.trait_count(94, "disables", "with_upgrades")  # 含A杖、魔晶
kb.heroes_owning(["life_stealer_rage"])  # {54}
kb.mechanisms("huskar_life_break")  # 接受的机制、条件、是否确认
kb.rule_target_heroes("R13")  # 规则目标技能的所属英雄（候选）
kb.relation_holds("R13", "tidehunter_gush", {"scepter"})  # False
```

## 固定的含义

| 概念 | 含义 |
|---|---|
| 版本 | `kb.version`记录补丁（现为7.41f，已核对）和每个读取文件的路径、哈希；产物应把它写进自己的manifest |
| 基础数 / 含升级数 | `base`只算不需要A杖、魔晶就有的技能，赛前可知；`with_upgrades`再加上只在升级后才有的（U104、U105） |
| 确认状态 | `confirmed`只在依据是用户（`user*`）或游戏字段（`field`）时为真；`two_ai`不算确认 |
| 条件 | 规则目标的`when`（基础、A杖、魔晶、装备、任意）和`unless`（哪种升级会让它不成立） |
| 说不准 | `relation_holds`返回True、False或None；None表示升级情况未知，调用方要单独处理，不能当成成立 |
| 未知名字 | 不认识的英雄、特性、技能、规则一律抛`KeyError`，不会悄悄返回空 |
| 关联 | 规则算出的是候选，不是逐对验证过的关系；`rule()`给出`status`（候选/待定）和没有计算的字段 |

## 当前使用者

- 路线A：`modeling.situational_triggers`（M2b针对装触发）、`scripts/build_m2b_triggers.py`。
- 路线B：B0起会用同一个接口读逃生、控制等机制。

需要新的读法时，在接口里加方法并写测试（`tests/test_mechanics_api.py`），不在调用方直接读内部文件。
