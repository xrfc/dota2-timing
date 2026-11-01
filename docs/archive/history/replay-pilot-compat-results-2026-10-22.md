# 原始录像兼容修复与轨迹、视野续报（2026-10-22）

本报告接续[首轮失败记录](replay-pilot-2026-10-22.md)，替代其中“当前可用轨迹0场”的状态结论；首轮证据保持不变。

## 实际交付

同一冻结清单的3场均完整解析、比赛ID及10人英雄身份与缓存API详情一致。已导出可追溯轨迹和英雄阵营可见性变化，未扩大采集、训练或修改共享环境。

| 比赛ID | 解析秒数 | 轨迹行数（10人合计） | 英雄视野事件 | 轨迹时间范围 | 清洗隔离记录数 |
|---|---:|---:|---:|---|---:|
| 9056009571 | 151.37 | 30,495 | 4,050 | 0–3048/3049秒 | 30 |
| 9056009136 | 117.77 | 24,760 | 3,905 | 1–2476秒 | 0 |
| 9056009130 | 92.64 | 19,393 | 3,287 | 0–1938/1939秒 | 18 |

三场每位玩家已保留轨迹的最大相邻时间间隔均为1秒。这个数不代表赛前、首秒、末秒和全部原始状态完全覆盖。隔离记录涉及同秒冲突，不能重新补成确定值。适配器还分别报告1780、1820、1780条时钟/坐标相关过滤警告（含经济通道），详见各场quality；原有适配器仅接收0到duration范围，原始输出保留被过滤的赛前数据。不能把这些警告计数等同于比赛中的轨迹缺口，也不能把全部警告未经逐条核验解释为赛前记录。

三场均通过既有真实隐藏坐标扰动检查及observer与features样本ID对齐检查。扰动检查每场选取一个有最后可见位置的观察截点，不是全部时刻、全部字段的无泄漏证明。

## 修复与证据链

- `scripts/build_replay_compat.py`复制已安装Gem 0.10.0到独立目录，回移植[上游fixed8修复](https://github.com/whanyu1212/gem-dota/tree/bae361de1d82e7a0a8457c788bf6f9d90e9c4d86)，并修正比赛ID的64位读取。
- 副本和原包逐文件哈希保存在`data/replay-pilot-2026-10-22/compat-v1/manifest.json`；这是修改后的兼容副本，不能仅以发行版号0.10.0声称精确原版复现。
- 已有捕获修复在提前解析出错时拒绝结果，不再接受不完整解析。
- 新解析目录：`data/replay-pilot-2026-10-22/compat-results-v1/`。`execution.json`绑定计划、兼容清单与捕获实现哈希；逐场receipt记录退出状态和耗时。
- `workspaces/<match_id>/prepared/<preparation_id>/`保留raw.json、cleaned.json、observer.jsonl、quality.json与manifest.json。
- `exports/<match_id>/trajectories.jsonl`保留比赛、英雄、玩家槽位、游戏时间、source_tick、source_ref及raw_sha256；`visibility.jsonl`单独保存英雄视野事件。
- `exports/<match_id>/audit.json`记录10人覆盖与导出哈希；`<match_id>.observer-verification.json`记录观察视角检查。

追溯时先通过audit找到preparation与raw哈希，再用source_ref定位原始行。全图真实轨迹不能当作玩家当时已知坐标；决策视角应读取observer中的可见、隐藏、未知与last_seen。

## 复用命令

已有产物无需再次下载或解析；导出到新目录，旧目录不可覆盖：

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_replay_tracks.py \
  --workspace data/replay-pilot-2026-10-22/compat-results-v1/workspaces/9056009136 \
  --metadata data/purchase-until-daily-2026-10-22-proxy-resume-01/matches/9056009136.json \
  --match-id 9056009136 --output data/replay-audit-new/9056009136
```

该命令调用`workflow/replay_audit.py`校验已有产物并导出；本轮未修改共享workflow接口。跨机器复现需要原始录像、冻结详情、兼容副本及其清单，不可用重新抓取代替同一份证据。

## 验证和未完成边界

本轮专项：`PYTHONPATH=src .venv/bin/python -m pytest tests/test_replay_compat.py tests/test_replay_ingestion.py tests/test_observer_context.py -q`，29项通过。首次调用遗漏PYTHONPATH导致收集失败，补上后通过；未安装依赖。未组织双方静止的全库验收，不能称全库验收通过。

当前可用于离线轨迹追溯和视野证据查看，不等于训练准入：

- 阵营可见性事件不是完整地图视野网格，也不是玩家摄像机或注意力。
- 坐标仍是解析器原生坐标；地图变换、传送/死亡/复活对应、实体生命周期、暂停边界仍需专项语义验证。
- 血魔单位（尤其魔法值）尚未验证；非空不能证明可用于技能可释放判断。
- 视野中的未知保留为未知，不转成不可见。隐藏坐标检查只覆盖既有检查定义的范围。
- 不自动扩到20–50场，不修改现有训练集、标签、划分，不推送。

下一阶段优先完成坐标/生命周期与视野语义核验，再决定是否扩大稳定性试跑。
