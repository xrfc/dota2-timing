# 数据流程与开发

## 原始录像试点 — 2026-10-22

3场录像已下载、保留原始与解压哈希；Gem 0.10.0均提前终止，0场可用轨迹/视野，身份解码亦不匹配。未修改依赖或训练输入；下一步是解析兼容性诊断，不是扩大采集。详见[试点报告](replay-pilot-2026-10-22.md)。

更新：2026-10-23。数据方向唯一持续维护的流程、现状、决策和后续任务文档。
整体优先级见[项目总路线](roadmap.md)，消费者见[模型流程](model-foundation.md)。

## 1. 当前目标与已确认设置

为“开局双方阵容预测主宰整局11装备源日志出现”提供可追溯输入，不把购买行为当成最佳出装标注。

| 项目 | 当前设置与限制 |
|---|---|
| 队列 | 旧952＋新增1038，共1990场；7.41f来源时间证据不等于独立客户端版本认证 |
| 英雄／位置／段位 | 主宰hero_id=8；一号位是请求范围，非逐场独立认证；部分玩家平均段位不认证主宰个人MMR |
| 时间 | 全部保留比赛至少30分钟；整局新标签仍受长局筛选偏差影响 |
| 划分 | 用户确认比赛随机80/20、seed=42，1592训练／398开发验证，允许玩家重叠，无独立test |
| 随机实现 | 按SHA256(json_bytes([42, match_id]))排序、ID破并列；并非sklearn随机划分，不换seed找成绩 |
| 输入 | 仅train拟合127英雄词表，友敌multi-hot及unknown_count，共256列；不含账号、未来经济、时长或胜负 |
| 标签 | 有效源purchase_log出现对应key为1；合法日志未记录为0，不证明实际未买；缺失／非法不能补0 |
| 任务版本 | juggernaut-source-log-7.41f-whole-11/1，window=null；快照/2、契约/1 |

装备顺序：bfury、maelstrom、mjollnir、manta、sange_and_yasha、butterfly、blink、ultimate_scepter、monkey_king_bar、diffusal_blade、skadi。
A杖不合并升级A杖或魔晶；升级装备不用于推断未记录的前置购买。合法赛前负时间记录保留，不用终局库存回填标签。

## 2. 全流程

1. **来源与范围**：固定时间、补丁证据、英雄及请求预算；保存发现计划、请求／失败收据和缓存。更晚窗口曾获方向确认，不等于具体范围、硬预算和采集已执行。
2. **身份去重**：检查match_id、来源哈希、唯一目标英雄；新批去重要涵盖历史计划／失败／缓存，不只保留候选。
3. **资格与排除**：分开记录尝试、成功、可检查、候选及排除。新增1600次尝试中1038候选、558日志缺失、3事件非法、1缺缓存；旧排除部分只有收据，不称原始数据完整重放。
4. **语义与覆盖**：检查事件及时间，记录段位覆盖、时长和玩家连通性。日志合法不等于完整；证据不足不等于已证实不符合。
5. **成员冻结**：沿用批准划分及成员摘要；已知683个玩家跨train/validation，44个目标主宰账号重叠，不能宣称玩家独立。
6. **编码和标签**：词表仅由train拟合，未知保留mask；整局标签独立版本，旧30分钟和旧952快照不覆盖。
7. **快照发布**：来源及父包验证后写snapshot/sources/split/report/protection，complete最后写；已有目录拒绝覆盖。
8. **模型交接**：adapt_snapshot读取X/y/mask；来源统一data.source_io，迁移只接受登记的生产者指纹差异，非实现字段完全一致。

## 3. 已完成与证据

| 产物 | 状态 | 证据入口 |
|---|---|---|
| 队列审计及公共读取 | 已完成限定来源核验 | [公共读取](public-source-reader.md)、[历史数据记录](archive/2026-10-22/data-prep-progress.md) |
| 随机v2 | 已生成／重放 | [规则与命令](random-cohort-v2-2026-10-21.md)；reports/cohort-random-v2-2026-10-21/ |
| 整局11装备 | 已生成／重放，两侧均有正负样本 | [支持数与验收](whole-log-task-2026-10-21.md)；reports/cohort-whole-log-11-2026-10-21/ |
| 模型消费 | 已通过适配并用于固定实验 | [模型主文档](model-foundation.md)；生产时“未训练”不否认后续训练 |

