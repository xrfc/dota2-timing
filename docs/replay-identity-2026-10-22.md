# 录像坐标直接实体来源与原生地标（2026-10-22）

接续[三场语义审计](replay-semantics-2026-10-22.md)。用户要求继续开发，本轮完成其建议的直接实体来源检查和录像内地标取证。只使用同三份本地压缩录像，隔离重解析；无下载、扩量、训练、标签/划分变更或客户端操作。

## 结果

**三场77,370条原始坐标与旧输出逐条一致，全部直接取自主英雄实体；同build的38个静态地标签名也完全一致。** 这补齐三场位置采样缺少直接实体身份的证据，不是独立游戏真值认证或训练准入。

| 比赛ID | 原始坐标（本轮全量对照） | 清洗后保留坐标（上轮） | 非主英雄采样 | 静态地标签名 | replay build |
|---|---:|---:|---:|---:|---:|
|9056009571|31,400|30,495|0|38|6965|
|9056009136|25,670|24,760|0|38|6965|
|9056009130|20,300|19,393|0|38|6965|
|合计|77,370|74,648|0|每场38|均6965|

两个坐标分母不同：原始序列包括赛前、超出duration和被清洗隔离的记录；本轮不把它们重新纳入可用轨迹。上轮与本轮消费的raw哈希逐场一致，见`semantic-link.json`。

30名玩家各只观察到一组实体index/serial。本轮覆盖的采样点没有主英雄缺失回退，不能宣称真实回退、实体复用、幻象/分身所有边界已经验收；实体复用和主实体缺失仅有合成回归。

## 实体取证方法和边界

1. 校验本地录像的下载回执哈希、冻结raw/manifest和兼容Gem全体Python文件的清单与哈希。
2. 将已冻结兼容副本复制到本轮各场私有目录，仅在`PlayerExtractor._sample`完成实体选择、调用`_build_hero_snapshot(entity, tick, player_id)`后插入取证调用。不修改选择算法、坐标公式、安装包或旧捕获实现。
3. 从**实际传给采样函数的entity**保存index/serial、class、team、原始player ID字段、生命状态和cell/vec分量；另记录该实体是否与该玩家canonical hero的index/serial一致。缺失值保留None，不代入0。
4. 使用现有`prepared_demo`解压入口，在独立进程重解析。只附加玩家与地标提取，不重跑模型/特征工程。解析器报告截断或错误则拒绝成功结果。
5. 按每个玩家完整有序序列逐条匹配`tick,x,y`和英雄名，验证`cell*128+vec`。保留重复tick顺序，不能去重后碰巧一致。每条结果连接旧raw引用与新capture引用。
6. 发布前再次核对输入和关键实现、私有Gem源码哈希；`execution.json`、`capture.json`、`audit.json`及receipt记录证据链。输出已存在则拒绝覆盖。

`canonical_for_slot`是Gem当前主英雄句柄的内部判定，不是另一解析器的独立认定。它解决“实际坐标用了哪个实体”这一局部问题，不证明Gem的玩家绑定、协议解码或所有机制必然正确。当前比对范围是坐标与身份，不是对全部经济、装备或战斗事件的重新认证。

## 地标证据：同录像、同build，不冒充官方底图

助手选择四类静态实体作为本轮检查范围：22座塔、12座兵营、2个遗迹、2座泉水，共38个签名/场。签名为`class + team + native_x + native_y`，**跨场不使用实体index/serial连接**。三场签名完全相同。

| 地标 | Radiant原生坐标 | Dire原生坐标 |
|---|---|---|
|遗迹实体|10464, 11032|21912, 21384|
|泉水实体|8928, 9446|23792, 23232|

捕获入口使用类名关键词收集候选，另外保留了XP泉水、观察者和能力实体：三场候选记录分别46、45、45条。报告的38个静态签名只取上述四个精确类名及非缺失坐标；候选记录不删除。能力实体坐标缺失不补0；观察者阵营变化不视为固定阵营地标。

地标NPC名称在本次读取的字符串表字段中未解析出来，保留null。因此不能从这些证据单独给每座塔贴上“T1上路”等标签；图中只标实体类别和阵营。`first_tick/last_tick`是该记录被观察到的边界，不等于出生/死亡时间或连续存活证明。

三场录像解析出的build均为6965。旧冻结API详情中的`patch=60`只作为该来源的原始字段，不在此推断官方补丁名称；没有补丁发布边界/地图资源的独立对应证明。**“同build录像内地标一致”不等于“已对齐某官方补丁底图”。**

