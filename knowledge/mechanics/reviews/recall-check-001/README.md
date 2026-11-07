# 漏记检查（MK-T5，2026-11-04）

`recall.json`由`scripts/check_mechanics_recall.py`生成，拿v10和两份外部清单对照。两份都不是标准答案：v1手工标注可能偏宽（如风行者·风行），关键词也会误报。这里列的是候选，不是已证实的漏记。

| v1特性 | 有记录 | 已被排除 | 没有记录 |
|---|---|---|---|
| 高机动 | 12 | 2 | 22 |
| 控制 | 24 | 0 | 16 |
| 幻象/召唤物 | 17 | 3 | 6 |
| 闪避/致盲 | 11 | 2 | 4 |
| 治疗/吸血 | 27 | 1 | 4 |

关键词对照：`stun`命中75个技能、全部有记录；`silence`15个、全部有记录。官方说明里写了这个词的技能基本没漏，漏记集中在说明不用关键词的技能。

已读官方说明核实的例子：莱恩·妖术（“Transforms an enemy unit into a harmless beast”）、风暴之灵·球状闪电（“charging across the battlefield”）、虚空假面·时间漫游（“Rushes to a target location”）、自然先知·自然的呼唤（“Converts an area of trees into Treants”）。

原因：v3起的候选靠关键词和字段筛出来，复核只判断候选，看不到没被筛出的组合。
