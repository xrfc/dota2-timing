# 模型基础闭环（2026-10-16）

2026-10-20：新增[版本化任务契约](task-contracts.md)。`adapt_snapshot` 接受 /1、/2，
新 /2 模型强制携带完整契约及实现指纹；`load_model`、`predict_lineup` 增加可选
`expected_task_contract`。旧 /1 仍可读，但不能通过新契约范围检查。
inspect 与 /2 预测展示任务契约；默认参数、标签语义和真实训练授权不变。

## 离线评估输入契约 — 2026-10-18续接

依据维护指南的独立evaluation职责，完善现有指标/整玩家组bootstrap的输入校验；不是新研究方案或真实效果评估。
API仍为metrics(y, p)、group_draws(groups, repeats, seed)、paired_intervals(y, baseline, linear, groups, repeats=500, seed=20261015)。

- y为已观测的一维0/1数值，概率为同长度一维有限[0,1]数值；拒绝bool、文本、None、NaN/Inf、复数及二维输入。
- 不接受MaskedArray，防止np.asarray悄悄丢弃mask。调用者须按每个目标的既有mask同步筛选y、两组概率和group；未知不填0。
- groups只接受同类型整数ID或非空字符串ID；拒绝浮点、bool、混合类型、未知身份和空白ID，不能据此推断现实身份独立。
- repeats为正整数，seed为非负整数；空数据也先校验参数。空metrics保留null指标，空paired_intervals保留0个有效重复/null区间，空group_draws不产生抽样。
- 列表及NumPy数组均可用；不修改输入。大整数ID保持精确，整组有放回抽样保留重复副本和全部组内行。
- 固定原95%百分位区间及linear-baseline差值方向：AP/AUC增大通常更好，Brier减小更好。单类别的AUC、无正例的AP仍为null；valid_replicates按指标分别计数。
- 合法历史数值结果用合成parity回归约束，冻结purchase_baseline不修改；不自动选split、模型、阈值或真实数据。
- evaluation不属于当前训练制品实现清单，本轮不改模型schema、训练参数、数据来源或旧哈希。

合成测试命令：
~~~bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_model_evaluation.py tests/test_modular_maintenance.py
~~~
这些校验只能识别结构/数值错误，不能识别同长度但错序的数据或认证研究许可；调用者仍须保证行对齐和数据用途。

## 模块化更新 — 2026-10-17

语义仍以本页为准，结构见[维护指南](modular-maintenance.md)。输入适配在batch，固定任务/特征在specs，拟合在training/estimators，制品在artifacts，预测在inference；foundation兼容旧API。
加载/预测不导入sklearn，拟合逻辑回归才加载训练实现。新制品指纹按provenance.IMPLEMENTATION_FILES覆盖模块化清单；兼容历史四文件清单及无清单制品。
下方“四文件指纹”和“仅改foundation”是旧轮次记录，不能当当前实现清单。任务、参数、mask和test隔离语义不变。
频率/逻辑回归新旧参数和18条合成预测均逐字节一致，不是实际模型效果证据。

## 只读制品检查 — 2026-10-18

新增 `modeling.inspection.inspect_model(path)`，直接复用 `artifacts.load_model` 的严格校验，
返回可JSON序列化的摘要；CLI `inspect --model PATH` 默认仅向stdout打印JSON。
与 `predict` 不同，它不需要阵容，不计算概率，也不读取训练快照、原始数据或当前源码；
不调用拟合、选模、评估或自动修复。demo/predict原有行为保持不变。

```python
from dota_items.modeling.inspection import inspect_model

summary = inspect_model("/path/to/saved-model.json")
print(summary["targets"])
```

