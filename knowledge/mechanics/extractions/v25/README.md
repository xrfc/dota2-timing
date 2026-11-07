# 复核后事实 v25（U120、U121）

新增机制“加速”（`haste`，词表v14）：提升自身、自己的单位或友方移动速度的效果，顺带加一点移速的也算，只让敌人变慢的不算。

- 116行加速，来自`reviews/haste-001`：249个候选由Codex（`gpt-6.1-sol`，high）独立判断，Claude看过依据；依据记`two_ai`（不是两边盲审，同U81做法）。12个不确定的没有记。
- 条件：基础、需A杖、需魔晶或装备；装备25件。
- “可被弱驱散的保命效果”只算用户确认的16个“主要作用是跑”的加速技能和风行者·风行的闪避（特性映射v6，`data.mechanics_traits_v4`的`only_subjects`）。嗜血术这类顺带加速的只记加速，不算保命。

行数3179→3295，接受2482→2598。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v25.py --output <新目录>
```
