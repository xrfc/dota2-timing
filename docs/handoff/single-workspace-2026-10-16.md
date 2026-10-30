# 单目录整合与模型agent接续（2026-10-16）

> **2026-10-30现行入口**：当前单工作区已切回`main`；旧数据/模型分支均已合并并清理，不再保留分支引用。下方基准、迁移收据及提示词仅作10/16历史。当前任务读[总路线](../roadmap.md)，Git结构及恢复见[维护记录](../git-maintenance-2026-10-30.md)；协作规则仍读AGENTS及并行协议。

> **2026-10-17更新**：先读[单模块维护指南](../modular-maintenance.md)。foundation已拆分，data.validation及handoff.bundle为新维护入口；旧API兼容。下方独立worktree和验收属于历史。本轮单执行者，未来恢复并行仍须协调。

> **现行协作规则（2026-10-16）**：先读[并行开发与串行集成协议](parallel-development.md)。两侧专属文件可并行开发；共享文件、依赖变更和最终全量验收串行协调。2026-10-28起取消其他开发者停写确认门禁，当前执行者串行验收并检查源码漂移；下文历史验证不是本轮验收结果。

用户明确要求全部整合到一个dota2-timing目录，模型与数据管线并列；确认模型agent停止写入后授权执行。
本方案取代旧双worktree协作方式，但不改变研究协议。

## 2026-10-16迁移时的唯一工作目录（历史）

/home/node/.openclaw/workspace/work/dota2-timing

当前共享分支feat/purchase-data-prep；基准af239e9。两个旧分支在迁移前均指向此提交，
没有待合并的不同提交：本次整合的是模型侧6个未跟踪文件，不是Git历史merge。
feat/purchase-model-foundation分支保留历史引用，不包含这些尚未提交的新实现。
不要切换到它，否则会同时影响另一agent的工作目录。

结构保持现有Python包兼容：

- src/dota_items/data/：数据管线。
- src/dota_items/modeling/：模型模块，已接收foundation.py、synthetic_foundation.py。
- scripts/、tests/、examples/、docs/：按数据/模型职责分别维护，目录共享。
- data/：原始缓存和本地备份；reports/：审计、交接包和运行产物。
- .venv/：沿用原数据侧环境；没有用模型侧venv覆盖它。

整合的6个文件：docs/model-foundation.md、examples/model-foundation-lineup.json、
scripts/model_foundation.py、src/dota_items/modeling/foundation.py、
src/dota_items/modeling/synthetic_foundation.py、tests/test_model_foundation.py。
复制时逐文件SHA-256一致；旧模型说明是迁移前历史验收，独立环境指引不再适用。

## 保全与恢复边界

- 完整模型工作区归档：data/worktree-backups/dota2-timing-model-2026-10-16.tar。
- 归档SHA-256：1fff313c7423e447d0b64858e82aeacf25c02ab1fae8427b2213b0ab2f3fcd16。
- tar与源目录逐项比较通过，包含旧环境、忽略文件与报告；不上传。
- 模型历史reports另存reports/model-worktree-preserved-2026-10-16/。
- 迁移收据：reports/worktree-consolidation-2026-10-16.json。
- 归档中的.git指针与venv绝对路径属于旧位置，不应直接当可运行新工作区使用。
  如需恢复，先解压到独立暂存位置核对文件，再由用户决定是否重建worktree；不要覆盖当前目录。

## 本轮验证与完成状态

旧worktree已通过git worktree remove移除，磁盘旧目录不存在；git worktree list仅剩dota2-timing。
模型历史分支保留，未提交、推送或合并远端。6个模型文件整合前后哈希一致。
415项pytest、22项学习/知识、6项JS，共443项通过；304文件格式检查通过，pip check通过。
统一检查仍因原数据模块两处E501返回1，不冒充全绿；日志reports/consolidation-check-2026-10-16.log。
旧952快照train/validation通过foundation.adapt_snapshot只读兼容检查；没有fit或效果评估。
迁移的synthetic模型制品加载和predict成功，synthetic=true、BKB=null；不是真实模型效果。
原数据、冻结快照、标签、划分及三个遗留数据文件均未修改。
共享文件修改仅AGENTS.md和三份旧handoff文档的历史标记；新增本入口。

## 2026-10-16给模型agent的提示词（历史，不直接照搬执行）

项目已改为单工作区协作，请停止使用旧dota2-timing-model路径。
唯一目录是/home/node/.openclaw/workspace/work/dota2-timing，当前分支feat/purchase-data-prep。
你的6个新增文件已整合进来，数据管线data与模型modeling在src/dota_items下并列。
先读AGENTS.md、本文、docs/model-foundation.md、docs/data-prep-progress.md、
docs/handoff/purchase-data-interface.md；旧双worktree文档仅作历史。

请先核查git status和文件现状，不reset/clean、不切分支、不另建worktree、不覆盖未提交文件。
沿用现有.venv，检查依赖，不重新创建环境或自动安装依赖。
你负责modeling模块、模型脚本/测试及docs/model-foundation.md；不修改数据筛选、标签、快照或划分。
共享README/pyproject/统一CLI/依赖变更先协调。禁止并行提交、切分支和全库自动格式化。

接续任务：复核已有模型基础接口与数据交接包的兼容性，增加必要合成回归，
完善加载/预测和学习说明；不要重复造一个快照格式或把已经完成的工作说成待实现。
真实数据只能做获准的只读结构/来源检查；训练与验证split适配不等于授权fit。
不要读取旧test作选模，不运行真实训练、截距对照或新增1,038场模型评估。
新增数据已发现跨旧划分连通组，研究用途/标签/划分选择仍待用户确认。
不推送、合并或代表用户启动其他agent。输出写新的独立reports子目录，拒绝覆盖冻结产物。

现有数据包：reports/purchase-data-handoff-2026-10-16/，包含旧952场快照和新增审计，
不包含新增建模快照。旧模型制品在reports/model-worktree-preserved-2026-10-16/model-foundation/。
交付时区分合成测试、真实只读兼容、真实训练、提交、推送各自状态。