历史验收数字按对应日期和范围解释；本次整理没有重放真实数据或全库验收。

## 4. 接口、命令与维护

- data.random_cohort_snapshot：随机成员与快照；data.whole_log_snapshot：整局观测、重标与包构建。
- scripts/prepare_random_cohort.py、scripts/prepare_whole_log_cohort.py：生产／--verify只读重放。
- data.source_io为公共读取，data.validation为来源校验；handoff.bundle的载荷核验不代替来源认证。
- contracts.tasks是共享任务定义；data不得依赖workflow，不能绕过指纹失配。

已有整局包的只读核验（失败应停止，不放松校验；不训练）：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/prepare_whole_log_cohort.py --parent reports/cohort-random-v2-2026-10-21 --output reports/cohort-whole-log-11-2026-10-21 --verify
```

生产命令见[随机记录](random-cohort-v2-2026-10-21.md)、[整局记录](whole-log-task-2026-10-21.md)；接口见[任务契约](task-contracts.md)、[数据交接](handoff/purchase-data-interface.md)。这些仅作技术／证据参考，不另维护路线。

## 5. 任务状态（不自动执行真实采集）

| ID | 依赖／优先级 | 内容 | 完成标准 |
|---|---|---|---|
| DATA-01 | 已完成（2026-10-22） | 独立交接校验入口与身份记录，真实来源及旧基线只读核验通过 | 新训练消费者的前后校验接入留MODEL-02；本轮未训练 |
| DATA-02 | 独立评估方案前 | 更晚窗口／补丁、玩家重叠、长短局覆盖方案 | 列可比较性和独立性限制，不先把新增数据叫test；关键范围由用户决定 |
| DATA-03 | DATA-02及采集准入 | 复用采集器补单轮硬预算、全历史去重及停止证据 | 合成验证预算／429即停，不自动保活，不按装备或胜负选样 |
| DATA-04 | 获准小批采集后 | 新版本来源审计与交接 | 尝试到排除分母完整、旧产物不变；新用途和划分单独决定 |
| DATA-05 | 三场限定审计已完成，语义准入未完成 | 核验视野、位置、经济、库存与玩家可知信息 | 时序和人工核验证据明确；未认证字段不进入决策特征 |

DATA-02以后不阻塞现有冻结输入的正则化对照。当前不启动补采、重划分或扩大英雄／补丁范围。

## 6. 学习与历史

L01–L12按需补基础，不要求重建已完成管线；[个人学习记录](../learning/docs/roadmap.md)不自动勾选。
[整理前原文](archive/2026-10-22/data-prep-progress.md)保存完整历史和详细API；旧952、30分钟五装备和整局11装备不混用支持数或授权。
以后流程、决策、DATA任务只更新本文；长日志与不可变证据另存并登记链接。

## 7. DATA-01输入交接保护（2026-10-22）

用户本轮授权实现输入保护，不含真实训练。新增scripts/verify_whole_log_handoff.py及tests/test_whole_log_handoff.py；未修改生产者、快照、旧实验或训练逻辑。
复用来源重放verify_inputs与诊断verify：核验父包和整局全部载荷、1592/398成员及X/y/mask维度、任务／词表／行序／标签／mask身份；绑定既有frequency/C=1模型，逐行重算预测和指标，检查固定基线参数。

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/verify_whole_log_handoff.py --parent reports/cohort-random-v2-2026-10-21 --cohort reports/cohort-whole-log-11-2026-10-21 --baseline reports/whole-log-fixed-baseline-2026-10-21 --output reports/whole-log-input-handoff-2026-10-22
```

以上是已执行命令，输出现已存在，禁止原路径重跑覆盖。复验可使用不存在的新输出目录并加--expected reports/whole-log-input-handoff-2026-10-22；比较完整输入身份及保护清单，不训练。handoff.json记录身份／保护哈希，complete.json最后发布。失败目录不自动删除，缺完成收据不视为成功。
输入指纹使用绝对路径，异机搬迁不能直接沿用；需重放并生成新交接，不能忽略路径／哈希失配。read_handoff(directory)可只读核验完成收据、报告身份摘要和全部保护文件；它不重新重放来源，也不是物理文件锁。后续训练前后都应调用，不能只在现在验证一次。

