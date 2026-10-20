# 数据准备进度：2026-10-16

## 2026-10-18 新增数据用途授权更新

用户明确允许使用新增1038场，替代下方“新增仅审计”的用途限制；不等于立即训练、随机重划或批准具体标签/分组选择。
新队列v2方案与本机算力判断见[接入草案](purchase-cohort-v2-plan-2026-10-18.md)。旧952及所有冻结审计声明保留历史，不改写旧产物。
当前先确认扩展身份图、整组开发划分与标签口径，再准备v2快照；没有真实训练或新增独立测试集。

## 公共读取收尾 — 2026-10-17上午

采样和玩家关联已迁移至公共source_io；旧私有函数仅兼容，不再被其他模块引用。
旧952快照兼容重建通过，7项实现清单变化已登记，全部非实现字段一致；新队列审计统计/顺序/类型不变。
新审计及公共包位于reports/public-reader-2026-10-17/；操作见[公共接口](public-source-reader.md)。
下方“13项当前实现不变”为凌晨历史结果；旧快照内13项记录仍不改写，当前重建清单为15项。


## 2026-10-17 模块化兼容更新

来源核验下沉data.validation，纯上下文在contracts，交接读取在handoff.bundle。新审计reports/refactor-2026-10-17/cohort-audit.json已离线重建，audit-differences.json确认相对10/16兼容审计仅生产者哈希一项变化。
旧快照13项实现哈希不变，无新划分或训练。新包在独立handoff目录发布。下方所有“本轮”“当前生产者”及10/16 SHA属于历史轮次，不代表10/17代码。
当前操作见[维护指南](modular-maintenance.md)及[交接协议](handoff/purchase-data-interface.md)。

> 前述首轮审查、验证和文件保留情况属于当时历史记录；同日后续可靠性修复与当前验证见文末增补。

## 本轮实查与范围

目录dota2-timing，分支feat/purchase-data-prep，HEAD af239e9040116903e3fb8e66416fc381030a6720。
首次git status仅三个未跟踪文件；完整阅读项目规则、交接必读协议，旧会话只提取文字要求。
磁盘实测data 689MiB、reports 57MiB（打包前），文件系统可用约938GiB。
未读写模型worktree；不训练、不真实对照、不联网补采、不提交/推送/合并。

三个遗留文件完整保留，不覆盖、不删除、不编辑：

| 文件 | 审查与实测 |
|---|---|
| scripts/audit_purchase_cohorts.py | 离线CLI、拒绝覆盖已有报告；已存在报告未被覆盖 |
| src/dota_items/data/cohort_handoff.py | 已有来源检查、连通图、分布与包哈希校验；无打包入口，verify_bundle不是完整语义加载器 |
| tests/test_cohort_handoff.py | 7项实测通过；覆盖桥接汇总、缺失值和包哈希/路径，不代表全面故障覆盖 |

遗留模块294、295行存在两处Ruff E501。numeric函数仅按数值类型筛选，未显式拒绝NaN/Inf；
本次真实统计未出现非有限值。保留代码，不把当前回归通过描述为通用强校验完成。

## 已验证证据

磁盘已有reports/purchase-cohort-audit-2026-10-16.json。执行build_audit重新计算，
规范化JSON与原报告完全一致：旧快照verify_snapshot通过；新增16批预检逐批离线重放，
冻结计划、发现响应、批次完成/清理收据、候选清单和现存来源哈希验证通过。
没有写回或修复原报告/缓存。审计SHA-256：

a411e08e5cd3c17a534a31e77eb06a441f184051188e506a3033459632deb8a4

| 分母 | 旧批 | 新批 |
|---|---:|---:|
| 尝试处理 | 2900 | 1600 |
| 初筛候选 | 952 | 1038 |
| 排除记录 | 1948 | 562 |
| 排除记录现存缓存 | 0 | 561 |

新旧尝试ID不重叠，候选1,990份来源核验通过。旧排除仅有历史收据，不可独立重放原始内容。
新增1,599份可检查缓存；另1场缺文件，不把1,600次尝试写成1,600次下载成功。

### 排除证据的含义

