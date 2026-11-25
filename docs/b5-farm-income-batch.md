# B5 开发集分类实收：可恢复提取与对账

2026-11-25，接续 B5 第③步。用户要求长程开发、自行校验；[本次决定](decisions/2026-11-25-long-development.md)。当前任务是取得可复核的真实结果，后续模型试验另按既定研究契约执行。

## 范围与目标

固定已有开发机会全集：1,169 场 7.41f、15,005 个一号位兵线机会，来自原 1,341 场开发集。收线 6,235、朝野区移动 1,176、未知 7,594。输入来自 [PR #46 固定版本](https://github.com/xrfc/dota2-timing/blob/408e022/docs/b5-route-coverage.md)，本主题不依赖其代码导入。原 337 场已正式评分；本工具仍拒绝读取原留出比赛，三场已读录像只作回归。

沿用用户已定的目标：决策时刻起 30 秒为主窗，20 秒为对照；分别取游戏原始 creep、neutral 分类实收。此次发现 creep 字段也包含敌方召唤物收益，不能再简称为“仅自然兵线收入”；纯兵线目标属于另一项研究定义，本轮不静默扣除召唤物金币。实际动作来自原 t..t+6 走位标签，保留未知、零收入、死亡与缺端点的机会。不会按结果成功与否筛选转野，也不把收入当事前特征。营地位置不证明有野或可达；这些缺口仍未解决。

此前现金差包含购物、死亡损失等，不能代表刷钱收入；新目标与旧现金目标的误差不能直接相比。分类实收只说明已选择动作的结果，不揭示同一时刻另一个选择的反事实收益。[历史金币回归依据](https://github.com/xrfc/dota2-timing/blob/a392ff0e638441c6681e2ca4b88e391c39057f9b/docs/b5-farm-gold.md)

## 接口与校验

共享来源模块 `sources.gem_farm_income.capture_farm_income(raw_demo_path, cases)` 接受已解压录像及 `(hero, t)` 列表。当前 `gem-farm-income/2` 从 PlayerResource 的 selected hero、阵营/槽位确定归属，返回资源行号、0/20/30 秒端点、分类累计金币、逐笔 GOLD 事件及兼容层指纹；不读取路线标签或 data 模块。业务脚本 `collect_b5_farm_income.py` 属路线 B，负责固定机会、来源验证、窗口计算和批次管理。

- 每秒首个 tick 开始、实体更新前采样；保留录像 tick 与引擎 net_tick，二者不能混用。解析结束后用最终游戏时钟重查端点秒数。
- 端点差为 `C(t+n)-C(t)`；日志按整数游戏秒 `[t,t+n)` 汇总，包含起点、排除终点。两路差额原样保留，不强制调平。
- `complete` 仅表示结果窗与端点完整，不表示日志对平；`event=0` 仅表示该通道合计为零，不能覆盖非零累计实收。原始 combat 秒可能与登记的 replay 时钟差一秒，必须沿用同一时钟对齐，不能为消除差额任意切换。
- 缺端点、缺计数和比赛结束截断分别标记，未知金额为 null；完整观察且没有收入才记零。日志为空但观测累计金币为正时拒绝产物。
- 必须完整解析、比赛 ID 一致、十人英雄与阵营槽位一一对应、累计金币不倒退。selected handle 的实体 index/serial 和阵营必须一致，真实身份冲突仍拒绝；缺失选择或未解析实体保留 null，不回退到 controller 缓存。末次观察秒仅表明流覆盖，实际比赛时长来自固定元数据。
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
  --out reports/b5-farm-income-20261125/batch-roster-v2-final --workers 4

PYTHONPATH=src .venv/bin/python scripts/collect_b5_farm_income.py report \
  --plan reports/b5-farm-income-20261125/plan.json \
  --out reports/b5-farm-income-20261125/batch-roster-v2-final
```

`plan` 不覆盖已有文件。`run --limit 4` 检查计划前四场；`--match` 只能指定计划内比赛。去掉 limit 再执行相同 run 即续跑：已完成项仍核验原录像和产物身份。report 区分已计划与已完成数，未完成不得当成零收入。进程异常终止留下锁时，先核查进程状态，不能自动删除别人的锁。

## 同期几何诊断

另行只读重放原未知标签的 4,198 个去重目标、1,095 场，冻结输入和状态哈希全部一致。1,342 段仅失败于固定前沿增距的片段中，同 lane 移动前沿完整 1,334 段，580 段满足原三个几何条件；13 段存在前沿大跳需审查，其余 567 段是可供后续讨论的例子。不能据此自动改标签。

2,901 段仅失败于营地终点距离者，205 段在 t+7..20 且中断前进入原诊断所选营地半径；完整观察 2,052 段，另有跳位 706、非存活 143。所选营地只是“失败条件最少”的示例，不一定是玩家目的地，因此该比例不是转野标签精确率。后续轨迹仅作诊断，不能进入事前特征。证据在本机 `reports/b5-geometry-followup-20261125/REPORT.md`。

## 验收与下一项

首轮专项共 56 项通过，覆盖端点时钟、零与未知、身份/兼容层拒绝、固定人口、来源及产物漂移。发布前增加原录像二次哈希，防止解包/解析期间来源被替换；旧 batch-v1、batch-v2 保留，以下首轮结果只对当时的实现和样本成立。

真实验收：按计划顺序前 16 场，188 个机会（收线 74、转野 13、未知 101）；30 秒完整 186、结束截断 2，20 秒完整 187、结束截断 1。可观察的 **746 项分类金额全部对平**，截断金额保留 null。首四场在新实现中重新解析，capture 与结果逐项相同；再次执行前 16 场全部复用，并重新验证原始字节和兼容层。证据为本机 `reports/b5-farm-income-20261125/real-validation.json`、`smoke-v2-summary.json` 和 `resume-v2.log`。

首轮全量检查为 2,042 pytest 加学习、知识、前端及 Ruff；记录在 `check-final.log`，前后 8,928 个文件指纹一致，包含未跟踪源码。不能用这 16 场宣称全体开发集或独立验收通过。

### 扩大运行后发现的问题

旧批次完成 53 场、682 个机会后，另一场因身份冲突停止。2,728 个分类金额格中，2,683 对平、32 因结束截断为空、13 非零。已逐 tick 核完全部 13 个差额格（6 场、7 个机会）：11 格与中立巨魔骷髅死亡时的累计增量相伴，另 2 格来自击杀术士小恶魔的 creep +3。同秒有多次击杀时只保留聚合残差，不反推每只赏金。原端点、原事件、源字节和 7,988 个邻域 tick-start 时钟均重放一致；未改值或豁免。

这些证据支持“当前 GOLD 通道未覆盖某些小额收入”，不能证明引擎有统一的 `<5` 金过滤规则。Gem 的直接及 bulk 解码合成输入 0..5 金均原样保留；[公开控制台变量转储](https://github.com/SteamTracking/GameTracking-Dota2/blob/85c705fa134abf135abdaba6718805546e511b03/DumpSource2/convars.txt)未找到金额阈值明文，[OpenDota GOLD 处理](https://github.com/odota/parser/blob/51c934fba40858a6061b4b60bc4b79972d420d8a/src/main/java/opendota/Parse.java#L443)原样复制 value。详见本机 `reports/b5-farm-income-discrepancy-20261125/remaining/REPORT.md` 与覆盖表；其余比赛的差额仍需各自核查。

身份故障为比赛 9081458883：控制器重建后，Gem 缓存的两个玩家指向同一巫医实体，而 PlayerResource 中风暴之灵的选定英雄始终正确。新来源改用 PlayerResource 并校验 handle/serial，错误信息同时带比赛 ID；不是放宽校验。修复版已重提前 54 场、692 个机会，原先成功的 53 场所有端点、事件和窗口结果逐项不变，故障场也通过；收据为 `roster-regression-validation.json`。随后补齐协议中的负槽位“未分配”哨兵处理：与 None 一样保留缺失端点，真实重复槽位或身份冲突仍拒绝；最终实现专项含 45 个来源测试与 24 个批处理测试。

该场旧 state-v3 在 t492–664 的 173 秒也存在英雄属性与玩家经济混合行；t665 恢复。该场 10 个机会在 t945–1861，其邻域未见这个重复问题，不能把这些机会或整批一概判为污染。随后核完 1,169 场、15,005 个机会的 t..t+6，共 105,035 次帧观测：任意英雄跨 pid 重复、本人非唯一、本人位置/队伍歧义、缺帧/本人/位置均为 0，全部状态哈希匹配。已知坏帧正对照能检出 WD 重复和 Storm 缺失。阴性仅覆盖这些窗口和已知症状，不证明整场状态、历史特征或所有身份问题都正确。295 个机会含非存活帧，单独记录，未据此改标。现有状态和标签保持冻结，影响报告在本机 `reports/b5-farm-income-identity-20261125/{state-impact,population-screen}/`。

修复后的原始金币在新目录 `batch-roster-v2-final` 重提，旧输出不迁移或覆盖。长批次使用确切提交导出的源码副本（保存在 reports，非新增 Git worktree），逐文件摘要与运行 manifest 保持一致，避免共享工作区切分支改变在跑的生产者。完整运行及差额汇总继续按真实完成数记录；有差额时保留待审状态，不自动宣告对账成功。

最终实现的五场小跑、复用、全量检查与文件指纹分别记录在 `final-smoke.log`、`final-resume.log`、`check-roster-final.log`、`check-roster-{before,after}.txt`。长批次结束后自动生成 `full-run-2/status.json` 和 `summary.json`，区分是否完整提取、未知端点及金额差额。当前不把部分已完成结果当成全量完成。

第③步后续是完成全体同窗金币对账，核验事前营地条件的可观测性，归类异常。第④步才登记并验证一个改法，使用同一目标的简单基线和按整场折外比较。动作定义变更、跨场景收益权重及新独立验收来源仍需用户决定。
