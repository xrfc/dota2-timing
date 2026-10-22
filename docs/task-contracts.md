# 版本化任务契约（2026-10-20）

## 2026-10-21 新登记任务

新增 `juggernaut-source-log-7.41f-whole-11/1`，整份有效源日志11装备，`window=null`、`labels.scope=whole_available_source_log`，所有有限事件时间含赛前时间。旧30分钟ID、默认值和旧产物保持不变。沿用契约/1及快照/2容器，靠明确task_id与完整登记字段区分，不接受任意目标名单。
新生产入口、继承成员、数据限制及完整验收见[整局11装备任务](whole-log-task-2026-10-21.md)。`modeling.batch`、训练与模型制品验证按已登记任务确定5或11列；`model_foundation.py demo/predict --task-id`支持两个ID，demo仅合成数据。新任务不自动授权真实训练。下文“唯一登记”属于10/20历史。

## 范围与决定

用户授权建立共享任务契约，并确认本轮只有一个执行者操作 Windows 副本。
本轮是工程接口演进，不运行真实采集、快照生成、训练或划分重建。
研究范围沿用现有实现；以下字段不是本轮新增研究决定，也不证明模型效果。

唯一登记 ID：`juggernaut-source-log-7.41f-30m/1`。
登记位于标准库模块 `dota_items.contracts.tasks`，不接受任意配置或动态插件注册。

| 字段 | 当前登记值及含义 |
|---|---|
| 英雄 | 主宰，ID 8 |
| 位置 | 请求 position 1，但未独立验证实际位置；不能宣称所有样本均为一号位 |
| 补丁范围 | 仅 7.41f；官方发布时间推断，不是客户端版本认证 |
| 时间窗口 | 游戏时间 `[0,1800)`，右端点不包含 |
| 目标 | 五种装备 key 在有效源购买日志中是否出现 |
| 装备顺序 | bfury、maelstrom、manta、black_king_bar、skadi |
| 负例 | 有效源日志未出现，不等于实际没有购买 |
| 未知 | null 标签与 false mask，不能变成负例 |
| 特征 | lineup-multihot/1；只用赛前阵容英雄 ID，词表仅 train 拟合 |
| 未知英雄 | 每侧 unknown count |

`task_contract()` 每次返回独立 JSON 对象；校验比较完整登记值和 JSON 类型，
拒绝未知 ID、版本、额外字段、字段遗漏以及 bool/float 冒充整数。
任何新英雄、窗口、补丁、标签或特征都需要新的明确研究决定与登记版本。

## 数据生产者与模型消费者

1. `data.task_snapshot.build_task_snapshot(summary_path, task_id=...)` 在重建前检查
   summary 的英雄、请求位置、补丁、窗口及装备顺序。
2. 调用原有生产者核验来源、审计和玩家分组；不跳过旧哈希检查。
3. 要求补丁时间证据一致、样本目标英雄匹配，然后生成
   `purchase-log-modeling-snapshot/2`，在 `task.contract` 保存完整契约。
   `task_implementation_sha256` 另记录新生产者和契约实现哈希。
4. `modeling.batch.adapt_snapshot` 接受 /1 与 /2；/2 必须带有效契约，
   并继续检查标签、编码、词表及所选 split。它不是来源真实性验证器。
5. `fit_model` 从 /2 任务产生 `purchase-foundation-model/2`，原样保留契约；
   新制品实现指纹必须包含 contracts/tasks.py，缺失则拒绝。
6. `load_model(..., expected_task_contract=...)` 和
   `predict_lineup(..., expected_task_contract=...)` 可要求严格任务兼容。
   /2 预测及 inspect 输出包含 `task_contract`；它声明适用范围，不验证调用场景
   实际属于该补丁或位置。应用方仍须检查其场景。

样例 API：

```python
from dota_items.contracts.tasks import task_contract
from dota_items.modeling.artifacts import load_model
from dota_items.modeling.inference import predict_lineup

expected = task_contract()
model = load_model("model-v2.json", expected_task_contract=expected)
result = predict_lineup(model, lineup, expected_task_contract=expected)
```

