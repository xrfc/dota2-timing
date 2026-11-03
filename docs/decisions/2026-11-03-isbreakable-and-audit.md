# U48 部分破坏记条件；IsBreakable作为依据；排查其他机制

- 背景：[破坏对照](../../knowledge/mechanics/reviews/break-check-001/README.md)。
- 用户决定（2026-11-03原话）：“部分破坏的记条件，可以直接用 IsBreakable，其他机制排查一下吧”。
  1. **部分破坏记条件**：标签仍是可被破坏，游戏文件的Break附注原文记入`break-check-001/break-conditions.jsonl`。
  2. **“能否被破坏”直接用`IsBreakable`**：不再靠读文字推断。不覆盖用户明确裁定；发现冲突时报告。
  3. **排查其他机制**：抓取同一镜像提交的`items.txt`（`knowledge/game-files/snapshots/2026-11-03-items/`），结果见[排查报告](../../knowledge/mechanics/reviews/game-files-audit-001/README.md)。
- 范围：排查只列疑点，没有改判断。候选如何处理待用户决定。
- 落地待办：词表下一版写入破坏规则、部分破坏条件。
- 来源：2026-11-03用户消息。
