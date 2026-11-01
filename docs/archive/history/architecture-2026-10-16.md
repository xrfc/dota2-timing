# 双方向架构审查（2026-10-16）

## 后续替代 — 2026-10-17

本页为历史审查。当前以[模块维护指南](modular-maintenance.md)为准。foundation职责混合、data/workflow及sources/data反向依赖已处理，交接读取独立为handoff.bundle。
私有读取复用已于10/17上午收尾消除，见[公共读取接口](public-source-reader.md)；下方454项及旧lint状态不是当前验收。

## 同日加固集成更新

数据与模型子任务并行完成专属修改后停写，由架构协调者串行收尾。
- 数据交接强化固定载荷、JSON/路径/哈希/schema及故障发布检查；非有限统计输入明确拒绝。
- 模型加强适配、制品语义与合成端到端回归；实现指纹覆盖共享编码、C网格及storage。
- 原两处E501已修复。本节以下454项及20文件原字节记录是架构初次审查的历史结果。
- 本次合法修改cohort_handoff生产者，旧审计不能与新生产者冒充逐字节重现；
  旧实现已归档，新审计/包位于 reports/purchase-cohort-compatibility-2026-10-16/，
  新旧审计逐项比较仅1项实现哈希变化，统计与研究边界完全不变，旧产物保持不变。
- 最新全量结果由父会话在两侧停写、源码指纹稳定的验收窗口独立记录，不能以专项代替。

## 结论与证据范围

保持一个仓库、一个 Python 包、data/modeling 两个开发方向，不拆服务、不重新建 worktree。
两方向通过冻结 JSON 快照交接，算法层不应依赖采集、审计或工作流实现。
本轮仅工程结构优化，不改变数据范围、标签、划分、模型参数或真实训练授权。

实查 GitHub origin（git ls-remote --heads）：main=c6a5e1f；
feat/lineup-contracts、feat/purchase-data-prep、feat/purchase-model-foundation 均为 af239e9。
本地分支 feat/purchase-data-prep，双方向新增实现尚未提交，不能从 GitHub main 判断当前完成度。
远端引用与本地 Git 对象核对；未验证本轮 GitHub Actions 运行，未推送或合并。

## 现行开发协作规则

用户已明确：两侧可并行修改各自专属文件；共享文件修改、依赖安装与最终全量验收串行协调。
文件所有权、暂停写入确认、单写者执行和验收窗口见[协作协议](handoff/parallel-development.md)。
这是工程协作边界调整，不是拆包、数据迁移或新增真实实验授权。

## 当前结构与职责

| 目录 | 职责 | 开发边界 |
|---|---|---|
| src/dota_items/sources | OpenDota/Gem 读取、预算与缓存 | 数据侧；不依赖模型 |
| src/dota_items/data | 清洗、语义审计、标签、连通组划分、冻结快照及交接包 | 数据侧；不依赖模型 |
| src/dota_items/contracts | 新增轻量共享编码接口 | 双方协调；不导入业务层或第三方库 |
| src/dota_items/modeling | 快照适配、频率/逻辑回归、诊断、敏感性报告、制品预测 | 模型侧；不导入数据管线 |
| src/dota_items/workflow | 旧回放工作区、准入、任务进程与登记 | 编排层，不是当前实验的统一调度服务 |
| src/dota_items/recommendation | 独立的人工规则推荐 | 不是训练模型的在线推理入口 |
| storage.py / domain.py / normalize.py | 文件身份与基础数据处理 | 公共基础设施，改动需评估跨方向影响 |
| scripts / tests / examples / docs | 命令编排、软件验证、合成样例、说明 | 共享目录，按文件职责分工 |
| data / reports | 本地缓存、冻结证据与输出 | 不当作可随意覆盖的代码目录 |
| learning / knowledge | 学习材料与知识证据 | 与数据证据链有联系，不是模型训练结果 |

依赖箭头表示代码调用，不表示数据流（下图只展示双方向主干，不含下述历史反向依赖）：

```text
scripts → data → sources / storage
scripts → modeling → contracts.lineup / storage
```

数据流：sources → data → 冻结 snapshot/manifest → modeling → 独立模型制品/报告。
脚本可以组合数据验证与模型调用；算法模块不能通过脚本反向访问采集。

## 发现与处理

1. **模型导入审计链（已优化）**：foundation 与 synthetic_foundation 原从
   data.lineup_preflight 导入两个纯函数，连带导入 feasibility、patch_time、player_overlap 等。
   现改为 contracts.lineup；columns 也归入该接口，foundation.columns 的旧导入路径仍兼容。