- 558场purchase_log_not_present：原字段缺失，证据不足，不是实际未购买；五装备unknown，不能填负标签。
- 3场invalid_purchase_events：按冻结预检规则不合格，保留缓存，不自动恢复为候选。
  全部可检查分母里的观测器仍报告1041份present（1038+3），因为两种检查粒度不同；
  该诊断表不授权3场训练，不用它绕过原预检。
- 1场audit_invalid（9042034504）：离线审计为FileNotFoundError，采集failure收据为ValueError；
  两个阶段分别保留，不能从缺文件推断比赛内容或伪造下载成功。
- 旧排除：1828条日志不存在、2条事件非法、118条audit_invalid；只认证收据当前哈希，
  不声称原缓存已重验，亦不改变既有清理历史。

## 玩家连通性：不改变划分

| 图范围 | 比赛 | 连通组 | 最大组 | 跨旧split的组 | 这些组中的新增场次 |
|---|---:|---:|---:|---:|---:|
| 旧952 + 新1038候选 | 1990 | 518 | 1270 | 7 | 583 |
| 旧952 + 新1599可检查缓存（含排除） | 2551 | 510 | 1852 | 5 | 1094 |

候选图新旧直接共有642个已知账号；扩展图879个。两图身份槽位均完整，无非法或同场重复账号。
扩展图的组数变少是组进一步合并，不是风险减弱。按账号连接不等于独立现实人物认证。
候选图389场新增没有观察到旧关联；纳入排除缓存后连通关系可能变化，不能把389自动认定为独立测试集。
旧快照本身仍保持571/191/190及原零跨split已知账号交集；新增路径造成的桥接不是原快照被改坏。
报告中的train/validation图桶只表示旧/新队列，不是对新增比赛分配模型split。

## 分布审计（描述性，不是效果评估）

| 指标 | 旧952 | 新1038 |
|---|---:|---:|
| 估算carry / 其他 | 946 / 6 | 1018 / 20 |
| 时长最小 / 中位 / 最大（秒） | 1800 / 2236.5 / 4794 | 1800 / 2190.5 / 4596 |
| 平均段位编码中位数 | 75 | 75 |
| 有效段位记录人数中位数 | 5 | 6 |
| 有1800秒及之后购买事件 | 843 | 889 |
| 有重复源事件行 | 789 | 852 |
| 有同秒不同物品 | 794 | 845 |
| 空购买日志 | 0 | 0 |

新1599份可检查缓存时长均≥1800，补丁时间一致；旧952和新1038同样均满足。
只验证冻结时间证据，不认证比赛客户端版本；段位只是一部分玩家的平均字段，不认证主宰个人MMR。
旧候选北京时间10/13 04:43:44—16:07:12，新候选00:42:54—04:32:24；新增其实更早，
不是时间上的未来测试集。末事件达到1800不证明全程无漏采，早于1800也不能直接判丢日志。
重复源事件保持证据，只对装备存在性计一次；不自行删除或去重修改原始缓存。

| 装备源日志正观测 | 旧952 | 新1038 |
|---|---:|---:|
| bfury | 881（92.54%） | 936（90.17%） |
| maelstrom | 68（7.14%） | 91（8.77%） |
| manta | 756（79.41%） | 836（80.54%） |
| black_king_bar | 0 | 2（0.19%） |
| skadi | 48（5.04%） | 38（3.66%） |

两候选队列各装备unknown均0；这只是合法源日志观测，负值不是真实未买证明。
新BKB仅2个正例，不据此保证可学/可评估，更不改变旧训练集确定的输出资格。
阵容频率以比赛为分母：新减旧最大的若干变化包括敌方英雄12约+2.92百分点、
敌方121约+2.62、敌方126约−2.62；友方31约−2.23、友方123约+1.97。
这是事后描述性比较，不是漂移显著性检验或筛样理由；未按旧test重新选模型。

## 接口交接

