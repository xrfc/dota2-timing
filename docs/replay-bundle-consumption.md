# 从压缩录像包生成决策复盘（2026-11-27）

[采集与单次解析流程](replay-pipeline-v2.md)已经产出 `replay-bundle/1`。本轮补上显式消费入口：先验证 bundle 并固定引用，再由带线、打野或补刀前复盘读取压缩通道。新输入不经过旧 `gank-inputs-v2` 缓存，也不将新 manifest 冒充旧格式。

这一步只接通已有工程证据与复盘页面。它不新增训练数据用途，不证明行动建议正确，也不代表 7.42 地图、机制或模型已经适配。产品口径及页面说明见[一号位兵线复盘](lane-decision-review.md)。

## 1. 分层与读取 API

| 模块/入口 | API | 职责与边界 |
|---|---|---|
| 共享 `data.replay_bundle_input` | `create_reference(root, *, match_id, expected_producer, match_allowed)` | 使用调用方给出的当前生产者与比赛排除策略复验 bundle，返回小型引用对象；不写文件、不决定产品支持的补丁 |
| 同上 | `load_reference(path)`、`validate_reference(value)` | 校验引用形状、精确补丁名、比赛 ID、绝对 bundle 路径和 manifest SHA；读取引用不等于验证比赛内容 |
| 同上 | `open_bundle_input(reference, *, match_id, allowed_patches, expected_producer, match_allowed)` | 先检查比赛/补丁策略，再验证固定 manifest、来源、生产者、全部产物和实际质量；只接受 `passed` |
| 返回的读取会话 | `normalized()`、`metadata()`、`rows("state"/"extras")` | 分别读取基础解析、绑定的元数据、去掉 header 的逐秒行；不重新解码 demo |
| 返回的读取会话 | `verify()`、`receipt()` | `verify` 必须在通道迭代完整结束后执行并重新校验；`receipt` 只返回来源说明，不能代替复验 |
| B 线 `data.replay_review_input` | `project_match(parsed, state_rows, *, source_key)` | 把已验收基础数据及单次使用的状态流投影为轨迹、可见秒点、位置推断、战斗事件和兵线前沿；纯数据转换，不读文件、不批准来源或训练 |
| `scripts/replay_pipeline.py reference` | CLI | 注入 U133 非留出策略和当前固定兼容解析器身份，把验证后的引用写到新文件 |
| `scripts/lane_decision_review.py --bundle-reference` | CLI | 复盘入口，注入精确补丁门禁，组织读取、投影、页面构建和发布前复验 |

共享读取模块不导入 workflow，也不导入 B 线的留出划分。调用方必须提供 `expected_producer` 和策略函数，不能直接拿待验 manifest 自称的 producer 充当可信期望值。实际 CLI 使用 `workflow.replay_collection.current_producer` 从当前代码及固定兼容目录计算生产者身份。接入层属于消费者，不改写已冻结 bundle 的生产者。

自定义 B 线消费者的调用顺序示意如下。`expected_producer` 和 `allowed_match` 均应来自调用方已经明确的运行配置和排除策略。

```python
from dota_items.data.replay_bundle_input import load_reference, open_bundle_input
from dota_items.data.replay_review_input import project_match

reference = load_reference(reference_path)
source = open_bundle_input(
    reference,
    match_id=match_id,
    allowed_patches=("7.41f",),
    expected_producer=expected_producer,
    match_allowed=allowed_match,
)
match = project_match(
    source.normalized(),
    source.rows("state"),
    source_key=reference,
)
receipt = source.verify()
# 调用方还须核对当前生产者、消费者及知识输入未变，之后才发布结果。
```

state/extras 可以按次流式读取，基础 normalized 仍会解压进内存；复盘也会累计轨迹、物品状态和 extras，并可能多次扫描 state。这里减少了完整未压缩磁盘副本和重新解码，不声称整个消费过程恒定内存或只读一遍通道。

## 2. 先固定引用，再生成复盘

从仓库根目录使用现有 `.venv`。下例使用已验收的非留出长局 9081264566；两个输出路径均须尚不存在。若需要再次运行，换新的 reference 文件和报告目录。

