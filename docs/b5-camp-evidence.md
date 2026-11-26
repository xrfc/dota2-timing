# B5：营地事前可见证据

2026-11-26，接续已完成的[分类实收提取与对账 PR #47](https://github.com/xrfc/dota2-timing/pull/47)。[用户要求及边界](decisions/2026-11-26-camp-evidence.md)。本主题已完成固定 1,169 场、15,005 个机会的事前可见单位提取、完整覆盖报告及独立验收，[PR #49](https://github.com/xrfc/dota2-timing/pull/49) 未合并。营地完整存量、归属、路线可达与清营条件仍未解决，也尚未接入旧复盘页。

## 固定范围

继续使用原 1,341 场开发集中的 1,169 场 7.41f、15,005 个兵线机会。动作仍为收线 6,235、朝野区移动 1,176、未知 7,594；原 t..t+6 标签不变，不按后续死亡或收益剔除机会。原 337 场已正式评分，不能作为新的独立验收；此批不读取它们。

输入是 `reports/b5-farm-income-20261125/plan.json`，SHA256 `8ad71d1e60b251360b9e96a4afc0c4a599443ddaa1c88abdb012b060cba7f3ad`；按 match/hero/t/fold/action 投影的人口摘要为 `4909b7905e5d5568831f96ca5cff385302fd28cd9a9228fde2c31c9746a80d42`。它是前一主题保存的不可变输入，本实现不导入尚未合并的金币脚本或模块。

## 来源与公开证据的边界

| 层 | 职责 | 不能据此声称 |
|---|---|---|
| `sources.gem_camp_evidence` | 在请求秒首个 tick-start、实体更新前冻结 active 中立类单位及双方可见性，保存原始审计证据 | 全知来源中的隐藏单位是玩家已知信息 |
| `data.camp_evidence` | 根据 PlayerResource 确认的观察阵营，白名单投影明确 visible 的单位事实 | 可见单位为零就代表空营，active 就代表存活 |
| `scripts/collect_b5_camp_evidence.py` | 固定计划、来源指纹、逐场原子发布、严格恢复与覆盖报告 | 已具备路线可达、完整营地存量或清营耗时标签 |

采样固定请求秒的首个回调，重复 tick 或同秒后续回调不能覆盖。t 沿用 Gem `game_time_s` 的整秒标签，表示该标签首次出现时、当前实体更新前的状态，不代表物理精确 t.000 或整秒连续观察；不事后平移时刻。首回调没有观察者身份就保留缺失，不能等后续身份出现再补回当前帧。完整解析后核对时间基准、比赛身份和来源版本，拒绝时钟漂移。

`observed` 仅表示该回调取得实体管理器及观察英雄的 PlayerResource 身份，不保证有可见单位、视野字段完整或营地库存完整。公开字段覆盖率的分母仅为实际公开的可见单位行，不能推广到隐藏或未解析单位。

具体 NPC 名来自 `m_iUnitNameStringTableIndex` 对应的 **UnitNames**。EntityNames 可能只给通用 `npc_dota_creep_neutral`，两种名字分别保存，不能混查同一个索引。观察英雄归属来自 PlayerResource 的选定英雄 handle（index/serial）、阵营和槽位，不能依赖可能被重建的控制器缓存。

实际视野读取 `CDOTADataRadiant/Dire.m_bNPCVisibleState`，每个 word 对应 64 个实体 index；缺 word 是 unknown，不是 hidden，更不是空营。旧包末视野事件可能包含当前 tick 后续更新，因此不能直接拼接到更新前状态。`m_nFoWTeam` 不能替代实际可见位图。

首版范围是 active `CDOTA_BaseNPC_Creep_Neutral` 类，保留血量、最大血量、生命状态、位置、阵营和 index/serial；缺字段为 null 并注明原因。真实普通野怪和巨魔骷髅均可属于该类，被玩家控制也不据此删除。陈的其他单位类不在本版覆盖内。owner handle、控制掩码、出生/生成器等信息即使可从全知来源读出，也不能自动升级为当时已知事实。

x/y 保留与状态 v3 相同的原生无符号 cell 坐标：`cell * 128 + offset`，地图中心偏移为 16,384；本层不减偏移、不贴图、不匹配营地。接入现有 `map_api` 时应使用其坐标转换，避免重复减去偏移。

公开层只包含己方明确可见的单位，不暴露隐藏/unknown 单位的数量、属性、位置或原始控制字段，也不附加未来死亡与动作标签。`stock_complete=false`、`empty_confirmed=null`、`camp_id=null` 保留限制；不按最近静态营地强行认定归属。审计原文和校验收据独立保存，不能直接作为模型输入。

## 自校验与后续出口

### 全集公开证据覆盖（2026-11-26）

固定 1,169 场、15,005 帧已全部发布，公开质量报告 `reports/b5-camp-evidence-quality-20261126/final/coverage.json` 的 `complete_population=true`；pending、missing_frame、missing_observer 均为 0，所有帧为 observed。累计 179,149 次可见单位观察，七个公开允许字段各有 179,149 个有效值、缺失均为 0；2,439 帧零可见。这些是可重复出现的单位观察次数，不是独立野怪数或营地库存。生产报告和全集独立核验得到相同计数。

| 原动作（仅用于覆盖分组） | 保留帧数 | 零可见帧数 |
|---|---:|---:|
| 继续收线 | 6,235 | 974 |
| 朝野区移动 | 1,176 | 156 |
| 未知 | 7,594 | 1,309 |

原 fold 0–4 的帧数为 3,120、3,047、3,089、2,765、2,984；观察阵营 2/3 为 7,525/7,480 帧。机会、动作和 fold 与固定计划逐条一致。唯一 t==duration（9090837174、Faceless Void、t2599、fold4、继续收线）仍保留，observed 且零可见；没有 t>duration 的机会。

公开质量报告的 2,340 个输入与三份审计源码前后摘要一致，精确源码和逐帧 CSV 同目录归档；`coverage.json` SHA256 为 `ec57c895b32fd9b866ce83bd358fca5dafc8e8a6ab176bbe189de983819badb6`。本报告只读公开 evidence/receipt，验证覆盖、字段与绑定，不能替代原始录像及 raw→public 的独立核验。

全集独立核验在 `reports/b5-camp-evidence-review-20261126/full-final-1/`：`report.json` 的 passed 与 complete_population 均为 true，1,169 场、15,005 帧全部匹配，pending 为 0；原始输入、逐场产物、11 个绑定生产文件及 190 个 compat 文件前后复核通过，没有读取原留出来源，也未调用生产投影作为判断基准。报告 SHA256 为 `c6080839345739a32b4919c9d05ed47a84e452da4b82a53238ae9822669858a6`。这是全集保存证据的独立重建，独立真实重放的范围仍只有下面注明的首场。

### 实现与真实回归

来源专项 48 项通过。首场固定开发录像 9080976703 的冻结源码小跑已完成：15 个机会均 observed，10 帧有可见单位，89 次可见单位观察，公开允许字段无缺失，耗时 34.7 秒。证据在 `reports/b5-camp-evidence-20261126/probe-frozen-first/`，199 个源码文件冻结在 `probe-producer-1/`。此前未冻结的小跑被前后源码漂移检查拒绝，未作为验收或复制进正式批次；原日志保留。

首场另由独立采样实现真实重放，15 帧、3,065 条全知原始单位行、89 条己方可见行均零差异；位置用 Gem 既有 `_pos` 比较，并另存 cell/offset，PlayerResource、名称表、视野位、首回调和最终时钟均复核。输入、代码及兼容包前后哈希一致，证据为 `reports/b5-camp-evidence-replay-check-20261126/REPORT.md`。这仍共用同一 Gem 协议解析器，不能称为不同解析器的交叉验证，也不代表全部 1,169 场已独立重提。

同目录 `linkage.json` 将这次独立重放连接到正式批次同场的 15 帧：原始 capture 完整内容及公开 evidence 均精确一致，来源与投影模块字节相同。两次生产者目录不同，因此只证明这组帧及指定模块一致，不声称整个目录相同。

正式批次先跑原计划前四场，52 帧全部 observed，565 次可见单位观察；10 帧零可见，允许字段无缺失。之后增加四个既有身份/受控单位回归场（9081458883、9090682276、9090978218、9084444002），累计八场、106 帧全部 observed、1,221 次可见观察、11 帧零可见，允许字段无缺失。所有原机会均保留。这些是按工程风险选择的回归，不能作为模型独立验收或推断全集覆盖率。

独立验收 `reports/b5-camp-evidence-review-20261126/{smoke-1,pre-full-8}/` 不导入生产投影作为 oracle，而是重算原始 word 的 bit、单位名称/handle、公开白名单与每个固定机会；原 demo/meta/receipt、全部产物、11 个绑定生产文件和 190 个 compat 文件前后复核。最新版十项注入篡改均被拒绝，含用布尔 false 冒充整数 0（`probe-independent-v2.json`）。保存证据自身不能完全独立复原坐标或全部 PlayerResource 原字段，因此另有上述真实单场重放补证，不混称验证范围。

八场另做受控/召唤/尸体语义核查：可见的非零控制掩码记录 53 条、不含 neutral 名称前缀的召唤单位 15 条、life_state=2 且 HP=0 的记录 56 条均正确保留（类别可重叠），控制字段本身不进入公开层。Magnus t935 的可见骷髅存活、HP73；Sven t943 的四个后续核验身份只有一个在当前帧出现，其余未从未来倒填，也未据此推断尚未出生。当前 owner 字段未解析到时，不拿后续 owner 链补足。具体身份和原始指针见 `reports/b5-camp-evidence-replay-check-20261126/controlled-regression/REPORT.md`，属于审计诊断，不能转作事前所有权或库存特征。

专项共 108 项通过；串行全量检查为 2,094 pytest、10 learning、12 knowledge、前端和 Ruff 全部通过，8,930 文件前后指纹一致。日志与指纹在 `reports/b5-camp-evidence-20261126/check-initial*`。

专项要覆盖首回调后状态变化、重复 tick、缺观察者、可见位图 64 位边界、UnitNames、实体 index 重用、隐藏属性及未来数据非干扰、严格恢复和来源漂移。真实验证先用固定开发计划的小批机会，再扩至全集；既有控制单位案例用于检查解析语义，不构成新的训练样本选择。

收尾复验串行运行 `scripts/check.py --scope all`，日志和包含未跟踪源码的前后指纹存于 `reports/b5-camp-evidence-20261126/check-final*`；只有命令退出 0 且前后指纹一致才提交结案。固定人口、每帧投影、字段覆盖和缺失原因已分别核对，不能把这些工程核验扩大成游戏语义全部核实。路线可通行、营地完整存量和清营能力仍各自待证，训练另按研究契约执行。

## API、批处理与恢复

`capture_camp_evidence(raw_demo_path, cases)` 接受解压 `.dem` 和 `(hero, t)` 对，返回 `gem-camp-evidence/1`；`project_camp_evidence(captured)` 返回 `camp-evidence/1`。后者为纯投影，不加载 Gem。来源延迟加载指定 compat-v1，验证 manifest 和全部 190 个 Python 文件；缺包、源码增删或哈希不符均拒绝。

CLI 的 `--compat` 指向 **gem 包目录**，不是父目录。`--limit 4` 只处理固定计划的前四场，已完成场也计入四场并重新校验；不会截短计划。去掉 limit 即继续全集。`--match` 可重复指定，仅允许固定计划内比赛作回归。最多四个工作进程，复用现有虚拟环境。

```bash
PYTHONPATH=src .venv/bin/python scripts/collect_b5_camp_evidence.py run \
  --plan reports/b5-farm-income-20261125/plan.json \
  --data data/demos-2026-11 \
  --compat data/replay-pilot-2026-10-22/compat-v1/gem \
  --out reports/b5-camp-evidence-20261126/batch-v1 --workers 4 --limit 4

PYTHONPATH=src .venv/bin/python scripts/collect_b5_camp_evidence.py report \
  --plan reports/b5-farm-income-20261125/plan.json \
  --data data/demos-2026-11 \
  --out reports/b5-camp-evidence-20261126/batch-v1
```

长任务从明确冻结的生产者目录运行，并把该目录的 `src` 放在 PYTHONPATH 中；CLI 验证实际导入位置属于生产者。当前工作区变更后不能冒用旧目录续跑；须回到完全相同的冻结实现，或为新实现另建批次，不忽略哈希失配。

每场原子发布 `matches/<match>/{raw.json,evidence.json,receipt.json}`。raw 是 `b5-camp-raw/1` 的全知审计包装；evidence 是白名单公开证据；receipt 绑定固定机会、录像/元数据/原收据、生产者、compat 及两个载荷的摘要。根 manifest 绑定整个批次，单目录写锁防止并发写；未发布的暂存目录不计完成。恢复时重读来源，校验载荷并重新投影比较，不能只检查文件存在或 checksum。

`report` 固定开始时已发布的名单，后来发布的比赛留给下一份报告。完整与待补按原计划计算，字段覆盖仅统计己方可见单位，不报告隐藏单位数量。`complete=true` 只说明固定人口已有结果，须结合缺失状态和独立审计理解；未取得证据的帧照样保留，不自动补零。

### 本轮冻结运行

生产者位于 `reports/b5-camp-evidence-20261126/producer-candidate-1/`，全部 200 个 Python 文件（199 个 src＋CLI）与提交 `bb34f940b1062f1a34a76fbc0063144efb9e3710` 精确一致；`provenance.json` 与 `committed-producer.json` 记录绑定。实际批次为同目录的 `batch-v1/`，八场小跑和后续全量使用同一实现，不覆盖既有场次。

`full_supervisor.py` 依次执行全集 run、完整 report、独立 `verify_batch.py --require-complete`，三步均退出 0。`full-run-1/status.json` 已记录 complete，北京时间 2026-11-26 12:57:42 开始、16:03:21 结束；生产报告为 `full-run-1/final-report.json`。独立验收器也被冻结并自查前后源码 SHA。以后续跑仍须先核对实际进程与输出锁，不凭旧状态文件猜测已停止，更不能在活跃写进程下抢锁。

另用 `reports/b5-camp-evidence-quality-20261126/coverage.py` 从公开 evidence 按原 action/fold/观察阵营报告提取质量。它固定已发布快照，未知动作照常保留，未发布机会为 pending 而不是 missing_frame；不读取隐藏单位或比较行动收益。14 项故障测试通过，相同快照产物摘要可重复。完整批次已用 `--require-complete` 核对全部机会及唯一 t==duration 边界；`final/` 取代部分覆盖快照作为本轮结案依据，旧报告保留。

实体 index/serial 用于定位证据和区分生命周期，不应直接作为数值训练特征。原始 owner/control 等字段仅供审计；公开单位阵营也不能单独证明野怪归属、敌对关系或可清营。