新增scripts/package_purchase_handoff.py，复用旧来源重建与字节校验，输出拒绝覆盖。
交接目录reports/purchase-data-handoff-2026-10-16；说明见[接口协议](handoff/purchase-data-interface.md)。
包只复制旧快照、来源摘要和本轮审计，附元数据、mask合成例及哈希清单；不构建新增快照。
不包含原始账号缓存，不是异机完整重放包。尚未在模型分支运行读取器或做双方集成。
打包退出0，5份载荷+manifest已生成；只读加载验证952行、原split、特征及mask维度通过。
manifest SHA-256：41cf85c28f51ed4a565ae05abda5e31bb15bd43f9e8e26c320bdc5222ad102e7。
最终三个遗留文件SHA-256与审查时一致；新增文件格式与git diff --check通过。

## 验证

- 遗留7项+新增打包3项专项测试：10项通过。
- 全库pytest 390项通过；学习10、知识12、JavaScript6项通过，共418项。
- 全库298文件格式检查通过，JS语法检查通过；本轮新增两个Python文件Ruff通过。
- 统一check.py返回1：仅遗留模块两处E501，不能宣称全检查绿色。
- 日志reports/data-prep-check-2026-10-16.log；软件回归使用合成数据，不是真实训练/对照。

## 待用户决定（均未执行）

1. **维持旧实验，新增仅审计**：当前状态，最少改变，不能利用新增数据训练。
2. **构建全新合并队列协议**：先决定是否把被排除但身份可检查的比赛也作为连通证据，
   再整组设计新划分。最大组1270/1990（扩展身份图更大），60/20/20可能严重失衡；
   不可随机拆组，旧留出已看过，不能重新包装成独立最终测试。
3. **设计独立评估队列**：按完整身份图选择与旧数据无连接的比赛，并预先冻结时间与选择规则；
   会减少样本并产生选择偏差，可能需要另行授权补采。不能直接使用上述389作为最终测试。

建议先选择研究用途和连通证据范围，再实现新快照；不在未确认时自动执行上述2或3。

## 文件清单

本轮新增：scripts/package_purchase_handoff.py、tests/test_package_purchase_handoff.py、
docs/handoff/purchase-data-interface.md、docs/data-prep-progress.md。
原三个未跟踪文件保持原样；共享README/CHANGELOG/project-status/pyproject未修改。
本地reports交接包与日志受.gitignore排除。无提交、推送或合并。


## 2026-10-16 同日增补：交接可靠性专项（单目录并行开发）

本轮只修改数据侧5个文件：`src/dota_items/data/cohort_handoff.py`、
`scripts/package_purchase_handoff.py`、`tests/test_cohort_handoff.py`、
`tests/test_package_purchase_handoff.py`、本文。审计CLI只读审查，无需修改。
未修改共享协议、模型、sources、原始缓存或冻结产物；未执行全库验收、真实训练、
对照、选模、补采或任何新增1,038场用途/划分变更。旧开发环境/双worktree指引不执行。

### 已修的实证缺口与兼容性

- 原读取器允许仅列出snapshot的残缺包、JSON重复键及指向包内其他文件的符号链接。
  现复用`purchase-data-handoff/1`固定五载荷清单，严格检查清单类型、SHA-256格式、
  生产者/来源元数据和显式用途声明；缺项、额外清单项、路径别名、越界路径一律拒绝。
  拒绝包根、manifest及载荷符号链接（含包内、外部和悬空链接），只读取普通文件。
  原本完整的冻结包仍可只读加载；仅snapshot的旧测试夹具不再被当作完整交接包。
- 对manifest及所有JSON载荷拒绝重复键、NaN/Inf及溢出为Inf的JSON数字；
  检查snapshot、summary、cohort-audit、synthetic-reader-example各自的schema版本，
  审计的三个研究边界声明必须为false，合成读取例必须保持不可训练声明。
  不复制模型适配器，不声称这些检查已验证完整字段语义、编码或来源真实性。
- 打包器捕获一次输入字节，验证审计证据与来源重建，检查重建前后summary/snapshot
  字节一致，避免后续复制与已验证输入脱节。先校验载荷，再独占创建输出并写入；
  复核落盘载荷后才写manifest。输入无效时不创建输出，写入失败保留现场；
  缺少或截断manifest的目录不能通过读取器，文件/目录/符号链接输出均拒绝覆盖。
  不是跨进程锁或断电持久性保证；使用独立输出路径，不并发改写正在验证的包。
