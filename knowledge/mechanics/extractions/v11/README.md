# 复核后事实 v11（U81、U83）

在v10上写入全量补漏和U83裁定（`reviews/audit-adoptions-001.jsonl`）。词表`vocabulary-v10.json`，规则仍是`rules-v4.json`。共3127行：接受2433，排除694。

| `origin` | 行数 | 含义 | 算用户确认吗 |
|---|---|---|---|
| `user_ruling`（另更新4条已有行） | 13 | U83裁定 | 算 |
| `full_audit_both` | 158 | Claude和Codex各自提出 | 不算 |
| `full_audit_sequential` | 284 | Codex提出，Claude看过依据后认同 | 不算 |
| `full_audit_round2` | 60 | 第二轮，同上 | 不算 |
| `assistant_proposal` | 20 | Claude提出，用户未反对 | 不算 |

已被[v12](../v12/README.md)取代。未复查：第1–8轮Codex很可能是默认强度，已接受的旧记录这次没有重新判断对错；原有AI接受、这次Codex没提到的56条留给U5抽查。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v11.py --output <新目录>
```
