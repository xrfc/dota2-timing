# 全量补漏（U81、U82）

不靠关键词筛候选：逐个读734个技能和200件现役装备（不含配方），对照68个机制判断。只从字段读的机制不在其中。

- Codex：`gpt-6.1-sol`，`reasoning effort: high`，38批，约72万tokens，盲审，输入不含现有记录和Claude判断。结果在`results/`；`results-effort-none/`是默认强度的10批，只作对比。
- Claude：独立于Codex读完（`claude/adds.tsv`），但看得到现有记录，只记缺的。
- 对比：`compare.py` → `comparison.json`。Codex独有的行，Claude看过其引用后再判断：`triage.py` → `triage.json`。这一步不是盲审。
- 局限：只读文字，未运行游戏；两边读的是同一份说明，可能错在同一处。

汇总：两边都提出且原来没有159条；只有Claude 27条；只有Codex 376条，另有44条Codex不确定；与原有AI排除冲突5条；被用户裁定或字段挡住23条，不改；原有AI接受、这次Codex没提到56条，留给抽查。
