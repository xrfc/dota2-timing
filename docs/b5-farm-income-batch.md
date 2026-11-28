# B5 开发集分类实收：可恢复提取与对账

2026-11-25，接续 B5 第③步。用户要求长程开发、自行校验；[本次决定](decisions/2026-11-25-long-development.md)。当前任务是取得可复核的真实结果，后续模型试验另按既定研究契约执行。

2026-11-26 结案：固定全集提取及 297 个差额格的金额核验已完成，独立 closure 通过；原值保留，一个付款 tick 的分配机制仍未确认。以下保留分阶段证据，最终状态以文末“全量金额核验结论”为准。下一项为营地事前可见证据，不启动训练。

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

### 2026-11-26：恢复运行与独立审计

用户要求继续开发。原 `full-run-2` 日志最后更新于北京时间 11 月 26 日 00:53，管理会话已不存在，宿主进程检查也没有该提取器；状态文件仍写着 running，不能据此宣称进程活着。确认后将旧锁移存到 `recovery-20261126/`，保留原日志和状态，用同一 b354e19 源码副本恢复到 `full-run-3`。已完成比赛仍验证录像字节和产物，未换生产者或覆盖旧结果。具体中断原因尚不能确认。

续跑前固定快照的审计结果为 623 场、7,903 个机会。31,612 个金额格中，31,143 对平、304 因比赛结束截断为 null、165 非零；无 missing_endpoint/missing_counter。差额涉及 91 场、105 个机会，均为正数，creep 为 3/6/9/12，neutral 为 2–12；这些只是分布，不能由金额相似自动归因为同一种日志缺失。旧 13 格精确延续，新增 152 格仍须核查。全部窗口由冻结 capture 重算一致，审计前后输入哈希一致；证据在本机 `reports/b5-farm-income-audit-20261126/`。

本轮再定向重放三场、四个机会、七个差额格：幽鬼 creep +12 与主宰 +6 分别对应四次、两次术士小恶魔死亡同期的 +3；敌法师 neutral +12、水人 +10 集中在巨魔骷髅死亡的 tick。后两者保留同 tick 聚合残差，不按怪数分摊赏金。4,565 个 tick-start 时钟一致，原始端点、事件、窗口及来源全部重放一致；记录在 `reports/b5-farm-income-discrepancy-20261126/{REPORT.md,validation.json}`。这是按较大差额和 event=0 选取的诊断，不是随机验收。623 场快照现有 20 格具备逐 tick 证据、145 格仍待查，续跑新增差额另算。

独立只读入口 `scripts/audit_b5_farm_income.py` 固定审计开始时已发布的比赛文件列表，校验计划、冻结生产者、产物载荷和窗口重算，输出覆盖及逐格差额。提取中后来发布的文件留待下一份快照；审计不改原输出、不接管写锁，不导入 `--producer` 指向的代码。当前批次的原生产者文件保持不变。

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_b5_farm_income.py \
  --plan reports/b5-farm-income-20261125/plan.json \
  --batch reports/b5-farm-income-20261125/batch-roster-v2-final \
  --producer reports/b5-farm-income-20261125/producer-roster-v2-final \
  --out reports/b5-farm-income-audit-20261126-verified
