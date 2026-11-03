# Codex第5轮：v4中只有Claude审过的组（U56）

范围：`extractions/v4/facts-v4.json`中`basis=claude_only`的702组。`codex exec --sandbox read-only`盲审，24批，约70万tokens。

## 结果

同标签674组（都接受671、都排除3）。分歧28组：Claude接受、Codex排除24组、不确定4组。分歧写入[待用户裁定汇总](../../../../docs/handoff/user-rulings-2026-11-02.md)K块。

同标签组不是用户确认，也没有比较生效条件。两个AI可能共用同一种错误，第3轮后的37组先天就是例子。结果尚未写入v4。

## 方法与局限

- 输入不含Claude判断；运行目录为空，要求不读其他文件。只读沙箱挡不住读盘，这一点靠指令约束。
- 已过滤过时升级文字；装备带完整说明和属性；定义来自词表v4，措辞由助手整理。
- 未运行游戏，也没有联网。

## 文件

`build_packet.py`生成`batches/`；`prompt.md`、`schema.json`、`run_batch.sh`是调用方式；`results/`是原始回复；`codex-review.jsonl`是汇总。