- `numeric`保留原口径：bool、None及其他非数值计missing，不填0；空输入统计量为null。
  NaN/±Inf明确报错，不悄悄删除观测或改变分母；有限输入计算出非有限中位数也报错。
  普通有限数值的observed/missing及统计结果不变。
- 两处E501用相邻字符串字面量拆行修复；`build_audit`的AST（不含位置）与历史实现一致，
  字符串运行时语义不变。没有对其他冻结实现做格式化或搬迁。

### 冻结证据与生产者哈希：不能静默兼容

修改前`cohort_handoff.py`的SHA-256为
`bf2061c23742f7a7dd229cced6f4b3acd518fb6c545c351e13f32467a0cda2bf`，
正是历史cohort审计`evidence_sha256`中的生产者身份。修改代码（包括仅修E501）必然改变它。
旧952快照的implementation清单不包含此模块，所以旧快照来源重建仍通过；
但以当前生产者完整重建历史cohort审计将改变自证哈希，旧审计重新打包时仍会因哈希失配拒绝。
这不是原始数据或旧快照失效，也不能通过忽略生产者哈希冒充历史重现。

历史cohort审计、旧952快照和既有交接包均保持原字节；既有包的完整性读取仍通过。
历史审计SHA-256仍为`a411e08e5cd3c17a534a31e77eb06a441f184051188e506a3033459632deb8a4`，
既有包manifest仍为`41cf85c28f51ed4a565ae05abda5e31bb15bd43f9e8e26c320bdc5222ad102e7`。
原生产者精确字节保留于专项临时目录`/tmp/dota-handoff-data-wqhs5c6q/cohort_handoff.before.py`，
独立核对上述哈希通过；此临时文件不是新证据协议或发布包。

交父会话的兼容建议（未执行）：保留历史生产者用于隔离重放；或在新的不存在输出目录
生成绑定当前生产者的新审计，显式记录生产者身份变化并比较统计内容，不覆盖旧审计。
不能修改历史产物、重写旧哈希或静默放宽打包器校验。共享架构/接口协议应由协调者增补
上述历史生产者限制及严格读包策略；本轮不自行修改共享文件。

### 当前验证与只读交接

- 合成故障专项：107项通过，覆盖缺失/错误schema、重复JSON键、哈希错误、路径/符号链接、
  非有限数、用途声明、输入漂移、拒绝覆盖、载荷损坏、写盘失败及截断manifest。
- 4个本轮Python文件Ruff lint通过、格式检查通过；仅专项，不代表全库验收。
- 既有包只读读取952行，split数量571/191/190；`verify_snapshot`完整来源重建通过，
  未调用fit或效果评估，未按旧test选模。历史审计对当前生产者的失配为预期且未绕过。
- 其余数据实现、旧快照、历史cohort审计及既有包所有文件与本轮开始时指纹一致。
  AST比较确认`numeric`/`verify_bundle`以外所有原有函数语义不变。