## 命令

以下真实数据命令仅说明接口，不表示已执行或授权重建现有研究数据。
输出必须使用新路径，已有文件拒绝覆盖。

```text
python scripts/prepare_purchase_snapshot.py --summary SUMMARY.json --output NEW.json --task-id juggernaut-source-log-7.41f-30m/1
python scripts/prepare_purchase_snapshot.py --summary SUMMARY.json --verify NEW.json --task-id juggernaut-source-log-7.41f-30m/1
```

旧生产者重建如需已登记迁移，仍显式添加 `--allow-producer-migration`。
该开关只作用于底层历史审计；/2 自身的内容和任务实现指纹仍精确比较，
不自动允许未来契约/生产者变化。

合成 demo 与已有制品预测：

```text
python scripts/model_foundation.py demo --output NEW-SYNTHETIC.json --task-id juggernaut-source-log-7.41f-30m/1
python scripts/model_foundation.py predict --model MODEL.json --lineup LINEUP.json --task-id juggernaut-source-log-7.41f-30m/1
python scripts/model_foundation.py inspect --model MODEL.json
```

## 兼容边界

- 不传 `--task-id` 继续走原有 /1 入口，旧文件不补字段、不重写。
- /1 读取不会推断缺失的位置、补丁或特征版本；要求新契约的调用拒绝 /1 模型。
- /2 缺失契约、或将带契约容器标成 /1，均拒绝。
- 旧模型无实现清单、四文件清单及上一版模块清单仍按 /1 规则读取；
  不因此认证旧模型训练数据的补丁或位置。
- 原 `purchase_snapshot.py` 及其历史生产者哈希保持不变；没有新增迁移白名单。
- 现有 `purchase-data-handoff/1` 包和历史实验脚本仍使用 /1。
  本轮新 /2 接口是独立快照到模型的链路，不自动改写旧包或历史实验。
- 数据集的 scope 元数据不是训练许可；测试只训练合成样本。

## 维护与验收

共享契约变更由单执行者协调数据和模型侧。`tests/test_task_contracts.py`
同时属于 data/modeling/recommendation 专项检查，Windows CI 也纳入该回归。
测试覆盖范围篡改、类型、schema 降级、旧模型兼容、制品指纹、生产者配置拒绝、
新旧合成模型数值一致、保存加载和 CLI 任务检查。

新增任务时应同步契约、生产者、适配器、训练/推理能力及文档，而不是只把 ID
加入白名单。改变标签、编码或权重表达时须决定对应 schema 版本。

## 本轮验证记录

后续推送前已在独立临时目录补齐 Ruff 并通过静态检查；
最新范围和测试结果见[开发分支同步检查](github-sync-2026-10-20.md)。
下列未安装 Ruff 状态为契约实现当轮记录。

- 任务链路及相关数据、模型、架构专项首轮 223 项通过；后补 CLI 用例后，
  任务契约专属测试共 31 项通过，/2 合成 demo 创建、保存、重载成功。
- 整个 Python 测试目录：883 通过、21 失败、9 跳过；234 个源码、脚本、
  测试、文档及配置文件在该次运行前后指纹一致。
- 21 项失败中，12 项为 Windows 缺少创建符号链接权限，9 项为测试默认
  GBK 解码 UTF-8 文件。仅为子进程设置 PYTHONUTF8=1 后，这 9 项均通过；
  连同 31 项任务契约测试，补验共 40 项通过。
- 当前 Python 未安装 Ruff 和 Gem；未安装依赖或改变系统权限，
  未完成 Ruff 检查及完整环境下的全量验收。CI 配置已补测试，但未推送运行。
- `git diff --check` 通过；历史 `data/purchase_snapshot.py` 无差异。
- 没有运行真实数据生成或训练，没有变更划分、旧快照或模型产物，没有提交或推送。
