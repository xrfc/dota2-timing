# 复核后事实 v20（U113，MK-T6c）

事实行、规则求值和v19完全相同。`numeric_upgrades`（69组“升级只改数值，不记机制”）每组新增`ruling`，写明是谁裁定的：

| 来源 | `ruling.how` | 决定 | 组数 |
|---|---|---|---|
| 用户逐条裁定（`reviews/user-rulings-001.jsonl`，带`review_id`、原备注和日期） | `user_ruling` | U65 | 3 |
| 同上 | `user_ruling` | U66 | 18 |
| 同上 | `user_ruling` | U72 | 19 |
| U65第1条通用规则：A杖、魔晶升级只减冷却时不记机制 | `rule` | U65 | 29 |

U65的通用规则是助手建议经用户“其他按你的判断”成为决定（见`docs/decisions/2026-11-04-round7-rulings.md`）。构建时每组必须恰好对上一个来源，裁定文件里的每条数值裁定也必须用上，否则报错（`data.mechanics_facts_v20`）。

未做：`patch_verified=false`；只读文字，未运行游戏。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v20.py --output <新目录>
```
