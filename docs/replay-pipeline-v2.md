# 精确补丁采集、单次解析与压缩存储（2026-11-27）

本轮按用户要求实现[五项采集/解析建议](https://github.com/xrfc/dota2-timing/pull/54)，并回答解析结果如何节约空间。实现入口为 `scripts/replay_pipeline.py`；原冻结生产者作为回归基线保留，新产物使用 `replay-bundle/1`，不冒充旧 `demo-import/1.1`。

## 1. 分层与已实现能力

| 层 | 模块 | 职责 |
|---|---|---|
| contracts | `replay_collection` | 标准库精确补丁身份、官方快照摘要、开始/结束边界、元数据一致性 |
| sources | `replay_collection_io` | 有上限的公开请求与下载，复用匿名额度；完整 HTTP 200、长度和摘要检查 |
| sources | `replay_capture_bundle` | 固定 Gem 兼容层身份；一次解码同时输出基础、state 和 extras，后者已含小兵 |
| data | `replay_bundle` | 流式 gzip、不可覆盖的发布、压缩/原字节双摘要、来源引用、公共读取与旧文件无损归档 |
| data | `replay_quality`、`replay_bundle_quality` | 统一身份/结束/通道检查；从实际压缩产物重算质量后才接纳缓存 |
| workflow | `replay_collection`、`replay_processing` | 冻结计划、分阶段恢复、独立解析进程、资源预算与失败证据 |
| CLI | `replay_pipeline.py` | 参数及 U133 工程排除策略；核心模块不依赖脚本 |

八个新增库模块属于共享底座。CLI 属 B 线，注入既有 U133 排除策略；共享 workflow 不导入 B 线的划分模块。A/B 两线隔离、sources 不依赖 data、data 不依赖 workflow 的规则继续由架构测试强制。版本契约测试纳入三个模块 scope；最终仍做串行全量验收。

## 2. 版本、质量与恢复规则

- `--patch` 必填，支持 `7.41f`、`7.42`、`7.42a` 等精确名字。官方列表原字节、取得时间和窗口立即冻结；最新补丁上界是快照取得时间，不能推断为永远有效。数字 OpenDota patch 可另用 `--patch-code` 显式比对，实测 build 独立保存；二者都不代表模型支持。
- 发现与元数据共用 `start_lower/start_upper/end_upper`，查询就排除跨版本结束边界。沿用平均段位≥70、天梯全英雄选择、至少 900 秒、年龄 2–96 小时；年龄只作用开始时间。边界一小时是工程保守余量，不是游戏版本认证。
- `seed` 是已有本地录像的显式工程重放，不重新套用在线录像年龄筛选；仍检查官方版本窗口、段位、模式、时长、英雄和 ID。挑长局/特定英雄用于覆盖工程边界，不改变训练人口或划分。
- 真实 parser ID、元数据、标准化结果及十英雄身份必须一致；需要实际 build、开始/赛后标记、无解码异常/截断。标准化时长与元数据一致；parser 赛后秒与元数据的容差暂为 2 秒，是助手选择的工程诊断阈值，不是模型参数。
- state/extras 输出窗口为 `0..metadata.duration`，赛前/赛后秒点只记录排除数量；要求比赛内整秒齐全、十英雄齐全、核心字段有效。raw 解析与原 demo 保留，仍可重放核查排除部分。旁路只用 sink 逐秒写 gzip，不保留整场 state/extras 列表。
- 失败、`review_required`、`passed` 分开。质量状态不能只看字符串：读取缓存时重新核对来源/生产者、全部文件集合和双摘要，并从压缩数据重算覆盖/字段质量。把失败状态改成成功或联合重签坏通道摘要仍不能通过检查。
- 下载、解析、校验可分别执行。完成下载按 SHA 复用，解析失败保留原归档、日志及未完成 attempt；`--retry-failed` 才在新 attempt 重建。旧坏缓存会记录拒绝原因，不阻挡检查后面的有效 attempt，不覆盖旧目录。
- `--max-attempts` 限定本轮访问的比赛数（缓存核验也计入），另有下载落盘字节预算，成功文件及失败 `.partial` 均计入。总时限在阶段边界检查，网络分块检查余时，单次解析子进程超时至多 900 秒；本地哈希和缓存重验不受硬总时限中断，实际结束时间可能超过总预算。每次解析前检查 30 GiB 预留。没有后台无限等待或自动改路由。429 的共享冷却保持有效。
- HTTP 206/Content-Range、错误长度、编码/重定向或半文件不会发布成成功下载。当前按阶段续跑；中断下载另建 attempt，不做未经 ETag/Range 身份确认的追加。

## 3. 空间怎么省

上一批五场隔离试采占用 **3,416,902,284 字节（3.18 GiB）**，其中 `work/` 占 94.9%。已确认逐字节相同的重复部分为 1,234,465,821 字节；唯一 normalized JSON 共 537,104,679 字节，已有 gzip 只占 15,511,412 字节（缩小 97.1%）。首要问题是多份未压缩工作副本。

新流程采用三项措施：

1. 原 demo 保持原来的压缩格式，manifest 引用原路径和 SHA，同一录像重放不再复制归档。
2. 每个 bundle 只存 `raw-gem.json.gz`、`normalized.json.gz`、`state-v3.jsonl.gz`、`extras-v1.jsonl.gz` 与小型 manifest；不再经完整 `prepare` 创建 raw/prepared/input/cleaned 多份 JSON。state/extras 写压缩临时流，正式输出发布后仅清理本次临时流。
3. gzip 固定时间戳，边编码边压缩，64 KiB 缓冲合并小 JSON token；每件产物同时保存压缩 SHA、解压后 SHA 和长度。manifest 最后发布。`raw` 用旧 JSON 语义保留证据；Gem 的字符串/整数枚举在树内转成普通值，不制造整场 JSON 字符串再反解析。

这不是降低采样率或减少数值精度。基础 Gem 提取器仍在内存累计事件，所以不能声称整个解析过程是恒定内存；节省来自减少副本和旁路列表。gzip 可复用已有环境/读取器；当前不为容量问题引入未安装的 Parquet/Arrow。将来如主要需求变成按列扫描特征表，再单独评估列式存储及语义迁移。

`pack` 可以把明确列出的旧文件无损压缩到新目录，保留每个源文件原字节摘要。它只证明无损归档，不认证所给文件的比赛身份、解析质量或旧生产者；不会自动纳入新质量通过集合。旧文件和失败 attempt 均未自动删除，因此“新格式更小”不等于已经释放旧目录空间。清理冻结旧产物需先有可逆归档与消费者迁移证据，再按用户规则另行处理。

## 4. 命令

均从仓库根目录执行，复用 `.venv`。新 worker 自动为子进程设置固定 compat 路径，核验 190 份源码、manifest 与实际导入位置；不接受缺失后回退到原版 Gem。

```bash
# 有上限的精确版本发现；候选工程用途、排除 U133 留出
PYTHONPATH=src .venv/bin/python scripts/replay_pipeline.py discover \
  --root data/my-742-run --patch 7.42 --patch-code 61 \
  --max-candidates 8 --max-pages 6 --max-metadata 12 --max-seconds 300

# 同一冻结计划分别下载、解析、验收；也可 --stage all
PYTHONPATH=src .venv/bin/python scripts/replay_pipeline.py run \
  --root data/my-742-run --stage download --target 5 --max-attempts 8
PYTHONPATH=src .venv/bin/python scripts/replay_pipeline.py run \
  --root data/my-742-run --stage parse --target 5 --max-attempts 8
PYTHONPATH=src .venv/bin/python scripts/replay_pipeline.py run \
  --root data/my-742-run --stage verify --target 5 --max-attempts 8

# 只读空间盘点，不打开比赛内容
PYTHONPATH=src .venv/bin/python scripts/replay_pipeline.py space --root data/my-742-run
```

在线窗口会过期；历史重放应使用 `seed --snapshot <官方原字节> --retrieved-at <带时区的取得时间> --selection <JSON列表> --patch <精确名字> --patch-code <可选数字> --root <新目录>`。selection 每条含 `match_id/start_time/duration/avg_rank_tier/metadata_path/demo_path`，最后一项可省略以单独验证下载。重复发现必须另建目录，不改冻结计划。

旧文件归档：`pack --match <非留出ID> --files <JSON对象 role→源路径> --output <新目录>`。恢复原字节可用标准 gzip 解压，并与 descriptor 的 `uncompressed_sha256` 对比；`verify_bundle(..., verify_references=True)` 默认还检查源文件，纯归档离线校验可显式设为 false，但不能据此批准解析缓存。

消费新 bundle 使用 `data.replay_bundle.read_json_artifact` / `iter_channel`；正式接纳先调用 `data.replay_bundle_quality.verify_quality_bundle` 并提供当前期望身份和生产者。JSONL 含真实比赛 ID、精确行数及游戏内窗口。旧消费者不会自动把新 manifest 当作旧产物。

## 5. 真实回归与限制

原始日志与数据保存在忽略的 `reports/replay-pipeline-20261127/`、本轮 `data/replay-*20261127/`；可分发的摘要见[真实验收清单](acceptance/replay-pipeline-20261127.json)。

| 精确版本 | 比赛 | 时长（秒） | 实测 build | 游戏内 state/extras 各自秒数 | 含 manifest 的 bundle 字节 | 质量 |
|---|---:|---:|---:|---:|---:|---|
| 7.42 | 9103408009 | 1373 | 6993 | 1374 | 10,848,698 | passed |
| 7.42 | 9103407326 | 1272 | 6993 | 1273 | 11,055,584 | passed |
| 7.42 | 9103406760 | 1156 | 6993 | 1157 | 8,026,810 | passed |
| 7.42 | 9103406692 | 1444 | 6993 | 1445 | 11,336,820 | passed |
| 7.42 | 9103406291 | 1518 | 6993 | 1519 | 12,087,643 | passed |
| 7.41f，含朗戈 | 9081264566 | 3604 | 6972 | 3605 | 29,944,296 | passed |

六场均先确认不属于 U133 留出。五场 7.42 串行处理及质量复验用时 289.573 秒，长局用时 155.725 秒。五场旁路合计保留 6,768 个整秒，排除 728 个赛前/赛后秒点；长局保留 3,605、排除 145。游戏内每秒十英雄齐全；raw 保留完整证据，normalized 沿用旧 context 规则（包括初始化可见性），不把基础证据包当成批准的训练表。

五场新 bundle 合计 **53,355,555 字节（50.9 MiB）**，加上同一批原压缩 demo **136,502,886 字节**，为 **189,858,441 字节（181.1 MiB）**。与旧试采整个根目录的 3.18 GiB 相比少 **94.44%**。这是逻辑文件字节对比：新值计最终 bundle 与原录像，未计轻量计划/元数据、日志、保留的失败/旧 attempt；没有声称已经释放旧目录空间。

收益主要来自取消工作副本，并非每件 gzip 都更小。只比较双方原本已有的 normalized＋state，五场从 36,508,261 变成 40,443,666 字节（增 10.78%）：normalized 从 15,511,412 降至 12,643,682，state 从 20,996,849 增至 27,799,984。新写入器采用 gzip level 6，JSONL 编码写法也不同；逐行内容已对账，压缩参数仍可独立优化。不能将完整 bundle 与只含两个角色的旧压缩目录混比。

对 9103407326 单场 state 另做只读重压基准：当前 gzip6 为 5,585,976 字节，重压 0.69 秒；保持原字节改 gzip9 为 5,172,892 字节、2.11 秒；去掉 JSON 分隔符空白再用 gzip9 为 5,010,402 字节、2.05 秒（少 10.30%）。1,274 行含 header 均语义相同；纯重压两组原字节也相同。时间为单次读入/编码/写盘，不是整局解析时间。当前默认仍为 level 6，基准仅为后续压缩取舍证据，未回写已验收 bundle；记录在 `reports/replay-pipeline-20261127/state-storage-9103407326/report.json`。

真实 CDN 下载另用新目录重取比赛 9103408009，26,808,790 字节及 SHA-256 与原归档完全相同。首轮实跑曾暴露字符串枚举未转成普通 JSON 值，已修复并保留失败证据；最终六场由同一份 18 模块源码指纹产出，早期试跑不混入最终验收。

独立对账耗时 42.595 秒，419 个输入/源码文件前后摘要无漂移。五场 7.42 的 raw 解压后与旧 raw 逐字节相同；normalized 严格比较仅排除 `evidence_source/evidence_sha256` 两个来源字段，其余全等；6,768 条游戏内 v3 行逐行全等。7.41f 的 3,605 条 v3 行也全等，但 normalized 还存在旧 `adapter_fingerprint` 与当前值不同，因此报告保留 `comparison_requires_review`，不认定旧生产者已认证或可以迁移复用。长局旧 raw 实体已不在现有目录，只有旧 normalized 声明的摘要与新 raw 相同，不能声称完成旧原文件字节复核。六场均无旧 extras 对照文件，新 extras 已通过当前质量检查，跨实现语义对照仍未覆盖。

再次执行 `--stage verify`：五场在 15.037 秒、长局在 8.868 秒内从实际压缩数据复验通过；attempt 数分别保持 7→7（含早期两次试跑）、1→1，没有重新解码。旧试跑因生产者不同被拒绝；异常缓存不会阻止继续检查有效 attempt。日志区分固定校验原因、HTTP 状态、超时与退出码，不写 HTTP 请求地址或子进程输出。

全库收尾使用 `PYTHONPATH=src .venv/bin/python scripts/check.py --scope all`，最终日志为 `reports/replay-pipeline-20261127/check-final.log`；验收前后另核对跟踪文件及未跟踪源码指纹。专项覆盖跨字母补丁、畸形元数据、HTTP 半文件、损坏/伪造缓存、截断/缺失秒、生产者变化、失败重试和一次解析多通道。异常录像目前以合成故障注入验证，真实损坏文件与新出现的可选英雄尚未覆盖。

本地 11-06 与 11-19 的 Valve 英雄快照均有 127 位，ID 集合一致。朗戈（155）与凯（145）在旧快照已存在，作为高编号/复杂状态覆盖，不能称为 7.42 新英雄；7.42 notes 多出的熊灵条目也不是新增可选英雄。

本轮尝试发现一场 7.42a 长局含朗戈的录像，OpenDota anchor 返回 `400 {"err":"AggregateError"}`；同路由一次诊断相同，已停止。官方快照、窗口、事件和诊断记录均保存；服务失败不等于候选不存在或补丁不支持。

解析库继续使用固定兼容版本。新 pipeline 的跨版本回归不等于新 Gem 版本或地图已经验收；地图/视野、逐技能字段含义和真实模型效果仍须各自的证据。本轮不升级依赖、不训练、不读留出，不更改正式机制和地图入口。
