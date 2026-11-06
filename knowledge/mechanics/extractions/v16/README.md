# 复核后事实 v16（U101–U103）

直接读冻结的v15，写入U101–U103（`reviews/v16-inputs-001.json`），并按反馈身份重新计算每行的反馈依据。词表`vocabulary-v13.json`，规则`rules-v9.json`。共3177行：接受2481，排除696。

| `basis` | 行数 | 程序算确认吗 |
|---|---|---|
| `two_ai` | 2373 | 不算 |
| `user` | 459 | 算 |
| `user_spot_check` | 223 | 算 |
| `user_corrected` | 2 | 算 |
| `field` | 120 | 算，但这是游戏字段依据，不是用户批准 |

- **反馈重算**：有反馈或纠正的252行按`data.mechanics_feedback`重新计算，和v15比0行变化（`feedback_changes`为空）。原因分布：抽查确认且内容一致223、按纠正记录9、保留原有裁定9、没有能确认的反馈11。
- **纠正迁移**：10条旧纠正都能对上原反馈，9条各解决1条“错”，圣洁吊坠主动那条没有“错”可解决，单独成立（`reviews/feedback-resolutions-001.json`）。
- **U101**：幽鬼之刃会被林肯挡、不会被莲花弹，并记场地魔法和无视地形；死亡搜寻被林肯和莲花都会失效但不反弹（技能备注）；无影拳记无敌。
- **单体指向筛查**（`reviews/full-audit-009/`）：用户逐个确认。龙破斩等6个（U100）和震荡波、潮汐使者（U103）不算单体指向；苍穹震击、雪球等12个保持。巨浪、阴邪凝视有A杖时不触发林肯和莲花，只记在技能备注里，规则还读不到这个条件。

未做：`patch_verified=false`；只读文字，未运行游戏。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v16.py --output <新目录>
```