真实交接：reports/whole-log-input-handoff-2026-10-22/；identity_sha256为2ccbe366afacb9462605038605389739c409c550a516b66960febb97d56a3d83，training_executed=false。来源重放与旧模型预测／指标复算均通过，未修改成员、词表或标签。
专项68项通过（输入保护、旧实验、诊断、整局快照），新增文件Ruff通过；不是停写窗口下的全库验收。哈希保护证明一致性，不证明日志完整、最佳出装或验证独立性。

## 8. 两路采集复测与新批次（2026-10-22）

用户授权测试原两路脚本，可用则再取一批。本轮复用现有collect_purchase_latest.py的direct/proxy选项及共享互斥锁，未改采集代码、预算参数、凭据或环境；不是两个并发worker。31项采集／去重／预算专项通过。

| 路由 | 真实测试结果 | OpenDota请求 |
|---|---|---|
| direct | 官方补丁列表TLS连接被重置，保存failed收据；尚未测试到OpenDota连通性 | 0 |
| proxy | 官方补丁源及OpenDota可访问，成功保存新详情；达到分钟余量保护后退出75 | 69＝2发现＋67详情 |

原直连预算reports/collection-runtime/request-budget.json及代理预算data/purchase-proxy-trial-2026-10-15/request-budget.json继续使用，未重置历史记录。官方补丁证据请求不计入OpenDota请求数。
本批范围：7.41f发布时间证据，UTC 2026-10-19 04:42:34至2026-10-22 03:42:34（左闭右开），主宰、Ranked All Pick、至少30分钟、avg_rank_tier>=70的发现口径。既有五装备前30分钟观察仅用于历史采集诊断；不自动生成整局11装备训练标签，不把平均段位当主宰个人认证。

- 历史排除4751个ID；冻结200场计划，确认与历史排除不相交。
- 保存67份HTTP 200详情及来源manifest，3场通过既有初筛、64场purchase_log_missing；原始失败／排除缓存保留。
- results有68条，最后1条请求未预留即因预算暂停；实际详情请求／保存数是67，不是68。剩余133个计划ID未请求，仍保留在原计划中，不新建目录绕过去重自动补采。
- 停止时服务端日余量2931、分钟余量5、最后HTTP状态200；命中65秒分钟保护，不是429或日额度用尽。未自动冷却续跑、换出口或创建后台任务。
- 67份详情哈希及inspect_match只读重放一致，时间均在本批窗口；计划／协议／去重摘要和历史计划指纹核验通过。

已执行命令（目录已存在，禁止覆盖）：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/collect_purchase_latest.py --route direct --output data/purchase-latest-2026-10-22-direct
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/collect_purchase_latest.py --route proxy --output data/purchase-latest-2026-10-22-proxy
```

证据：两目录summary/results及来源收据；聚合复验reports/collection-route-check-2026-10-22/review.json。所有新数据training_allowed=false，不加入原1990场、不给正式split、不训练。3/67仅约4.5%的初筛可用率，不代表3场已达到建模准入。
下一决策：先检查较新对局购买日志可用率与来源覆盖，再决定恢复剩余计划或调整合法发现来源；不因本次代理可用就直接扩大到1万场，也不发付费parse请求。

## 9. 用户授权续采至日预算保护线（2026-10-22，首轮中断）

本节替代上一节“未自动续跑”的当前状态：用户随后明确要求继续至24小时限额。
新增 `scripts/collect_purchase_until_daily.py`，先核验并续取上一批未发送的133场，
再按相同冻结时间窗口向更早match_id发现；仍使用代理原预算和共享互斥锁，不换出口、不重置预算。
新目录 `data/purchase-until-daily-2026-10-22-proxy/` 与旧快照隔离，training_allowed=false。

- 本次启动时滚动24小时已使用69次，固定剩余上限1831次（发现和详情共用），不因旧请求过期扩大本轮额度。
- 分钟余量<=5时等待65秒保护冷却；达到本地1900次滚动上限、服务端日余量<=20、429或本轮24小时截止即停，不自动次日续跑。
- 窗口耗尽、网络或结构异常也会停止，不能保证一定消耗到日额度；这些停止不能报告为成功采满。
- 启动后实查已保存3份详情、0份通过初筛，状态collecting；这是启动观测，不是最终批次统计。
- 实时看status.json；结束看summary.json及results.json，来源载荷及哈希在matches/。保留批次plan，失败不自动覆盖或删除。
- 新增断点／预算测试，连同既有采集专项共40项通过；新增脚本及测试Ruff通过。未做全库验收、未训练、未改正式划分。

已启动命令（输出目录现已存在，不重复启动）：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -u scripts/collect_purchase_until_daily.py --previous data/purchase-latest-2026-10-22-proxy --output data/purchase-until-daily-2026-10-22-proxy
```


