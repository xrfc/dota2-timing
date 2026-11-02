# U5抽查：用户标记快照与交给Codex的剩余队列（2026-11-02，U42）

| 文件 | 内容 |
|---|---|
| `user-verdicts-2026-11-02.json` | 私有抽查页导出的用户标记，93组：对85、不确定5、错3 |
| `codex-queue.json` | 交给Codex的379组（497 − 用户已标93 − Codex第2轮P1已审17 − 不在v3当前证据的8组，后者列在`excluded_not_in_v3`）；`current_decision`为第1轮叠加第4、5轮（U40、U41）及第2版新增组的当前结论 |

交接与回传格式见[Codex抽查交接](../../../../docs/handoff/mk-codex-spot-check.md)；决定见[U42](../../../../docs/decisions/2026-11-02-spot-check-to-codex.md)。`tests/test_mechanics_round3.py`校验队列构成与输入哈希。