复现专项（复用`.venv`，将`--basetemp`替换为本次独立临时路径）：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_cohort_handoff.py tests/test_package_purchase_handoff.py -q -p no:cacheprovider --basetemp=/tmp/dota-handoff-data-wqhs5c6q/pytest-final
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check --no-cache src/dota_items/data/cohort_handoff.py scripts/package_purchase_handoff.py tests/test_cohort_handoff.py tests/test_package_purchase_handoff.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff format --check --no-cache src/dota_items/data/cohort_handoff.py scripts/package_purchase_handoff.py tests/test_cohort_handoff.py tests/test_package_purchase_handoff.py
```

只读消费仍调用`verify_bundle(Path("reports/purchase-data-handoff-2026-10-16"))`，
不调用打包器重写既有目录。验证文件完整性与schema不等于模型语义校验、完整来源重放、
真实性认证或研究授权；manifest身份需与独立交付记录比对，来源重放需原缓存/证据/对应实现。
当前包和新增审计均不授予真实训练或新增数据用途。


## 2026-10-16 同日增补：当前生产者兼容收尾（父会话集成审查）

本次按父会话接续授权，使用同一既有队列进行离线描述性工程重建，落实上节此前“未执行”
的新审计/新包方案。没有新增研究用途授权，不改变快照、标签、split或统计口径，不训练、
不做真实模型效果评估/选模、不补采。仅修改本文；源码、测试及共享文件均未修改。
以下是本次实测，不把上文历史全库/专项结果冒充本轮验收。

### 历史生产者归档与当前产物身份

第一步先将临时目录的精确历史生产者独占复制到项目新目录：
`reports/purchase-cohort-producer-archive-2026-10-16/cohort_handoff.py`，
同目录`identity.json`记录来源、逻辑路径、SHA-256与用途。复制前后均与历史审计核对：
`bf2061c23742f7a7dd229cced6f4b3acd518fb6c545c351e13f32467a0cda2bf`。
未覆盖当前源码；该归档只是历史文件保全，不声称已保存可运行的完整隔离环境。

独立新目录为`reports/purchase-cohort-compatibility-2026-10-16/`，全部拒绝覆盖：

| 文件 | 本次结果/身份 |
|---|---|
| `cohort-audit.json` | 现有audit CLI离线重建；SHA-256 `f7f23fac5c5aaa51a0a28f6db6204d027d2559e7c670c2093a1799ed070fde77` |
| `audit-differences.json` | 新旧JSON逐项比较，无排除字段；完整差异仅1项，详见下节 |
| `handoff/` | 现有package入口生成5载荷+manifest；不创建新增建模快照 |
| `handoff/manifest.json` | SHA-256 `08bfcbb1fe3a974c514a0c14f6a18e0a5749864b5aec24cbec80f9c2017297f8` |
| `readonly-verification.json` | 独立来源重建、读包及受保护文件指纹核验均通过 |
| `protected-before.sha256.json` | 重建前7,601项旧证据、完整data目录、源码等文件指纹；核验后无漂移 |
| `audit-cli.log`、`package-cli.log` | 两个现有入口均退出0 |
| `compare_audits.py`、`verify_readonly.py` | 本次任务的可重复验证脚本；不是新快照/交接协议，不复制模型适配器 |
| `workspace-before.txt`、`delivery-files.sha256.json` | 起始Git状态与本次交付文件指纹；未提交/推送 |

当前审计生产者`src/dota_items/data/cohort_handoff.py`：
`46e261c2bc432f9728d60ad2a8c7c35f3df7e133cceb8a4110d5733c2a06e389`。
现有audit CLI `scripts/audit_purchase_cohorts.py`：
`d5b164c8e1cb9dc03f4b89691331c02c1903ae0a8491846e3d6b46f43bba81e9`。
现有打包入口`scripts/package_purchase_handoff.py`及新manifest的producer_sha256：
`c9a7dd7c3fce7845b39c26ed7aa3bab1ee8ea34bcc5d27e41d44219c96a53812`。
这些身份绑定本次实测实现，不是签名或来源真实性认证。reports受Git忽略规则排除，仅本地保留。

### 新旧审计的全部差异（仅1项）

唯一变化字段为：
`evidence_sha256["/home/node/.openclaw/workspace/work/dota2-timing/src/dota_items/data/cohort_handoff.py"]`。
旧值`bf2061c23742f7a7dd229cced6f4b3acd518fb6c545c351e13f32467a0cda2bf`，
新值`46e261c2bc432f9728d60ad2a8c7c35f3df7e133cceb8a4110d5733c2a06e389`。

比较遍历所有JSON键、值、列表顺序与类型，不整体删除evidence或统计字段。
除上述单一生产者指纹外，collections、distributions、graphs、limitations、schema、
三个研究边界声明及其余来源指纹完全一致。旧952/新1038候选及新1599可检查缓存分母未变，
没有统计、队列或边界变化；若有任何其他差异，比较脚本非零退出，禁止继续打包。
这是一致性核验，不是新增1,038场的训练/评估准入。

### 当前来源校验、只读验证与旧证据保全

- 打包入口实际校验新审计证据并重建旧快照成功，没有跳过生产者哈希或放宽来源闸门。
- 独立`verify_readonly.py`再次核对5,545项新审计证据；`verify_bundle`分别读取新旧包，
  两者snapshot完全相同；包内snapshot/summary与原文件逐字节一致。
- 对新包内snapshot和summary另调用`verify_snapshot`完成来源重建；952行、
  split=train571/validation191/test190、254列不变，包在只读验证前后指纹相同。
- 7,601项受保护文件全部无漂移，覆盖旧审计、旧包、完整data及源码。历史审计SHA-256仍为
  `a411e08e5cd3c17a534a31e77eb06a441f184051188e506a3033459632deb8a4`，
  旧包manifest仍为`41cf85c28f51ed4a565ae05abda5e31bb15bd43f9e8e26c320bdc5222ad102e7`；
  旧快照仍为`f666e52d1748811997bb1652b1cb35b283f942a199bc65c5c8aff84732c12096`，
  旧summary仍为`2ea8231ba932d8b48873149e1c917bfadf3a8c1eb1a771885d96a13e8ffe0560`。
- 独立验证进程没有导入modeling模块，没有fit或模型效果评估。完整来源重建含原确定性快照
  重算，只比较既有快照，不写新标签/split。旧排除原始缓存缺失的历史局限仍保留；
  新审计不把“收据哈希成功”升级为独立原始来源重放或真实性认证。
- 本次无源码改动，未重复既已通过的107项合成专项，未自行全库验收；最终集成验收由父会话负责。
  严格历史审计重新打包仍会拒绝当前生产者失配；当前工程复现应先重建新审计，再打包新目录。

### 可重现命令

以下复用现有`.venv`、现有audit/package入口和相同相对输入路径。已交付目录不能重跑覆盖；
复现时`COHORT_RUN`使用全新的目录名。先运行比较，退出0才允许执行下一条打包命令；
任何统计/队列/边界变化均停止报告，不放宽闸门。

```bash
set -e
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1
COHORT_RECORD=reports/purchase-cohort-compatibility-2026-10-16
COHORT_RUN=reports/purchase-cohort-compatibility-replay-REPLACE-WITH-UNIQUE-NAME
mkdir -- "$COHORT_RUN"
.venv/bin/python scripts/audit_purchase_cohorts.py \
  --old-root data/purchase-1000-2026-10-14 \
  --new-root data/purchase-additional-1000-2026-10-15 \
  --summary reports/purchase-952-summary-2026-10-14.json \
  --snapshot reports/purchase-log-snapshot-952-2026-10-14.json \
  --output "$COHORT_RUN/cohort-audit.json"
