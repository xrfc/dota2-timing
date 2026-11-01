# 位置与可见性数据扩量（2026-10-26）

## 用户目标与本轮范围

用户在本会话明确要求优先获取更多位置、可见性数据，遇到需要对齐或游戏判断的问题再交给用户；出装不再作为本轮主线。先获取离线数据，不做地图页面，不训练、不改标签/划分、不打开Dota客户端、不推送。

本轮新增数据侧脚本 `scripts/collect_replay_expansion.py`、测试 `tests/test_collect_replay_expansion.py` 和本文；不覆盖其他未提交文件、旧录像或历史报告，不更新共享环境。入口/API/命令/验收在本文集中记录，公共文档索引未修改。

## 采样与执行参数（助手的有界执行选择，非用户指定统计方案）

- 复用 `data/purchase-until-daily-2026-10-22-proxy-resume-01/matches/` 的61场缓存详情。
- 排除已解析试点3场；对剩余58场按比赛ID降序取前10场，失败不替换。
- 继承缓存来源的选择偏差与狭窄时间覆盖，不宣称代表高分段总体、当前版本或独立评估集；本轮不扩大英雄/段位口径。
- 最多10次录像HTTP请求；不请求OpenDota，不消费/重置其共享账本，不使用前瞻500场评估预算。
- 单压缩文件512 MiB、累计压缩接收2 GiB、每场解析600秒；串行执行。失败接收字节计入预算（停止时可多接收一个至多1 MiB块，超限块不落盘）。
- 网络异常、非404的HTTP失败或下载格式/预算异常停止后续请求；连续3场失败停止。404保留原候选失败，不找替补。
- 使用原公开录像URL及已有本地代理，不尝试换出口、重试或刷新过期链接。
- 导入实际使用既有隔离Gem兼容副本，校验全部副本Python哈希和导入位置，不修改site-packages。

冻结目录：`data/replay-expansion-2026-10-26-v1/`。计划含候选详情哈希、兼容清单哈希、源码哈希和来源清单；请求前落盘预留收据，每个候选有最终状态。已开始的目录禁止再次执行，不自动恢复未封存请求。

## 命令

```bash
# 新目录，冻结后不可改代码或计划冒充同一执行版本
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  scripts/collect_replay_expansion.py freeze --root data/replay-expansion-NEW
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  scripts/collect_replay_expansion.py run --root data/replay-expansion-NEW
```

脚本复用公共 `data.source_io`、现有prepare工作流和 `scripts/audit_replay_tracks.py`；不新建另一套坐标/视野解码器。`freeze()`创建独立冻结目录；`run()`拒绝覆盖execution和逐场收据。单场导出必须通过比赛ID、10人英雄身份和来源包校验。

## 文件与解释

- `plan.json` / `execution.json` / `results.json`：冻结参数、执行和全部候选结果。
- `<id>.request.json` / `<id>.receipt.json`：请求预留与成功/失败；无收据的请求不可假定未发生。
- `<id>.dem.bz2`：原压缩字节；按魔数识别bzip2/Zstandard，不根据扩展名猜测。
- `workspaces/<id>/prepared/<preparation>/`：raw、cleaned、quality、observer及manifest；全部是离线工程产物，不授予训练准入。
- `exports/<id>/trajectories.jsonl`：全知位置、游戏秒、原tick与来源引用。
- `exports/<id>/visibility.jsonl`：阵营可见性事件，保留未知及实体身份。
- `exports/<id>/audit.json`：10人覆盖、时间范围、最大间隔、清洗问题及导出哈希。

已有observer产物沿用原工作流截点，不冒充新的逐秒对齐表。隐藏/未知敌人的真实位置不得当作玩家当时可知信息。位置原生坐标没有底图校准；大位移不自动标成传送，死亡实体位置不当作行走。成功解析不等于独立游戏语义已认证。

## 验证记录

- 采集防护与既有兼容解析测试：18项通过。
- 既有导入、观察上下文与时序审计专项：32项通过。
- 新增脚本和测试Ruff/格式检查通过。
- 上述50项为专项，不是双方静止的全库验收或新增真实数据语义认证。

## 实际结果

已完成：新增10场录像，10次HTTP请求，压缩接收506,308,833字节。10场均完成原始位置/视野通道导出，8场完成清洗与时序审计，2场全量规范化导入受限。下方为最终分层结果；所有初次失败记录保留，不替换样本或重复下载。

## 原始通道独立导出补充

扩量发现有录像成功生成原始解析缓存，但全量规范化JSON超过既有256 MiB导入上限。该阶段失败不能表述为下载失败或没有坐标。本轮不修改共享workflow限制，而新增数据专属 `scripts/export_raw_replay_channels.py` 和 `tests/test_export_raw_replay_channels.py`，只读缓存中的raw-gem.json（显式512 MiB上限），绑定原录像、缓存manifest、原始JSON、候选详情与时钟实现哈希。

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=data/replay-pilot-2026-10-22/compat-v1:src \
.venv/bin/python scripts/export_raw_replay_channels.py \
  --root data/replay-expansion-2026-10-26-v1 --match-id MATCH_ID \
  --output data/replay-expansion-2026-10-26-v1/raw-channels-NEW/MATCH_ID
