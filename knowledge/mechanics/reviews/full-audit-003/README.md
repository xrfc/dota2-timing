# 第1–8轮旧记录复查（U85）

第1–8轮Codex很可能是默认强度。这一轮把v11里来自这些轮次的`two_ai`行（`origin`为`v3_review`、`audit_round4`）重新判断，也比对生效条件。

- Codex：`gpt-6.1-sol`，`reasoning effort: high`，临时账号（32批日志都记录`account=temp`），32批，约87万tokens。盲审：输入不含原结论、审查者和引用，告诉它条目有对有错，不告诉比例。
- 范围：777个对象，打包1898行，去掉只差`item_ability_type`的重复后1879行，全部有结果。这18组重复行结论都相同。
- 未送审：`unit_target_spell`、`channeled`共207行，改为和游戏字段比对，7行不一致，看过都不用改。
- 结果：`compare.py` → `comparison.json`；同结论且条件也对的1817行，不同62行。`triage.py` → `triage.json`分四组：

| 组 | 行数 | 处理 |
|---|---|---|
| `other_condition`：原来排除这个条件，Codex说成立但属于另一条件，那一行已存在 | 18 | 不冲突，不改 |
| `redundant_upgrade`：基础已有同一机制，Codex认为升级行条件不对 | 10 | 用户裁定 |
| `keep`：材料之外有字段或用户裁定支持原结论，或Codex只是不确定 | 13 | Claude看过，不改 |
| `ask` | 21 | 用户裁定 |

处理结果：用户裁定写入v12，见[U86–U87](../../../../docs/decisions/2026-11-04-recheck-rulings.md)。

局限：只读文字，未运行游戏；盲审材料没有字段数值，部分不一致由此造成；`keep`和`ask`的分组是Claude看过结果后定的，不是盲审；结论相同不代表一定对，两个AI可能错在同一处；没有单独测量强度的影响，因为第1–8轮的输入和词表都和这次不同。
