# Codex任务书：无人工评审的结果驱动训练（U191，2026-11-22）

执行者：Codex gpt-6.2-astra，high。工作目录：`/home/node/.openclaw/workspace/work/dota2-timing-lane-outcomes`（独立worktree），分支`codex/outcome-autotrain-20261122`（基于PR #33 `codex/lane-outcome-learning`）。环境和数据复用`/home/node/.openclaw/workspace/work/dota2-timing/.venv`与其`data/`，只读。

## 先读

1. `AGENTS.md`（项目规则）、`docs/decisions/2026-11-22-no-human-review.md`（U191，本任务授权）。
2. `docs/current-status.md`、`docs/decision-framework.md`。
3. PR #33成果：`docs/lane-study-protocol.md`、`docs/lane-study-results.md`、`scripts/lane_study*.py`。

## 授权范围（U191）

- 可以：在U133非留出的1341场上建样本、反复训练、调参、做消融；提交并推送本分支；开PR到`main`（PR说明写清基于#33）。
- 留出337场：全部开发结束、方案冻结后只评估一次，评估前在文档里写下冻结的模型与指标，评估后不再改模型。
- 不可以：联网采集新demo；合并PR、推送main、删除或强推任何分支；修改主worktree（`dota2-timing`）里的文件；动用户评审数据库；把账号ID写入跟踪文件。
- 没有人工评审：不要等人工判断，不生成待人工判断的队列；需要“人”的地方用录像结果或可核验规则代替，Codex盲审只作交叉检查。

## 要做的事（按顺序，每完成一项提交一次）

1. **扩展到全开发集**：PR #33只用了76场试点。把补刀前样本扩到全部1341场非留出比赛（按#33协议的支持条件），复跑三个阶段，报告样本量变化后结论是否改变。
2. **结果标签扩充**：在20秒死亡、补刀之外，加入决策后窗口内的金钱、经验净变化，以及被击杀造成的损失（可复用死亡代价v0的胜率差，见`docs/b2-death-risk-baseline.md`）。说明每个标签的定义、窗口和局限。
3. **行动价值估计**：对“继续收线/后撤”给出各自的预期后果，用相似局面比较（倾向得分加权或双重稳健估计等，选一个并说明理由），报告重叠不足的片段比例。这是“模型自己判断哪个选择更好”的核心，替代人工评审。
4. **扩到打野与支援决策**：复用主worktree `reports/local-review-20261122/action-comparison-jungle-001` 与 `scripts/` 中现有的打野、支援取样逻辑，在全开发集上做同样的结果标签与行动价值估计。
5. **冻结并在留出集评估一次**：写好冻结清单后跑留出集，报告与开发集的差距。

每一步：先写测试；`NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost .venv/bin/python scripts/check.py`退出码为0才提交（本机有代理变量，不设NO_PROXY会让回环测试报502）。

## 文档（U24、U190）

每一步同步：相关模型卡/结果文档、`docs/current-status.md`、计划§7、`CHANGELOG.md`、`learning/docs/project-ml-notes.md`。实现选择（特征、模型、超参、阈值）注明“实现选择，非用户决定”。新文件登记到`docs/README.md`，新脚本在`src/dota_items/architecture.py`登记。数字只写实际跑出来的。

## 结束时

推送分支，开PR（或更新已开PR），最后一条消息用中文总结：做了哪些步、关键数字、留出集结果（若已跑）、未完成项和原因。中途遇到真正需要用户决定的事（改变研究目标、需要联网、需要新依赖），停在那一步，写进总结，不要自行越权。
