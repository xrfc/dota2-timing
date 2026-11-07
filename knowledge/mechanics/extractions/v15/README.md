# 复核后事实 v15（U99、U100）

> **已被取代**（MK-T6f）：这是旧版本，保留用于复现。当前知识见`knowledge/mechanics/current.json`，被取代清单见`knowledge/superseded.json`。

已被[v16](../v16/README.md)取代。

直接读冻结的v14，写入U99–U100（`reviews/v15-inputs-001.json`）和第二轮抽查最后46条标记（`reviews/u5-spot-check-002/verdicts-2026-11-06b.jsonl`）。词表`vocabulary-v13.json`，规则`rules-v8.json`。共3176行：接受2482，排除694。

| `basis` | 行数 | 程序算确认吗 |
|---|---|---|
| `two_ai` | 2387 | 不算 |
| `user` | 443 | 算 |
| `user_spot_check` | 224 | 算 |
| `user_corrected` | 2 | 算 |
| `field` | 120 | 算，但这是游戏字段依据，不是用户批准 |

- **R12**：按用户名单定目标，10个英雄不算，食人魔魔法师和冥魂大帝只在有A杖时例外。展开后的规则在`rules-expanded.json`。
- **R13拆成R13（林肯格挡）和R23（莲花反弹）**：变形、感染、技能窃取、超大米波摔扔只被格挡；死亡搜寻、幽鬼之刃按说明排除，待用户确认。现在没有待定规则。
- **单体指向**：龙破斩、旋风飞斧（远程）、裂地尖刺、地穴虫群、火焰气息、冰火交加改为不算（固定方向的范围伤害）。
- **Black Grimoire**：用户说7.41f已经没有，移到`retired_rows`；状态表见`retired-items-v2.json`。
- U5第二轮抽查结束，共192条：对176、错7、不确定9。

未做：`patch_verified=false`；只读文字，未运行游戏。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v15.py --output <新目录>
```