.venv/bin/python "$COHORT_RECORD/compare_audits.py" \
  --old reports/purchase-cohort-audit-2026-10-16.json \
  --new "$COHORT_RUN/cohort-audit.json" \
  --output "$COHORT_RUN/audit-differences.json"
.venv/bin/python scripts/package_purchase_handoff.py \
  --summary reports/purchase-952-summary-2026-10-14.json \
  --snapshot reports/purchase-log-snapshot-952-2026-10-14.json \
  --audit "$COHORT_RUN/cohort-audit.json" \
  --interface docs/handoff/purchase-data-interface.md \
  --output "$COHORT_RUN/handoff"
```

本次实际`COHORT_RUN`为`reports/purchase-cohort-compatibility-2026-10-16`，audit/package/compare
均退出0；独立只读验证命令如下。再次验证交付时仅将输出放到新临时目录，原包保持只读：

```bash
set -e
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1
COHORT_VERIFY_TMP=$(mktemp -d /tmp/dota-cohort-readonly-XXXXXX)
.venv/bin/python reports/purchase-cohort-compatibility-2026-10-16/verify_readonly.py \
  --run reports/purchase-cohort-compatibility-2026-10-16 \
  --output "$COHORT_VERIFY_TMP/readonly-verification.json"
```

核验保留本次生产窗口的完整保护指纹；若以后源码/来源发生变更，会明确失败，不能把旧收据
当作新环境证明。打包不重新计算cohort统计，因此不能省略audit重建及逐项比较步骤。
新manifest并不使包具备异机完整来源重放能力，也不授予真实训练或任何新研究用途。

## 2026-10-18 增补：已有审计的只读 Markdown 质量报告

新增数据侧文件：src/dota_items/data/cohort_report.py、scripts/report_purchase_cohorts.py、
tests/test_cohort_report.py；仅增量更新本文。没有改动生产者、source_io、共享契约或冻结证据。

### 接口与边界

- API：cohort_report.validate_audit(dict)、render_report(dict) → Markdown、
  write_report(Path(input), Path(output)) → 输入字节SHA-256。CLI显式要求--input及--output。
- 只支持purchase-cohort-audit/1，可带既有public-reader/1迁移声明；未知版本失败。
  通过公共data.source_io.read_source_bytes限量读取单个审计文件；局部严格JSON解码拒绝
  重复键、非有限数（包括1e999）。不修改历史parse_source_json的宽松兼容行为。
- 检查报告相关必需字段、非负整数（不接受bool）、尝试/候选/排除分母、排除记录及原因计数、
  缓存与证据层级、日志/观测支持分母、数值摘要边界、图内组及汇总一致性和研究边界声明。
  这些是已有JSON内部一致性检查，不重建审计、不读原始缓存、不认证证据哈希所指文件。
  不是完整历史schema所有附加字段的语义认证；尤其不重新验证原始身份、英雄频数或逐场内容。
- 报告仅显示聚合计数，不输出逐场ID、账号、缓存路径或证据路径。动态文本转义为纯文字；
  明确旧/新候选、排除原因可重叠、缺日志未知、两种图范围和跨旧split含义，以及待决定用途。
  缺字段失败而非补0；证据不足不冒充已证实不符合。训练/新划分许可均不改变。
- 验证及完整渲染后，在目标父目录暂存，通过排他硬链接发布；文件、目录、符号链接及悬空
  链接输出一律不覆盖，竞态已有目标也保留。普通解析/写入/发布失败不留半份正常报告。
  父目录须已存在且可信；文件系统需支持硬链接，不保证断电持久性或对抗恶意目录替换。

### 使用及预期

在仓库根目录，复用现有环境；每次创建自己的临时目录，不覆盖示例输出：

~~~bash
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1
REPORT_RUN=$(mktemp -d /tmp/dota-cohort-report-XXXXXX)
.venv/bin/python scripts/report_purchase_cohorts.py   --input reports/public-reader-2026-10-17/cohort-audit.json   --output "$REPORT_RUN/cohort-quality.md"
.venv/bin/python -m pytest tests/test_cohort_report.py tests/test_source_io.py   -q -p no:cacheprovider --basetemp="$REPORT_RUN/pytest"
.venv/bin/python -m ruff check --no-cache src/dota_items/data/cohort_report.py scripts/report_purchase_cohorts.py tests/test_cohort_report.py
.venv/bin/python -m ruff format --check --no-cache src/dota_items/data/cohort_report.py scripts/report_purchase_cohorts.py tests/test_cohort_report.py
~~~

预期报告转述旧候选952、新候选1038（新增用途未授权）；候选图1990场/518组/最大1270场，
扩展图2551场/510组/最大1852场。数字来自历史JSON，不是本轮重新采集或重算的新实证。
CLI失败返回1且不打印原始载荷；成功打印输入SHA-256。模块API保留ValueError/OSError供调用者处理。

### 本轮准确结果（非全量验收）

- 独立目录/tmp/dota-cohort-report-JhskB7；最终pytest命令的basetemp为该目录/pytest-final。
  新报告58项合成测试 + 既有source_io 23项，共81 passed；三个新Python文件Ruff及格式检查通过。
  覆盖缺字段、bool/负数、矛盾计数、篡改边界、重复键、非有限数、文本转义、输入失败不落盘、
  拒绝覆盖/悬空链接、发布失败清理和发布竞态。不代表真实模型效果验证或全库验收。
- 只读运行上述CLI，实际输出/tmp/dota-cohort-report-JhskB7/historical-report.md，退出0。
  输入前后SHA-256均为91cd0857a9f259711e5625e3e6e7abdd62725d4c17898c3c02915d3a964f95d5。
  没有重算历史审计或读取原始缓存，历史证据及旧训练/划分边界保持不变。
- 无依赖安装、真实训练/选模、补采、提交、推送或合并。没有改共享文件。
  当前check.py默认把新非model测试纳入data，无需修改测试分组；报告CLI的全库检查仍由协调者串行执行。
  共享文档导航若需新增入口，由父会话协调维护README/docs目录页，本侧未擅自改动。
