# 7.42地图与机制候选绑定（2026-11-27）

2026-11-27续：本页保留上一阶段来源/几何验收；后续营地、动态目标、路径视野和机制派生已另建[候选行动资产](patch-review-assets.md)。正式消费仍须逐项通过语义与游戏内验证。

当前执行入口是[计划§7](development-plan-2026-10-30.md#7-状态表唯一进度来源)。本轮使用已有Workshop导出与非留出录像做适配诊断；正式机制入口和旧复盘仍为7.41f。绑定、结构检查和几何对账不构成行动模型效果验收。

## 1. 版本身份与准入

| 资产/版本 | 已有证据 | 当前允许用途 | 不能据此推断 |
|---|---|---|---|
| 7.41f旧知识与地图 | 原有冻结来源与页面 | 既有复盘与复现 | 对7.42仍有效 |
| 7.42地图 | 本地Workshop导出，client 6989、Steam build 26825343；五文件摘要和结构复验 | 来源检查、几何诊断 | 精确字母补丁、录像6993全部几何/机制兼容 |
| 7.42机制候选 | 当前spec重建，139输入、11生产者、3输出摘要；3292行事实 | 候选复核和版本绑定 | 未决语义已认可、完整派生资产可正式消费 |
| 7.42录像 | 五场既有非留出样本，观测build 6993；固定manifest与状态通道摘要 | 本轮坐标、完整性与实体覆盖诊断 | 新训练用途或最终评估 |
| 7.42a及其他补丁 | 本轮没有相应配套验收 | 不继承7.42准入 | 因为同系列即可沿用 |

三种身份分开记录：精确补丁名、地图来源client/Steam build、录像实际build。绑定只能是`candidate`，能力只开放`source_integrity_inspection`和`geometry_diagnostic`；`action_review`和`training`始终为false。不能通过在清单里添加`verified`或把状态改为正式来绕过准入。

每个版本保留独立目录和摘要。旧版本不覆盖；新字母补丁重新登记，不自动跟随最新版。当前没有承诺按天数自动延长支持周期；支持以各消费者已经完成的验收为准。

## 2. 分层与API

| 模块 | 接口 | 职责 |
|---|---|---|
| `data.map_snapshot` | `verify_map_snapshot(root, expected_manifest_sha256=..., expected_patch_series=..., expected_client_version=...)` | 五份地图JSON、来源声明、网格、实体和兵线路径的校验；返回独立副本，`verify_again()`防漂移 |
| 同上 | `compare_map_snapshots(snapshot, older_root, expected_file_sha256=...)` | 对明确固定摘要的旧图计算差异；旧图没有manifest就明确只校验文件与结构 |
| `data.mechanics_candidate` | `verify_mechanics_candidate(root, expected_manifest_sha256=..., expected_patch=..., repository_root=...)` | 候选的输入、当前生产者、输出及改判引用；`summary()`和`verify_unchanged()`不改变正式知识 |
| `data.patch_assets` | `make_binding(...)`、`read_binding(path)`、`verify_patch_assets(spec, exact_patch=..., repository_root=..., purpose="diagnostic")` | 绑定地图和机制；精确补丁检查先于载荷读取，禁止候选进入行动复盘或训练 |
| `data.map_replay_source` | `open_geometry_source(manifest_path, expected_sha256=..., exact_patch=..., match_allowed=...)` | 只读已发布的录像格式；注入比赛排除策略，校验使用的元数据及state/extras双摘要，必须读到EOF |
| `data.map_replay_geometry` | `audit_replay_geometry(...)`、`compare_landmark_positions(...)` | 无IO的坐标和覆盖计算；不决定数据用途，也不自动判兼容 |
| `sources.map_landmark_capture`（B线） | `capture(path)` | 已验证兼容环境中捕获静态实体；只输出录像事实，不推断地图语义 |
| `scripts/capture_map_landmarks.py` | `--replay-manifest ... --manifest-sha256 ... --patch ... --compat ... --output ...` | 固定原demo与运行依赖，重新提取静态地标，独立回执且不覆盖旧解析包 |
| `data.atomic_directory` | `publish_directory(staging, destination)` | Linux原子无覆盖发布；即使目标并发出现或是符号链接也不替换 |
| `scripts/inspect_patch_assets.py` | `--spec ... --output <新目录>` | B线编排入口，注入U133排除，记录生产者与输入/输出摘要，发布前复验 |

共享data模块不导入workflow或任一产品线；B线CLI注入U133策略。新模块独立于旧冻结地图/解析生产者，不修改旧缓存或模型序列化路径。地标捕获复用原B线来源证据工具，因此登记为B线；共享地图/候选模块不反向导入它。

PR #55尚未合并，因此本分支对`replay-bundle/1`采用范围有限的诊断读取器，不复制整个采集解析实现。它检查使用的manifest、元数据、state和extras，记录原生产者，但**不重新认证完整bundle生产者、raw解析或全部质量指标**。将来接入PR #55的严格完整消费接口须单独集成验收。

## 3. 本地复现

旧候选`reports/patch-742-candidate-004`的两个生产者源码指纹已过时。本轮用已有spec新建候选，不覆盖004：

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_overlay.py \
  --spec knowledge/mechanics/reviews/v27-build-draft-001.json \
  --output reports/patch742-binding-20261127/mechanics-candidate-001
```

该目录已经存在，重跑须换新目录。`manifest.json` SHA为`1251f4ff098f4ba3458226e725c31078e278b0761efb7739e66869cf6743917c`。候选3292行中接受2582、拒绝710，另归档79；`two_ai`不提升为用户认可，`patch_verified=false`。

绑定由以下API创建，写入一个不存在的新文件：

```python
import json
from pathlib import Path
from dota_items.data.patch_assets import make_binding, verify_patch_assets

spec = make_binding(
    "data/workshop-map-742-build26825343",
    "reports/patch742-binding-20261127/mechanics-candidate-001",
    exact_patch="7.42",
    map_client_version=6989,
)
verified = verify_patch_assets(spec, exact_patch="7.42", repository_root=Path.cwd())
verified.verify_again()
with Path("reports/new-patch-binding.json").open("x", encoding="utf-8") as stream:
    json.dump(verified.binding, stream, ensure_ascii=False, indent=2)
```

检查spec采用`patch-assets-inspection/1`，字段为`exact_patch`、固定`binding`引用、`replays`的manifest路径/SHA列表、`older_map`五文件摘要和可选`landmarks`固定引用列表；`older_map`可为null，`landmarks`可为空列表。路径使用本机绝对路径。本轮已保存配置和结果于`reports/patch742-binding-20261127/`；这些真实材料不随Git分发。

```bash
PYTHONPATH=src .venv/bin/python scripts/inspect_patch_assets.py \
  --spec reports/patch742-binding-20261127/inspection-initial.json \
  --output reports/patch742-binding-20261127/inspection-new
```

诊断通道目前限每个压缩/解压文件1 GiB、每行1 MiB；这是工程读取上限，不是采样或时长口径变更。JSONL首行必须核验schema、比赛、游戏窗口及坐标语义，并计入解压摘要；仅把后续游戏内行交给纯计算模块。输出`report.json`及绑定输出SHA的`receipt.json`，现有目录拒绝覆盖。最终地图、候选、通道、引用和消费者代码复验失败时不发布报告。两个CLI共用原子发布接口；当前要求Linux `renameat2`，其他平台缺少无覆盖原语时明确拒绝发布。

## 4. 地图事实与验证边界

来源目录`data/workshop-map-742-build26825343`，manifest SHA `35ce2b5e18a20269fc4e8fbbb9d7bb0a5e4133fc9672d392400e98b1d39a0f7d`。327×327高度网格，47,964不可走格、2,394棵树、28野点、22塔、2门和6条兵线。

对比旧7.41图重算：1,968格高度变化；343格不可走变可走、984格反向；塔4处、野点5处、两座门的坐标变化；六条兵线路径均变。数量来自文件内容对账，不表示每处都已游戏内实测。

- 五份JSON有来源摘要，但原游戏文件和提取器只有声明摘要、没有全部随导出附带，本轮没有重现Workshop采集过程。
- 采样范围为世界坐标−10464到10400，真实引擎边界更大；不把裁剪网格当完整引擎边界。采样外不可走数量保留为原采集声明。
- 野点没有类型/阵营，不能按旧列表次序或最近点直接继承。区域语义和新底图尚未验收。
- 单次自定义局的Roshan/Tormentor刷新点数量不是运行时全部位置。
- 录像坐标减16384后对照世界坐标；英雄落不可走格可能涉及飞行、地形穿越等，统计不直接当作解析失败。
- state-v3建筑条目是ID/类/阵营/HP/maxHP，**不含坐标**。塔位需另行提取；extras的观察者和前哨只能做空间匹配，不认证稳定实体身份。

## 5. 完整7.42行动复盘尚缺

机制语义待裁定项见[影响清单A8](patch-7.42-impact.md)：司夜刺客钻地回蓝、米波分摊伤害和投掷视野、凯天隼冲击地形实测，以及尚未逐项确认的A1/A2/A4/A6；六条旧U47拒绝与新增IsBreakable字段冲突须核实范围。已定裁定继续沿用，不重新标为待决。

正式消费还需要对应版本的已认可机制与派生档案、保命/机动清单、营地类型和区域、新版底图，以及路径/视野/动态目标验证。上述缺口必须逐项关闭；本轮不将其布尔状态伪装为已通过，也不切`current.json`。

## 6. 本轮真实对账

可分发摘要：[验收记录](acceptance/patch-asset-binding-20261127.json)。完整本地结果为`reports/patch742-binding-20261127/inspection-final/`。五场比赛均为7.42、build6993、非留出：9103406291、9103406692、9103406760、9103407326、9103408009。

| 每场的静态类别 | 地图点/录像独立坐标数 | 严格同坐标数 | 最大最近距离（世界单位） |
|---|---|---|---|
| 塔 | 22/22 | 19 | 0.438615 |
| 营地刷新点 | 28/28 | 16 | 0.641196 |
| 双生门 | 2/2 | 0 | 0.606765 |
| 兵营 | 12/12 | 10 | 0.031250 |
| 基地、泉水 | 分别2/2 | 分别2 | 0 |
| 观察者 | 10/10 | 4 | 0.625000 |
| 前哨 | 2/2 | 2 | 0 |

五场上述结果一致。最近点覆盖与严格坐标相等分别报告；这些小偏差没有被四舍五入成完全相同，也没有设一个任意容差后宣布整图兼容。静态刷新点匹配不证明营地类型、刷新时序或视野/路径规则。

每秒通道共6,768个游戏秒、67,680个英雄本体秒；62,017个存活本体位置中无缺坐标、无越采样边界，69个最近格为不可走（约0.111%），保留为诊断，不直接判解析错误。extras的十处观察者九处严格同坐标、最大差1单位；两处前哨完全一致。该通道和新鲜静态实体提取的精度分别记录。

地标第二轮捕获五场分别92、91、91、91、91条完整坐标记录，缺坐标均为0；5–8条未映射记录仍保留，包括能力实体，不把它们臆测成地标。第一次捕获对局部vec误加`<128`限制，原结果保留在`landmarks/`并标记已被替代；修复后用原demo重跑到`landmarks-r2/`，新旧产物不覆盖。原始cell/vec和转换后的世界坐标同时保存。

检查spec中的`landmarks`每项为`{"capture": {"path": "绝对路径", "sha256": "摘要"}, "receipt": {"path": "绝对路径", "sha256": "摘要"}}`。检查器同时验证捕获输出、回执、原录像manifest身份以及回执内来源/代码文件；发布前再复验，不能将另一份同build产物混入。参考最终命令：

```bash
PYTHONPATH=src .venv/bin/python scripts/inspect_patch_assets.py \
  --spec reports/patch742-binding-20261127/inspection-final.json \
  --output reports/patch742-binding-20261127/inspection-final-new
```

初次候选与旧地图输入、正式`current.json`和原录像均保留。下一项是关闭第5节列出的正式消费缺口，而非继续把已完成的来源绑定、v4建表或文档归档重复排入下一步。