```

输出 `positions.raw.jsonl`、`visibility.raw.jsonl`、`manifest.json`，阶段明确为`raw_not_cleaned_or_aligned`。全部原tick、赛前/赛后及暂停期间的多条记录保留；游戏秒仅是原时钟映射，不去重、不插值、不恢复清洗隔离记录、不生成标签或训练特征。两个层级的行数不能相加：raw是原始通道，exports是其中经过现有清洗流程保留的序列。

首次原始投影有7项专项测试通过，覆盖同秒多tick保留、未知视野保留、身份/来源哈希失配拒绝、无覆盖和无训练准入。后续别名修复与实际结果见收尾记录。


## 最终交付与验收

最终原始通道目录：[`raw-channels-v2`](../data/replay-expansion-2026-10-26-v1/raw-channels-v2/)。首次v1导出及失败记录保留；原始脚本源码快照为`export_raw_replay_channels-v1.py`。当前脚本schema为`raw-replay-channel-projection/2`，增加英雄别名修正证据；不覆盖原值。v2对全部10场重新导出，**没有重新下载或重新解析录像**。

|层级|比赛数|位置行数|可见性事件数|用途/边界|
|---|---:|---:|---:|---|
|原始通道v2|10|259,697|37,956|全部原tick，未清洗/未强行对齐；暂停、赛前/赛后均保留|
|既有清洗导出|8|185,268|28,916|来源与游戏时钟核对；仍不等于独立游戏语义认证|

原始位置中：赛前8,927条，比赛范围内250,720条，赛后50条。两个层级有包含关系，不能相加作为总样本量。10场含100个比赛内玩家槽位，不是100个唯一自然人。

两场全量导入受限：9056008146（规范化JSON约284.84 MiB）、9056008092（约264.13 MiB），超过既有256 MiB入口上限。原始缓存、完整录像与原始通道均留存；这两场未执行依赖prepared格式的全量时序/坐标扰动审计，不能混称10场均已清洗验收。

### 证据与对齐结果

- 最终复核10场原始导出的manifest、文件哈希、全部消费输入及实现哈希；重新计数JSONL行数，每场10人身份通过。
- 4个比赛内玩家的原始hero_id=0，通过既有Gem目录的名称别名独立解析后与API身份交叉核对：复仇之魂2例、敌法师1例、痛苦女王1例。每行保留`hero_identity.reported_hero_id`、source_name、canonical_name及方法；目录代码和heroes.json均绑定哈希。正整数ID冲突不会被别名覆盖。
- 8场时序检查：保留坐标与来源、暂停感知时钟一致；未见时钟/来源失配或状态—视野身份失配。185,940次隐藏/未知、截点秒桶及未来坐标扰动对照通过，结论仅限所测坐标通道。
- 9056008026有4条位置记录在同一tick对应两条状态记录，均为最后一秒1959秒、tick 65380，slot 128/130/131/132；没有任意挑选一条。不是位置源引用失配，关联状态仍需单独处理。
- 暂停清洗案例9056008987：550条位置冲突中528条在暂停内、16条距边界4或6 tick、6条在末秒；442条经济冲突中440条在暂停内、2条在末秒。明细`pause-conflicts-9056008987.json`绑定输入哈希；不将冲突恢复为确定位置。
- 8场共2,056个≥1,200原生单位的位移候选：601恢复区间、1,299核心位移事件关联、72前采样同tick事件、12前邻事件、70未命中现有清单、2非存活端点。阈值只是检查设置；关联不是原因确认，未命中不等于数据错误。

### 交给用户的边界

目前没有需要用户立即决定的筛选/补值规则。72个候选（70未命中、2非存活端点）先由助手补齐事件链、排查解析与同tick问题，再把确需游戏经验的少量案例带完整上下文交给用户；不将72条原始疑点直接当作72个用户判断任务。用户判断仅作核查证据，不直接生成训练标签。

- [逐场索引与状态](../data/replay-expansion-2026-10-26-v1/handoff/matches.csv)
- [汇总与英雄别名证据](../data/replay-expansion-2026-10-26-v1/handoff/summary.json)
- [待技术筛查的位移清单](../data/replay-expansion-2026-10-26-v1/handoff/review-queue.csv)
- [八场语义审计汇总](../data/replay-expansion-2026-10-26-v1/semantic-summary.json)

### 软件收尾

最终相关专项58项通过（采集/兼容18、导入/观察/时序32、原始通道导出8），四个新增Python文件Ruff及格式检查通过。初版原始导出因严格原始hero_id检查拒绝4场，依据既有别名规则修复后新目录全部通过；新增回归确保未知名称与非零冲突仍拒绝。未做共享仓库静止的全量验收、训练、提交、推送、依赖变更或后台定时任务。