2. **冻结证据与代码指纹耦合（保留且明确）**：purchase_snapshot 重建包含实现哈希，
   verify_snapshot 比较完整规范 JSON。移动旧生产者代码即使行为相同，也会使旧重建失配。
   本轮不修改任何 data 模块及冻结快照；共享接口暂留兼容实现副本，由 parity 测试防漂移。
   下一版生产者再迁入 contracts，并形成新的版本与证据，不能静默重写旧快照。
3. **历史层次双向依赖（未冒充解决）**：data.pipeline/acceptance → workflow.validation，
   workflow.validation → data.context；data → sources，sources.gem_replay 延迟导入 data.context。
   这是包级双向依赖，不等于已经出现运行时循环导入故障。后续应将纯验证/上下文接口下沉，
   但需同步来源证据版本，不在这次进行大规模搬迁。
4. **数据内部私有接口复用**：feasibility_sampling/player_overlap 使用 feasibility._parse/_read_bytes。
   后续发布新版数据证据时抽到数据侧公共读取模块；不让模型依赖这些私有方法。
5. **共享目录冲突**：目录并列不隔离 Git index、环境和 README。继续单写者提交/安装约定，
   不并行切分支、全库格式化或覆盖对方未提交文件。共享 contracts 改动须同时运行两侧测试。
6. **依赖命名仍偏历史**：data extra 同时安装 pandas/sklearn，模型也使用它；当前不拆 extra，
   避免安装接口变更。待模型真正独立部署再考虑 modeling extra 与显式 NumPy 依赖。
7. **迁移后的检查入口**：直接运行原 check.py 时当前环境无法导入 dota_items。
   现仅为检查子进程显式添加当前 checkout/src 到 PYTHONPATH，保留用户原路径，
   不重建或安装共享环境；其他命令仍按文档显式设置 PYTHONPATH 或使用正确安装的环境。

## 可执行边界

新增 tests/test_architecture.py，纳入现有 pytest / CI，无新增检查依赖：

- 禁止 data/sources → modeling；禁止 modeling → data/sources/workflow/recommendation。
- 保持 recommendation 独立；共享 contracts 不引入业务层和第三方库。
- AST 检查覆盖绝对、相对和函数内 import；不声称能静态识别任意动态导入。
- 新进程验证导入模型时未加载数据/采集/工作流模块。
- 不同词表、未知英雄、空输入、重复值及特征列顺序与旧生产者保持一致。

复现：

```bash
.venv/bin/python scripts/check.py
PYTHONPATH=src .venv/bin/python -m pytest tests/test_architecture.py tests/test_model_foundation.py -q
```

## 本轮验证

- 426 项 pytest（含新增 11 项架构/兼容测试）、22 项学习/知识 unittest、6 项 JS 测试通过，合计 454 项。
- 本轮变更 Python 文件 Ruff 检查通过；全库格式检查通过。
- 全库 lint 仍有原有 cohort_handoff.py:294–295 两处 E501，统一检查退出码不是 0。
  这次保留数据侧文件原字节，不以全库格式化或忽略规则掩盖它。
- 19 个 data 实现文件与旧952快照，共20个 SHA-256 与审查前一致。
- 未重新训练真实模型、未重划分、未读取旧 test 进行选模、未推送/提交/合并。
- 本次只改两个现有模型文件的导入/columns、scripts/check.py、README 与文档索引；
  新增 contracts 两个文件、本测试和本文。起始工作区的其他未提交改动全部保留。

## 扩展约定（本轮工程建议，不是新研究授权）

- 新模型：复用 snapshot 适配和 mask；新增模型实现及合成测试，不回头调用采集器。
- 新标签/窗口/英雄范围：先由用户确认研究选择；数据侧发布新任务契约和来源证据，模型侧显式适配。
- 新编码：版本化字段顺序、词表与 unknown 语义；训练和预测复用同一个共享实现。
- 新制品：保留 task、preprocessing、来源身份、代码版本；输出独立目录，禁止覆盖冻结产物。
- 将来接入推荐：新增显式适配层；不要把源日志购买概率当成最佳装备效用。
- 当前无需插件系统、微服务、数据库迁移或拆成两个发行包；先让边界测试约束演进。

最新工作区规则见 [单目录交接](handoff/single-workspace-2026-10-16.md)，
数据接口见 [交接契约](handoff/purchase-data-interface.md)。
