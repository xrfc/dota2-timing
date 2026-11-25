# B5 开发集分类实收：可恢复提取与对账

2026-11-25，接续 B5 第③步。用户要求长程开发、自行校验；[本次决定](decisions/2026-11-25-long-development.md)。当前任务是取得可复核的真实结果，后续模型试验另按既定研究契约执行。

## 范围与目标

固定已有开发机会全集：1,169 场 7.41f、15,005 个一号位兵线机会，来自原 1,341 场开发集。收线 6,235、朝野区移动 1,176、未知 7,594。输入来自 [PR #46 固定版本](https://github.com/xrfc/dota2-timing/blob/408e022/docs/b5-route-coverage.md)，本主题不依赖其代码导入。原 337 场已正式评分；本工具仍拒绝读取原留出比赛，三场已读录像只作回归。

沿用用户已定的目标：决策时刻起 30 秒为主窗，20 秒为对照；分别取小兵、野怪的实际收入。实际动作来自原 t..t+6 走位标签，保留未知、零收入、死亡与缺端点的机会。不会按结果成功与否筛选转野，也不把收入当事前特征。营地位置不证明有野或可达；这些缺口仍未解决。

此前现金差包含购物、死亡损失等，不能代表刷钱收入；新目标与旧现金目标的误差不能直接相比。分类实收只说明已选择动作的结果，不揭示同一时刻另一个选择的反事实收益。[历史金币回归依据](https://github.com/xrfc/dota2-timing/blob/a392ff0e638441c6681e2ca4b88e391c39057f9b/docs/b5-farm-gold.md)

## 接口与校验

共享来源模块 `sources.gem_farm_income.capture_farm_income(raw_demo_path, cases)` 接受已解压录像及 `(hero, t)` 列表，返回十名英雄的阵营/槽位、0/20/30 秒端点、分类累计金币、逐笔 GOLD 事件及兼容层指纹；不读取路线标签或 data 模块。业务脚本 `collect_b5_farm_income.py` 属路线 B，负责固定机会、来源验证、窗口计算和批次管理。

- 每秒首个 tick 开始、实体更新前采样；保留录像 tick 与引擎 net_tick，二者不能混用。解析结束后用最终游戏时钟重查端点秒数。
- 端点差为 `C(t+n)-C(t)`；日志按整数游戏秒 `[t,t+n)` 汇总，包含起点、排除终点。两路差额原样保留，不强制调平。
- 缺端点、缺计数和比赛结束截断分别标记，未知金额为 null；完整观察且没有收入才记零。日志为空但观测累计金币为正时拒绝产物。
- 必须完整解析、比赛 ID 一致、十人英雄与阵营槽位一一对应、累计金币不倒退。末次观察秒仅表明流覆盖，实际比赛时长来自固定元数据。
- 计划固定输入 SHA-256、机会身份/动作/五折摘要；执行时重新验证元数据、收据和原始 demo 字节。任意增加比赛或改标签会被拒绝。
- 输出绑定计划和生产者代码；每场开始及发布前检查源码和 Gem 兼容目录。只接受登记的兼容层；升级 Gem 不得混入本批次。
- 逐比赛原子发布并校验载荷摘要；同一输出目录只允许一个协调进程。最多四个子进程各写不同比赛；失败停止排入后续比赛，已完成产物可复用。不同输入或实现须使用新目录，不覆盖旧结果。

固定输入：

| 输入 | SHA-256 |
|---|---|
| `reports/outcome-labels/rows.jsonl` | `f2f1254c33158b6923fa7185dd1454414fc8483baaa7c8f69d5cf88d6eb395ca` |
| `reports/b5-route-coverage-20261125/rows.json` | `fcc370fdcedaa19440d5a72bdd90a6743883710495894232ffaacb746415bda2` |
| Gem compat-v1 manifest | `3f6e9ee2c222869adce45c6dfef757e719c9576bfdde82927e76d6868c47403d` |

## 命令

在仓库根目录复用 `.venv`。本机 `data/`、`reports/` 和兼容层不随 Git 分发；不能用任意新数据替代这些固定输入。

```bash
PYTHONPATH=src .venv/bin/python scripts/collect_b5_farm_income.py plan \
  --out reports/b5-farm-income-20261125/plan.json

PYTHONPATH=data/replay-pilot-2026-10-22/compat-v1:src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/collect_b5_farm_income.py run \
  --plan reports/b5-farm-income-20261125/plan.json \
  --out reports/b5-farm-income-20261125/batch-v2 --workers 4

PYTHONPATH=src .venv/bin/python scripts/collect_b5_farm_income.py report \
  --plan reports/b5-farm-income-20261125/plan.json \
  --out reports/b5-farm-income-20261125/batch-v2
```

`plan` 不覆盖已有文件。`run --limit 4` 检查计划前四场；`--match` 只能指定计划内比赛。去掉 limit 再执行相同 run 即续跑：已完成项仍核验原录像和产物身份。report 区分已计划与已完成数，未完成不得当成零收入。进程异常终止留下锁时，先核查进程状态，不能自动删除别人的锁。

## 同期几何诊断

另行只读重放原未知标签的 4,198 个去重目标、1,095 场，冻结输入和状态哈希全部一致。1,342 段仅失败于固定前沿增距的片段中，同 lane 移动前沿完整 1,334 段，580 段满足原三个几何条件；13 段存在前沿大跳需审查，其余 567 段是可供后续讨论的例子。不能据此自动改标签。

2,901 段仅失败于营地终点距离者，205 段在 t+7..20 且中断前进入原诊断所选营地半径；完整观察 2,052 段，另有跳位 706、非存活 143。所选营地只是“失败条件最少”的示例，不一定是玩家目的地，因此该比例不是转野标签精确率。后续轨迹仅作诊断，不能进入事前特征。证据在本机 `reports/b5-geometry-followup-20261125/REPORT.md`。

## 验收与下一项

专项共 56 项通过，覆盖端点时钟、零与未知、身份/兼容层拒绝、固定人口、来源及产物漂移。发布前增加原录像二次哈希，防止解包/解析期间来源被替换；旧 batch-v1 保留，新实现使用 batch-v2。

真实验收：按计划顺序前 16 场，188 个机会（收线 74、转野 13、未知 101）；30 秒完整 186、结束截断 2，20 秒完整 187、结束截断 1。可观察的 **746 项分类金额全部对平**，截断金额保留 null。首四场在新实现中重新解析，capture 与结果逐项相同；再次执行前 16 场全部复用，并重新验证原始字节和兼容层。证据为本机 `reports/b5-farm-income-20261125/real-validation.json`、`smoke-v2-summary.json` 和 `resume-v2.log`。

最终全量检查记录在 `check-final.log`，前后文件清单摘要在 `check-final-before.txt` 与 `check-final-after.txt`，包含未跟踪源码。全体 1,169 场尚未在此验收快照中完成；去掉 limit 的运行及自动对账将沿用同一 batch-v2。实际完成数以 report 为准，不能用这 16 场宣称全量或独立验收通过。

第③步后续是完成全体同窗金币对账，核验事前营地条件的可观测性，归类异常。第④步才登记并验证一个改法，使用同一目标的简单基线和按整场折外比较。动作定义变更、跨场景收益权重及新独立验收来源仍需用户决定。
