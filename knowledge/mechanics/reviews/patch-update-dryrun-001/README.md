# 补丁更新流程试跑（MK-T6e，2026-11-06）

演示`scripts/patch_update.py`，没有据此改知识库。流程见`docs/mechanics-patch-update.md`。

- `status.json`：官方最新补丁仍是7.41f，`update_needed=false`。
- `game-diff-self.json`：同一快照自比，没有变化（检查脚本本身）。
- `impact-2026-10-09-to-11-01.json`：用10-09到11-01的英雄差异（7处中文文字修订，U36已看过）算影响范围：7个对象、29行事实、12条规则、20条装备关联；“齐天大圣”的英雄字段变化不对应任何事实行。