## 10. 续采断点恢复（2026-10-22）

首轮续采13:07:39因RemoteProtocolError（服务端断连）退出，不是日额度耗尽。
保存372场、17场初筛通过，355场缺购买日志；与此前67场／3场合计439场／20场。
376次已记请求包含3次发现、372次详情响应和1次断连无响应，不能把请求数当下载数。

用户随后明确要求恢复。新增对daily-purchase-continuation/1中断目录的读取：
检查上游protocol绑定、历史计划哈希、分页计划／发现结果、已存详情哈希及数量；
沿用原时间／补丁窗口和最后游标，已保存响应不重下。断连无响应的1场允许重试，
原请求预算不退回；共61场未保存详情先补，再继续发现。日额度停止的目录不自动恢复。

新目录data/purchase-until-daily-2026-10-22-proxy-resume-01/；原目录只读保留。
启动后已确认新详情落盘，状态collecting；最终数量请读该目录status.json／summary.json。
日志reports/collection-runtime/until-daily-2026-10-22-resume-01.log，PID同名.pid。
仍采用原代理、预算和互斥锁，分钟冷却等待；日保护线、429、窗口耗尽或异常即停，不自动跨天。
不承诺后台必然连续运行到额度；未改变初筛、训练准入或正式划分。

验证：15项断点／预算测试及26项相关采集／预算／历史回归通过，Ruff和格式检查通过。
本轮仅改续采脚本、对应测试及本文，不修改模型代码或产物，不做全库验收。

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -u scripts/collect_purchase_until_daily.py --previous data/purchase-until-daily-2026-10-22-proxy --output data/purchase-until-daily-2026-10-22-proxy-resume-01
```

以上已启动，禁止对同一输出目录重复执行；所有新数据training_allowed=false。


## 11. 恢复批次最终状态与录像审计（2026-10-23核对）

§10启动时的collecting为历史观测，现已停止。恢复目录summary/status显示：62次请求
（61次详情响应、1次发现请求），保存61场、7场初筛通过，发现请求HTTP 400后state=failed。
与首批67/3、续采372/17合计保存500场、27场初筛通过；不是日预算耗尽或采满。
不因HTTP 400推断所有发现接口不可用。本轮只读核对，不重启采集或改变预算/来源。
所有新数据仍training_allowed=false，未加入原1990场。

DATA-05新增证据链：

- [兼容解析试点](replay-pilot-compat-results-2026-10-22.md)：原三场隔离解析及失败拒绝，不覆盖旧产物。
- [语义审计](replay-semantics-2026-10-22.md)：74,648条保留坐标来源/时钟一致；258次死亡转换获同解析器日志佐证。
- [直接实体与地标](replay-identity-2026-10-22.md)：77,370条原始坐标逐条一致，均来自主英雄；同build每场38个静态地标签名一致。两个坐标分母不同，官方底图映射未认证。
- [突跳核对](replay-jump-events-2026-10-23.md)：1,170次全部建立事件关联；238恢复区间、862核心事件、61前采样同tick、6前邻、2肉钩效果、1死亡实体移动未解释。246次恢复中9次附近买活、7次重生标志；关联不等于机制确认。

录像最近70项专项通过；本轮整批工程验收另见[交付记录](validation-and-delivery.md)。
仅限定离线取证，不生成传送/正常速度训练标签，不授予训练准入。下一步优先补同tick顺序、
传送完成/中断及死亡实体移动证据；不自动扩量，与MODEL-07独立评估决策分开。