```bash
PYTHONPATH=src .venv/bin/python scripts/replay_pipeline.py reference \
  --bundle data/replay-bundles-741f-largo-20261127/jobs/9081264566/attempts/f4f07c0987914966b4339557ae4ccea3/bundle \
  --match 9081264566 \
  --output reports/replay-consumer-example/reference-9081264566.json

PYTHONPATH=src .venv/bin/python scripts/lane_decision_review.py \
  --bundle-reference reports/replay-consumer-example/reference-9081264566.json \
  --matches 9081264566 \
  --mode jungle \
  --out reports/replay-consumer-example/jungle-9081264566
```

`--mode` 可为 `lane`、`jungle` 或 `wave`。多场使用多个 `--bundle-reference`，每个请求的比赛必须恰有一份引用；缺失、重复或混入其他比赛会拒绝。`--bundle-reference` 与显式 `--root` 互斥，不会因缺少引用或读取失败而回退到旧目录。旧 `--root` 调用保留原行为，其历史数字 patch 60 检查不能解释为精确字母补丁认证。

两个入口均可用 `--compat` 明确兼容目录，默认仍是固定的 `data/replay-pilot-2026-10-22/compat-v1`。它是本地冻结资产，需要符合当前生产者校验，不能替换成任意安装的 Gem 版本。

引用格式为 `replay-bundle-reference/1`，包括 `match_id`、精确 `patch`、bundle 绝对路径、`manifest_sha256` 和 `training_allowed: false`。它不复制 demo 或解析载荷。引用是完整性锚点，不是来源真实性签名；移动文件路径或改变任何被绑定内容都需要新的明确验证，不能直接重签摘要绕过检查。

## 3. 精确版本与时间窗口

当前带线复盘的新输入路径仅支持 **`7.41f`**。选择中的全部引用先检查完比赛 ID、U133 排除和精确补丁，再打开任何 bundle 载荷。读取元数据时还要求对应比赛及数字 patch 60。数字编号不能替代 `7.41f` 身份；`7.41e`、`7.42`、`7.42a` 均不能因解析通过而进入这套 7.41f 地图/机制复盘。

通用 `reference` 可以为其他已通过质量检查的补丁创建引用，但每个消费者仍须声明自己的支持集合。本轮没有扩大复盘的版本支持，也没有切换正式地图或知识入口。

投影要求 state 按顺序完整覆盖 `0..duration`，每秒十英雄、玩家/英雄/阵营身份稳定，生命状态合法，坐标为有效二维数值或显式缺失。缺秒、重复秒、额外的赛外状态行均拒绝，不会靠补零或裁剪掩盖缺失。旧通道用于比较时，应由调用方明确按相同窗口裁剪。

战斗事件只进入比赛内窗口。可见性事件有所不同：normalized 中最多追溯到 -3600 秒的初始化信息会先参与可见区间展开，然后才把返回的可见秒点限制到 `0..duration`。如果在展开前直接删掉负秒事件，会忘记“开局前已出现、零秒仍可见”的英雄状态。保留初始化证据不等于把赛前行当成训练样本。

位置推断继续使用既有轨迹与前 15 分钟补刀信息。投影及页面材料仍包含全知复盘证据，不是已经完成阵营信息边界处理的训练表；`training_allowed` 始终为 false。

## 4. 耗尽、复验与发布

每次 `rows()` 调用都会登记一个待完成的通道读取。只有自然读到结尾、通过结束时的锚点检查才算完成；提前 `break`、从未启动迭代、提前关闭或读取报错，都不能通过之后的 `verify()`。消费者不能只读前几行就声称整份输入已完成验收。

页面构建先在新输出旁的临时目录写入。正式目录出现前，依次完成以下检查：

1. 所有通道读取已完整结束；再次核验固定 manifest、原始来源、产物双摘要和实际质量。
2. 重新计算解析生产者，与打开输入时的期望一致。
3. 重新计算消费者代码、知识、地图和页面资产指纹，与构建前一致。
4. 为已生成的页面、案例、行动及结果文件逐一计算 SHA，写入 `input-receipt.json`；确认目标目录仍不存在，再发布整个目录。

