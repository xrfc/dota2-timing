# 复核后事实 v13（U90、U92–U98）

已被[v14](../v14/README.md)取代。

在v12上加入：生效条件说明、用户反馈的真实含义、抽查结果、熊灵技能、减速拆分（`reviews/slow-rulings-001.jsonl`）、无视地形和高空视野（`reviews/terrain-rulings-001.jsonl`）。词表`vocabulary-v13.json`，规则`rules-v7.json`。共3176行：接受2489，排除687。

| `basis` | 行数 | 程序算确认吗 |
|---|---|---|
| `two_ai` | 2471 | 不算 |
| `user` | 435 | 算 |
| `user_spot_check` | 148 | 算 |
| `user_corrected` | 2 | 算 |
| `field` | 120 | 算，但这是游戏字段依据，不是用户批准 |

- **`condition_notes`**：2443行有AI写的条件说明，全量补漏和减速拆分新增的行大多没有。只供阅读。
- **抽查**：含第一轮93条标记和第二轮截至2026-11-05写出的111条（`reviews/u5-spot-check-002/verdicts-2026-11-05.jsonl`）。第二轮之后标的要重新导出。
- **`disputed_by_user`**：用户标错、还没裁定的行，不论原来算什么依据。现在0行。
- **`unattached_feedback`**：33条旧抽查反馈找不到对应行，保留原话。其中有用户问“这个东西是在哪读出来的？是7.41f吗”，现在还没回答。
- **没有修的**：v4按“技能+机制”去重的写法还在冻结代码里，改了旧版本就复现不了。第7、8轮核对没有发现因此丢失的记录，第3–5轮无法用同样办法核对。

- **无视地形**：63行，其中50行算AI记录：36行来自用户规则“跳跃和冲刺都算”加Codex分类，其余14行来自旧飞行迁移或说明写明。地雷滚滚没算，它的说明写碰到地形会停，留在穿树。
- **退役词条**：`retired_term_rows`共49行，新增了“飞行”的排除行。

未做：`patch_verified=false`；只读文字，未运行游戏；U5第一批未看完。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v13.py --output <新目录>
```
