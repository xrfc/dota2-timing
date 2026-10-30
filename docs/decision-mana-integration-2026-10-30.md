# R1：修复蓝量接入新版本评审包（2026-10-30）

对应总路线R1（COACH-01b+02）。本轮工程与浏览器验收已完成；**用户游戏评审尚待进行**，评审通过后R1才算关闭。

## 做了什么

- 新增`data.decision_mana.attach_current_mana`与`scripts/attach_decision_mana.py`：以8769原服务包`reports/decision-review-followup-2026-10-27-v1`为基础，绑定10/28修复产物`reports/decision-mana-repair-2026-10-28-v1`，生成新包`reports/decision-review-mana-2026-10-30-v2`。
- 只替换两例主宰状态卡的`mana`字段：9056008987为567/567（旧读数70.9），9056008877为543/543（旧读数67.9）。旧读数保存在`replaced_reading`；`decision_input`、事后采样、试标模板逐字节不变。
- 页面在目标英雄、决策时点显示蓝量数值和蓝色进度条，并注明“游戏单位未独立认证，不代表能施放”；对照卡的“蓝量取证”改为说明新旧读数。其他英雄、历史采样、非决策tick仍显示未知。

## 防泄漏与校验

- 新值只来自`current-resource.json`（仅决策tick）。capture与comparison只在同一tick做交叉核对：血量须与状态卡一致、蓝量须与capture一致、被替换的旧读数须等于审计过的旧值。未来样本被扰动不改变结果（有回归测试）。
- 基础包与修复产物共249个来源文件按哈希核验，生成前后各查一次；输出目录已存在、路径越界或来源漂移均拒绝。
- 修复值仍是同一录像源的重新解码，**不是独立游戏真值**；`can_cast`保持null，`training_allowed=false`。

## 验收

收据：`reports/decision-review-mana-acceptance-2026-10-30-v2/acceptance.json`。

- 真实浏览器（Windows Chrome 156，无头、临时配置）13项检查通过：初始不请求事后文件、两例蓝量值与进度条、其他8名英雄无蓝量值、历史采样隐藏/返回恢复、地图渲染、点击后才加载事后对照且不改动面板、无控制台错误。截图同目录。
- 全库`scripts/check.py --scope all`：Python 1347项、JS 23项、Ruff均通过，检查前后源码指纹一致。shell配置了代理，需设`NO_PROXY`，否则Host头403测试会被代理返回502。
- v1包/验收为改蓝条颜色前的开发产物，实现指纹已过时，保留不用。

## 启动（替代8769旧服务包）

```bash
PYTHONPATH=src .venv/bin/python scripts/decision_review.py --output reports/decision-review-mana-2026-10-30-v2 --serve --port 8770
```

打开`http://127.0.0.1:8770`。重新生成须换不存在的输出目录：

```bash
PYTHONPATH=src .venv/bin/python scripts/attach_decision_mana.py --base reports/decision-review-followup-2026-10-27-v1 --repair reports/decision-mana-repair-2026-10-28-v1 --output reports/decision-review-mana-NEW
```

## 仍未解决

敌方装备/CD（方案A有意不显示）、完整可施放条件、TP落点与到场时间、兵线/野区存量。按R1范围不补；是否需要由R2试标中的“信息不足”情况决定。

## 追加：全队状态（2026-10-30，用户选择方案A）

用户评审时指出其他英雄的蓝量/技能CD均为“未知”。原因是10/27状态探针与10/28蓝量修复都只抓案例主角。用户选定**方案A**：友方显示蓝量、技能/物品CD与TP；当时可见的敌方只显示蓝量，冷却不显示（敌方冷却在游戏内的可知程度未核实）；隐藏/无可靠位置的英雄一律不显示。

- `scripts/probe_team_state.py`：复用10/28修复计划冻结的解析器与两场本地录像（204个来源按哈希固定），以修正版本解析器离线抓10名英雄在**决策tick与前一秒**的状态；不读取任何未来时点，无联网采集。产物`reports/decision-team-state-2026-10-30-v1/`，每场20条（单场约35秒、190MB内存）。
- `data.decision_team_state.team_state`：以包内同刻可见行的血量绑定探针实体与英雄身份，不符即拒绝；敌方卡片的技能/物品/TP置空并标记`withheld_enemy_visibility_unverified`。`data.decision_state.entries`为从原状态卡抽出的共用冷却逻辑，行为不变。
- `scripts/attach_team_state.py`：在蓝量包基础上生成`reports/decision-review-team-2026-10-30-v2`，并要求探针中主宰蓝量与已修复值一致（两例均一致）。基础包逐字节不变。
- 页面：其他英雄按卡片显示；敌方即使数据混入冷却也不渲染（含原始读数展开区）。修正蓝量条CSS优先级问题（v1包中仍显示为绿色，已作废）。

结果（决策时点）：案例1友方4人+可见敌方4人（大圣隐藏），案例2友方4人+可见敌方4人（祈求者隐藏）。非主宰英雄的技能/物品名仍显示内部ID（如`pudge_dismember`），未做中文映射。

验收：`reports/decision-review-team-acceptance-2026-10-30-v3/acceptance.json`。真实浏览器15项通过（新增：全队蓝量与方案A一致、友方有冷却、敌方冷却不显示、蓝量条实际为蓝色）；全库Python 1359、JS 24、Ruff通过，源码指纹不变。team v1、acceptance v1/v2为开发中间产物。

当前页面（替代上文8770命令中的包）：

```bash
PYTHONPATH=src .venv/bin/python scripts/decision_review.py --output reports/decision-review-team-2026-10-30-v2 --serve --port 8770
```