消费者身份为 `lane-review-consumer/1`。覆盖复盘脚本及其相关数据模块、投影与读取模块、间接依赖的 `unit_state` 和 `contracts/death_risk`、显示资产、地图图片与地形/树木数据，以及保命手段、地图区域、英雄机动性、装备登记和英雄能力知识。这样，同一 bundle 配上不同地图或不同规则时，输出不会只有一个相同的录像来源标签。

报告中的 `lane-review-inputs/1` 收据保留模式、每场 `replay-consumer-input/1` 来源说明、消费者身份和 `outputs` 逐文件摘要。每场说明包括引用、生产者、补丁窗口、实际 build、时长、工程用途及全知标记。`outputs` 不含收据自身，避免自引用；它绑定本次生成内容，不是数字签名。摘要校验和发布前复核发现漂移时拒绝发布；这些校验不证明知识本身正确，也不构成模型或地图效果验收。

## 5. 旧适配器指纹与本轮证据

消费当前已经复验通过的新 bundle **不需要放行旧适配器指纹**。7.41f 长局的历史 `e498fe…` 与当前 `f4bf69…` 差异已经定位到 2026-11-21 的缓存摘要加固：五份指纹源文件只有 `gem_replay.py` 改变，fresh parse 到写 manifest 的代码段逐字节相同。完整 Git 提交、五文件 SHA、AST 比较和局限见[补充溯源清单](acceptance/replay-adapter-provenance-20261127.json)。

这解释了来源指纹变化，不能认证旧运行实际使用的全部依赖或旧包。长局旧 raw 实体缺失，旧对账的 `comparison_requires_review` 保留；没有新增 producer 迁移登记，没有覆盖原报告。将来若需要复用旧包，仍须按[显式迁移规则](public-source-reader.md)另行实现，不能删除差异字段或接受任意旧 SHA。

已有真实试跑：`reports/replay-consumer-20261127/reference-9081264566.json` 固定了已验收长局的引用，`reports/replay-consumer-20261127/jungle-9081264566/` 成功生成 **31 个打野决策时刻**。该目录及当时源码作为 probe 保留；加入完整输出摘要后，最终复验另写 `reports/replay-consumer-20261127/jungle-9081264566-final/`，不得把早期试跑自动算作最终实现验收。31 个时刻证明输入接入与报告生成成功，不是行动判断准确率认证。

最终真实结果与可分发摘要见[消费链验收清单](acceptance/replay-consumer-20261127.json)：

- 精确 7.41f 长局 9081264566 从压缩包生成最终报告，用时 28.305 秒，共 31 个时刻（噬魂鬼 15、斯温 16；该场包含朗戈）。67 个输出文件的完整清单/摘要、来源收据及 156 份消费者代码/知识/资产指纹均已独立复核。
- 独立新旧投影对账用时 34.275 秒，444 个输入/源码文件前后无漂移。在显式统一到 `0..3604` 后，tracks、seen、positions、combat、fronts、last 六项严格相等，仅来源 `key` 不作内容相等比较。
- 旧读取的末秒为 3749，新末秒为 3604；旧尾部 145 秒明确排除。轨迹位置秒数从 32,626 降为 31,714、兵线秒数从 3,750 降为 3,605、英雄/阵营可见秒数从 52,864 降为 49,070，战斗事件仍为 47,658。不能宣称未裁窗的旧输出与新输出完全相同。六秒/二十秒观察窗在终局不足时的截断已加入专项回归。
- 7.42 样本 9103408009 创建来源引用成功（3.024 秒）；进入现有复盘时，在精确补丁门禁处按预期拒绝（0.124 秒），没有生成报告目录。该结果验证隔离有效，不代表 7.42 地图已可用。
- 没有重新解码原 demo、联网补采、训练或读取留出；18 份解析生产者源码与上轮保持一致。当前只对这场长局执行了完整下游真实对账，其他英雄/版本的复盘泛化尚未验证。

完整验收命令仍为 `scripts/check.py --scope all`，最终结果保存在 `reports/replay-consumer-20261127/check-final.log`；验收前后对全部跟踪文件及非忽略未跟踪文件取指纹。源码、专项和全量验收结论以本轮 PR 描述及该日志为准。严格来源保证属于 bundle 模式，旧 `--root` 模式保留历史缓存行为。