```

每次审计使用新的输出目录。这个检查证明保存值与冻结输入的一致性，不等于原始游戏语义已全部解释；逐 tick 证据与尚待核查的差额应另行登记。全量提取结束时还须重新生成完整快照，不能沿用部分完成数。

审计专项 29 项通过，覆盖未完成、零与缺失、负差、重算后的丢行/重复/改值、输入删除与漂移、生产者失配、同批新发布文件和输出覆盖拒绝。真实最终审计记录在 `reports/b5-farm-income-audit-20261126-final/`：652 场、8,268 机会全部重算一致，33,072 金额格中 32,581 对平、320 截断为空、171 非零；无负差、缺端点或缺计数。这里的 final 指本轮审计实现验收，不是全体提取结束。串行全量检查与前后含未跟踪源码的文件指纹记录在 `reports/b5-farm-income-20261125/check-audit-20261126.log` 和 `check-audit-20261126-{before,after}.txt`。冻结提取器的八个绑定文件未修改。

### 下一项的可行性：事前可见中立单位

只读源码核查表明，compat-v1 已能从 `CDOTADataRadiant/Dire.m_bNPCVisibleState` 按实体 index 读取双方实际可见性；缺 word 为 unknown，不能用 `m_nFoWTeam` 替代。当前 state-v3 排除了 `CDOTA_BaseNPC_Creep_Neutral`，已有可见事件又缺位置与生命，所以仍需新来源采样。拟在决策秒首个 tick-start 同时读取位置、生命、实体 index/serial 和可见位图，与金币端点保持同一边界；包末可见事件可能含同 tick 后续更新，不能直接拼到包前状态。

这只是后续实现建议，尚未真实补提或构造训练特征。首版仅投影己方当时可见单位，保留字段缺失；隐藏单位出生位置、未来死亡不能用来推断事前营地归属。可见单位为零不能证明空营，最近静态营地也不证明实际归属、可达或清营耗时。具体字段覆盖、被控制/召唤单位和生命周期仍须在既有开发录像小跑核验。

### 本轮完成条件（2026-11-26 用户明确顺序）

先完成剩余提取与对账，再实现上述营地证据。完整提取要求 1,169 场、15,005 个机会全部发布，最终独立审计的 pending 为零；未知动作、零收入和死亡窗口继续留在固定人口中。每个 null 必须能对应比赛结束截断或单独处理的缺失原因。每个最终非零金额格按比赛、英雄、决策时刻、窗长和分类关联到重放证据，端点、事件、累计变化和来源摘要必须匹配；未解释项为零后才能关闭此项。数值差额原样保留，对账完成不等于两个通道数值相等。

完整提取于北京时间 2026-11-26 12:00:54 结束。`full-run-3/status.json` 的 run_exit/report_exit 均为 0，1,169 场、15,005 机会齐全；297 个差额格使监督器保留 `extraction_complete_needs_quality_review` 状态并返回 1，这表示需要完成对账，不表示提取失败或应重提。最终机会动作仍为收线 6,235、朝野区移动 1,176、未知 7,594。30 秒完整 14,816/截断 189，20 秒完整 14,896/截断 109；完整窗口的 creep 差额分别 33/24 格、neutral 分别 162/78 格。

本轮独立全量审计在 `reports/b5-farm-income-completion-20261126/snapshot-final/`：60,020 金额格中 59,127 对平、596 截断为空、297 非零，涉及 167 场、195 机会；没有负差、缺端点或缺计数。`analysis-final/` 独立确认全部未知动作、506 个原 death=1、335 个 early_death=1、295 个标签窗含非存活帧的机会仍在；4,353 个原 death=null 保持未知，不当成没死亡。完整双分类零收入为 20 秒 1,817 窗、30 秒 1,163 窗。唯一 t==duration 的机会也保留；没有 t>duration。

异常核验的边界：金额解释指固定原值能够按身份、端点、逐 tick 累计与日志重放，且差额有具体证据；不要求证明全部引擎奖励公式。两处英雄所属巨魔骷髅的 creep 差额已通过 UnitNames、生命转换、阵营、控制掩码、owner handle/index/serial 和 PlayerResource 证实；其中多只同时死亡者保留聚合残差。另一处敌法师是非击杀者，neutral 与非可靠金钱各 +4，原始 GOLD 无该玩家记录；另有被动收入 +1，所以相邻样本的总实收 +5 可完全分解。附近 +5 的完整日志作为正对照。这笔金额可核清，但为何分配给敌法师仍未确认，不把“此前堆过野”写成已证实的堆野奖励。

这些证据分别在 `reports/b5-farm-income-control-audit-20261126/` 和 `reports/b5-farm-income-stack-audit-20261126/`。neutral 的增量由更新回调定位，钱包在包围它的相邻 tick-start 样本间核对，不冒称两个同 tick 钱包样本。原始 GOLD type8 与规范化事件逐笔相等；错误选择原始类型的早期诊断不用于结论，旧输出保留。全量独立核验还处理同 tick 多次回调，首个样本必须为更新前，后续只能按原顺序推进增量前缀，不能改冻结端点。

### 全量金额核验结论

`reports/b5-farm-income-reconciliation-20261126/final-summary/` 覆盖全部 297 个非零金额格，195 个机会、167 场；按比赛/英雄/tick/分类去重后有 270 个残差 tick。238 格关联普通中立巨魔骷髅死亡，53 格关联术士小恶魔死亡，4 格由英雄所属骷髅的实体证据确认，2 格由非击杀者实际到账与 GOLD 缺项证据确认。这里的关联不推导逐只赏金或统一日志金额阈值。

独立出口 `reports/b5-farm-income-completion-20261126/closure-final/report.json` 为 `accounting_closed=true`、`ready_for_camp_evidence=true`、`blockers=[]`。它从原始记录重建完整人口及所有非零键，逐条重算195个机会，核对167场原始录像前后SHA和3个额外证据tick，并复核截断、未知/死亡/零留存；没有依赖汇总的布尔标记放行。249组同tick额外回调按有序增量前缀验证，重复tick自身没有残差。全部原金额和差额保留。

`allocation_mechanism_unconfirmed=true` 仅指敌法师这一付款 tick 的具体分配机制未确认；实际到账和缺日志已核实，不与金额未决混淆。确切重放、汇总及独立验证脚本按SHA留存，入口见上述目录的 `provenance.json` 和 `REPORT.md`。本轮串行全量检查记录为 `reports/b5-farm-income-20261125/check-completion-20261126.log`，前后包含未跟踪源码的文件指纹为 `check-completion-20261126-{before,after}.txt`。