冻结Gem的`extractors/lane.py`文档引用旧报告画布的泉水投影锚点：Radiant `(9684,9684)`、Dire `(23120,22350)`。这些值与本次泉水实体坐标不同，但两者可能本就表达不同投影/锚点，不能仅据此宣布上游坐标错误。当前不复用其路区分类、不减16384、不缩放套图。备选路径是补充可追溯的同build地图资源或独立解析器地标，再验证变换，而不是调整数字使图看起来合理。

## 可用清单更新

| 能力 | 本轮状态 | 限制 |
|---|---|---|
|原始位置直接实体身份|三场77,370条采样取证与旧序列一致|同解析器内部证据；真实回退/复用未覆盖|
|清洗后轨迹关联|与上轮相同raw哈希，新增全原始序列身份链接|不恢复隔离记录，不扩大时间覆盖|
|录像原生静态地标|三场同build、每场38个签名一致|非官方底图对齐，塔/兵营具体路区名称未确认|
|地图原点、朝向、缩放、路线标签|未认证|不自动生成路区特征|
|位移/复活机制|仍待解释|上轮1,170个突跳不自动标成传送或错误|
|视野、真实暂停、训练准入|沿用上轮限制|本轮不改变用途或训练授权|

## 文件、API与复现

新增数据侧文件：

- `src/dota_items/sources/replay_identity.py`：实际实体取证与隔离解析；sources不依赖data。
- `src/dota_items/data/replay_identity.py`：`compare_positions(raw, captured)`纯比较，`native_position(row)`保留未知。
- `scripts/audit_replay_identity.py`：哈希核验、私有副本取证、离线重解析CLI。
- `scripts/report_replay_identity.py`：验证audit/capture哈希，汇总静态签名并生成原生坐标SVG。
- `tests/test_replay_identity.py`：15项新专项测试。

产物根目录：[`data/replay-identity-2026-10-22-v1/`](../data/replay-identity-2026-10-22-v1/)。每场保留私有取证源码、执行指纹、capture、逐条链接audit和完成回执；旧录像/旧解析不覆盖，解压临时文件由已有入口自动清理。`summary/summary.json`记录跨场地标对照；不等于完整bundle验收。

原生地标示意图：[9056009571](../data/replay-identity-2026-10-22-v1/summary/9056009571.svg) · [9056009136](../data/replay-identity-2026-10-22-v1/summary/9056009136.svg) · [9056009130](../data/replay-identity-2026-10-22-v1/summary/9056009130.svg)。SVG已通过XML结构检查，未做浏览器视觉验收。图中y向上是展示约定，不是独立朝向认证；悬浮标题包含实体身份与capture引用。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/audit_replay_identity.py \
  --archive data/replay-pilot-2026-10-22/advertised-http/9056009571.dem.bz2 \
  --receipt data/replay-pilot-2026-10-22/advertised-http/9056009571.receipt.json \
  --preparation data/replay-pilot-2026-10-22/compat-results-v1/workspaces/9056009571/prepared/8abca33c331d71738f31efb7 \
  --compat data/replay-pilot-2026-10-22/compat-v1 \
  --output data/replay-identity-new/9056009571

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/report_replay_identity.py \
  --audits data/replay-identity-new/9056009571/audit.json \
  --output data/replay-identity-new/summary
```

## 验证与协作边界

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_replay_identity.py tests/test_replay_semantics.py tests/test_replay_compat.py \
  tests/test_replay_ingestion.py tests/test_observer_context.py -q
```

实测53项通过；新增15项覆盖坐标/时钟/英雄篡改、计数缺失、重复tick、实体serial复用、非主实体不被主实体替换、未知坐标、重复插桩拒绝、错比赛、录像哈希拒绝和旧输出保护。五个新增Python文件的ruff与格式检查通过。开发期间首次lint有导入排序/长行问题，已修正；首次技能参考路径不存在，改为当前实际路径读取，不将其误判为技能缺失。

只新增本轮数据专属文件与独立报告，未改已有未提交文件、共享接口、共享索引或check注册。未组织双方暂停写入的全库验收，53项仅为专项结果。未安装依赖、切分支、提交或推送。

## 下一步

在现有三场内优先解释位移与复活候选：选取可追溯突跳，核对技能/物品使用、死亡、买活或重生事件的覆盖与歧义，不根据距离阈值直接造标签。另需独立地图资源证据才能升级“原生地标”为“官方底图映射”。不因本轮通过而自动扩量或训练。