以下命令在项目根目录运行，第一条需将路径替换成已有模型；后两条仅生成独立合成示例：

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/model_foundation.py inspect --model /path/to/saved-model.json
MODEL_TMP=$(mktemp -d /tmp/dota-model-inspection-XXXXXX)
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1
.venv/bin/python scripts/model_foundation.py demo --family frequency --output "$MODEL_TMP/frequency.json"
.venv/bin/python scripts/model_foundation.py inspect --model "$MODEL_TMP/frequency.json"
```

摘要包含schema/family、任务、synthetic、词表大小/特征维度/fit_split、训练参数、
逐目标trained/untrained及原因、source_sha256、代码revision、Python和依赖版本。
支持数中 `negative=observed-positive`、`total=observed+unknown`：
观测比例的分母是observed，不可将unknown当负例；single_class表示观测仅一类，
no_observations表示全未知。trained只表示已拟合，并不证明效果或可部署。
这让学习者先理解任务、缺失标签和训练分母，再看预测；不输出全部系数、截距或原始训练样本。

实现指纹覆盖分类为 `legacy_no_bundle`（仅旧foundation指纹，计数1，清单/bundle为null）、
`historical_four_files`（历史四文件）或 `modular_manifest`（现有模块化清单）。
输出记录的文件哈希和bundle摘要；`current_source_verified=false`明确没有核对当前源码。
检查器本身不加入历史训练实现清单，不修改制品schema或协议。
哈希只检查身份/内部一致性，不认证来源；记录版本也不是环境锁。
摘要固定提醒：源日志未记录不等于真实未购买，不能当最优出装、效果证据或训练许可。

未知schema、错误checksum、损坏类型/指纹继续严格拒绝，API抛原加载异常、CLI非零退出，
不创建或修改输入文件。通过独立子进程阻断sklearn、numpy、数据侧、batch、training、
inference和合成生成器导入检查API及CLI；检查路径不需要NumPy或训练库，
但这不等于提供了单独的检查器安装发行包。合成制品生成/旧predict仍使用现有环境。

专项测试入口（独立临时目录、禁止缓存写入）：

```bash
MODEL_TMP=$(mktemp -d /tmp/dota-model-inspection-XXXXXX)
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp "$MODEL_TMP/pytest" tests/test_model_inspection.py tests/test_model_foundation.py tests/test_model_foundation_validation.py
```

新增测试覆盖合成频率/逻辑制品、单类别/全未知/部分未知支持数、三代记录指纹、
损坏制品与CLI非零、输入前后字节不变及依赖隔离；不对真实模型预测或评估。
共享测试scope登记及最终全量验收由协调者串行处理，本侧不修改check.py。

## 范围与决定归属

当前唯一目录为 `dota2-timing`，data/modeling 并列；复用已有 `.venv`。
本轮只做工程修复与合成回归，不进行旧952场真实训练、截距对照、选模，
不赋予新增1,038场研究用途，不重划分、不读取旧test用于选模、不改数据侧或冻结证据。
已有历史基线不是从零开始；没有整体胜过频率的证据。真实实验仍需用户明确确认。

## 最小接口与输入边界

- `foundation.adapt_snapshot(snapshot, split)` 兼容 `purchase-log-modeling-snapshot/1`，
  返回独立 X/y/mask、split、审计元数据。默认 train，可显式 validation；test 适配始终拒绝。
- 检查 schema、modeling_ready、任务、固定五装备顺序和整型端点半开窗口 `[0,1800)`。
  不接受用 bool/float 冒充 ID、窗口端点或二进制标签；端点1800不包含在内。
- 五装备顺序固定为 bfury、maelstrom、manta、black_king_bar、skadi。
  1/0仅表示合法源日志出现/未记录，不是实际购买完整真值。
- 先读各行 split 分派，再检查所选集合的载荷；其他集合特征/标签保持不透明。
  split清单仍必须完整、比赛ID为正整数且无重复/交叉，所选行须与清单一致；空集合拒绝。
- 词表必须为排序、唯一、正整数，包含目标英雄8，且 `fit_split=train`。
  train适配时重新核对词表等于train阵容拟合结果，不从validation/test补英雄。
  维度为 `2×(词表大小+1)`，不硬编码254；列序必须等于共享 `contracts.lineup.columns`。
- 友方五英雄含主宰(8)，敌方五英雄，十英雄唯一；拒绝bool/缺人/重复/错误目标。
  词表外英雄按两侧unknown_count计数，预测不扩充词表；不声称通过官方英雄目录认证。
- X仅来自通过共享 `contracts.lineup.encode_lineup` 重算核对的encoded_features。
  match_id、group_id、role_hint、source_sha256、账号、原购买字段均不进X。
- 标签未知必须为 `null` 且 `mask=false`；内部以NaN保留，拟合逐装备排除，不能填0。
  直接传入Batch也检查维度、数值类型、有限性、binary/multi-hot值域、阵容计数和mask/NaN一致性；
  train编码不能留下unknown_count或未在train出现的词表列。
- `fit_model` 仅接收train Batch，不自动选模或读验证/测试；单类别/全未知目标不拟合，
  返回 `untrained` 和原因，预测为null。它不是不可伪造的训练授权令牌。

适配器检查结构/一致性，不认证真实来源、跨集合玩家身份或研究授权，不重建/重划分数据。
validation适配复用已冻结词表，不为检查词表而读取train载荷；train词表核验发生在train适配。
显式合成标记若存在须为bool；旧快照未提供标记时继续按非合成处理，标记不是真实性证明。

## 模型选型（实现选择，不是新研究结论）

| 模型 | 优点 | 当前限制与决定 |
|---|---|---|
| 训练频率 | 最低复杂度，衡量阵容是否提供增益 | 不看阵容，保留正式对照；单类别目标仍不输出概率 |
| 逐装备逻辑回归 | 小样本低容量、权重可解释、现有实现可复用 | 不直接表达英雄交互，先提供统一接口 |
| 树/提升树 | 可表达非线性交互 | 少数正例和高维输入易过拟合，暂作备选 |
| 小型MLP/Embedding | 可学习表示和交互，便于后续DL学习 | 样本数不等于独立玩家组数，暂不引入框架 |

合成演示逻辑回归默认C=1、liblinear、max_iter=2000、random_state=0、无class_weight。
这些是演示参数，不是最优参数；接口继续支持原C网格0.01/0.1/1/10与liblinear/lbfgs，
不改变已有敏感性实验的九候选或选择规则。收敛警告视为失败，不回退到频率或静默重训。
逐装备sigmoid不是softmax，概率不必加总为1；频率是训练观测比例。
真正对比仍须报告逐装备AP/Brier、正负/未知分母及整玩家组不确定性；本轮不产出效果指标。

## JSON制品、失败行为与旧版兼容

制品为 `purchase-foundation-model/1`，不使用pickle或反序列化sklearn对象。
保存固定参数、任务、五目标状态/支持数、词表/列序、系数/截距、输入SHA-256、代码revision、
Python/numpy/scikit-learn版本；synthetic标记在保存、加载、独立预测中持续展示。

外层checksum核对文件内容身份，不是数字签名。加载同时检查schema、任务/列序、
参数类型/允许值、每目标支持数及共同训练分母、single_class/no_observations原因、
frequency与支持数比例、系数维度和严格有限数值。字符串/布尔系数、过宽松舍入匹配、
untrained/频率目标夹带无效权重、非有限元数据、重复JSON键均拒绝。
可传 `expected_preprocessing` 做外部特征兼容检查。
有限权重若在实际阵容上产生溢出/非有限score，预测明确失败，不输出NaN或掩盖为正常结果。

缺文件保留FileNotFoundError；非法JSON/结构/校验和/语义返回ValueError。
保存拒绝覆盖，且先验证后创建文件；加载失败不创建/修复/重训任何制品，CLI失败返回非零。
制品记录依赖版本但不因版本差异自动重训；版本记录不等于完整环境锁。

### 实现指纹的兼容扩展

历史 `provenance.implementation_sha256` 只包含foundation.py，不覆盖后来下沉的阵容编码。
现在保留该字段（仍是foundation.py哈希），并增加可选成对扩展：

- `implementation_files_sha256`：foundation.py、contracts/lineup.py、
  modeling/purchase_baseline.py（C网格）、storage.py（规范JSON/摘要）的逐文件SHA-256。
- `implementation_bundle_sha256`：上述映射的规范JSON摘要。

路径是稳定的源文件逻辑名称，实际文件从已导入包位置读取，不依赖另一个worktree。
输入数据内容由source_sha256另行记录；依赖以版本记录。
两新字段均缺失时按旧 `/1` 制品加载，不伪造新编码指纹；只缺一个、文件清单不符或内部摘要
失配时拒绝。加载不要求历史指纹等于当前源码，因此保留旧JSON公式推理兼容，不声称旧代码
与当前实现已完全相同。若将来编码语义改变，必须显式发布相应接口/制品版本，不能仅靠哈希兼容。

本轮只读加载现存历史合成 `reports/model-worktree-preserved-2026-10-16/model-foundation/logistic-final.json`
成功（无新扩展字段，synthetic=true、BKB=null），加载前后SHA-256相同；另有合成回归覆盖旧字段
兼容与不完整/被篡改新扩展拒绝。不覆盖历史制品。

## 现有环境可运行命令

在唯一项目根目录执行；不创建venv、不安装依赖。已实查当前环境Python 3.12.3、
numpy 2.5.4、scikit-learn 1.9.1。每次使用新的独立临时目录，避免共享缓存/冻结产物写入：

```bash
MODEL_TMP=$(mktemp -d /tmp/dota-model-foundation-XXXXXX)
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1
.venv/bin/python scripts/model_foundation.py demo --family frequency --output "$MODEL_TMP/frequency.json"
.venv/bin/python scripts/model_foundation.py demo --family logistic --output "$MODEL_TMP/logistic.json"
.venv/bin/python scripts/model_foundation.py predict --model "$MODEL_TMP/logistic.json" --lineup examples/model-foundation-lineup.json
.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp "$MODEL_TMP/pytest" tests/test_model_foundation.py tests/test_model_foundation_validation.py
```

CLI没有真实数据训练入口，不调用包含旧测试评估的run_experiment。
合成演示12训练/4验证/2测试行，11英雄词表、24列；只拟合12训练行。
频率四个已训练目标均0.5、BKB=null；输出synthetic=true、performance_evidence=false。
逻辑回归概率随阵容变化，但标签人为构造，不是真实效果证据。

**历史说明（不执行）**：原模型worktree文档中的 `python3 -m venv .venv`、
`pip install -e ".[data,dev]"`、ensurepip缺失后定向安装及Windows独立解释器步骤，
均为迁移前环境准备记录，不是当前命令。旧worktree已移除，禁止照旧路径重建或覆盖共享环境。

## 本轮专项验证与交接

本轮仅修改foundation.py，新增tests/test_model_foundation_validation.py并更新本文；
原合成生成器、CLI、样例和原25项模型测试直接复用，没有另造框架。
新增回归覆盖畸形结构/类型、split污染隔离、词表只训练拟合、未知英雄、metadata不进X、
直接Batch旁路、mask/null、制品语义/重复键/校验和、旧版指纹兼容、保存拒绝覆盖、
单类别/全未知、两solver与四个既有C值、收敛失败，以及频率/逻辑回归训练→保存→加载→
独立命令预测一致性。异常CLI不写回或修复制品。
专项132项及模型导入/依赖边界2项通过；仅本轮模型文件运行Ruff/格式检查。全库验收由父会话在双方停写后串行执行，
不把专项通过或旧425/454项历史结果写成当前全库保证。

真实数据交接继续使用现有task/preprocessing/splits/samples与来源收据，不新建输入格式。
新增样本已发现与旧玩家组连通，不能直接拼接训练或当独立测试；研究用途与划分仍待用户决定。
共享contracts、storage、pyproject、CI、check.py、README、架构/交接协议和数据侧均未修改。
