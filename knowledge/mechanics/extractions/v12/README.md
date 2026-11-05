# 复核后事实 v12（U85–U89）

在v11上写入第1–8轮复查的裁定和控制分类细分（`reviews/recheck-rulings-001.jsonl`，由`reviews/full-audit-004/make_rulings.py`生成）。词表`vocabulary-v11.json`，规则`rules-v5.json`。共3109行：接受2413，排除696。

| `basis` | 行数 | 算用户确认吗 |
|---|---|---|
| `two_ai` | 2542 | 不算 |
| `user` | 396 | 算 |
| `user_spot_check` | 51 | 算 |
| `field` | 120 | 算 |

- `move`操作只改机制名，`basis`不变，并记`renamed_from`。按新分类搬过去的`two_ai`行没有用户逐条确认。
- `retired_term_rows`放退役词条“强制行为”“限制位移”下没有搬走的25行（排除22，接受3）。这3条接受行是诱捕、狂战士之怒、疯狂生长，已由缠绕或捆缚覆盖。
- Codex提出但未写入的（用户交给助手判断）见[U89](../../../../docs/decisions/2026-11-04-recheck-rulings.md)；冰川（魔晶）的创造地形写入，只算AI一致。

未做：U5抽查；`patch_verified=false`；只读文字，未运行游戏。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v12.py --output <新目录>
```
