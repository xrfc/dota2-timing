# Git结构与已合并分支清理（2026-10-30）

## 范围与当前结构

用户要求清理本项目GitHub和本地所有已合并分支、梳理Git结构并维护文档。仅处理`xrfc/dota2-timing`，不涉及账号下其他仓库。

- 远端：`origin = https://github.com/xrfc/dota2-timing.git`；GitHub默认分支为`main`。
- 当前本地只保留`main`，跟踪`origin/main`；远端只剩`main`，`origin/HEAD`指向它。
- 清理时三者HEAD相同：`0f90b74afb8fdb5604eac273ea7d7262318336f6`。
- 唯一worktree：`/home/node/.openclaw/workspace/work/dota2-timing`。数据/modeling仍是模块分工，不是两套Git工作区。
- 开始前工作区干净；切换main时提交未变。文档维护产生本地未提交修改，本次未提交或推送文档。

## 核验证据与删除清单

先fetch/prune，查询GitHub默认分支、全部分支及PR；开放PR为0。对每个当前分支tip执行`git merge-base --is-ancestor <tip> origin/main`，全部通过，不只依赖历史PR显示MERGED。PR #7合并后数据分支还有更新，但其最新tip与main相同，因此也可清理。

| 已删除远端分支 | 删除前完整tip | 本地同名分支 |
|---|---|---|
| docs/741f-development-mainline | 4cf23f94c82010cc09647040c7d39fb684a17850 | 原无 |
| docs/main-status-refresh | 70a9ef677b7c15cb0b1bc751f7cff4be6406429e | 原无 |
| feat/coach-workflow-infrastructure | 9cbc8314bba48ec395259149caf973f748bf7661 | 原无 |
| feat/hero-knowledge-cold-start | 267c3e76694d87a19f9b9e3b59e79c8da80dcdd7 | 原无 |
| feat/lineup-contracts | af239e9040116903e3fb8e66416fc381030a6720 | 已删除 |
| feat/purchase-data-prep | 0f90b74afb8fdb5604eac273ea7d7262318336f6 | 已删除 |
| feat/purchase-model-foundation | af239e9040116903e3fb8e66416fc381030a6720 | 已删除 |
| feat/training-admission-gate | d6bf02390cc892178c63017d36f10496705c113b | 原无 |
| fix/cache-identity-provenance | 942ebfd09f142660043f02c4811287ceca12a661 | 原无 |

远端9个引用使用单次atomic push删除，逐个附带预期tip的force-with-lease，避免删除核验后被他人推进的分支；不是强推覆盖main。本地3个使用`git branch -d`，未使用`-D`。首次HTTPS认证失败未删除远端；核实gh身份为仓库所有者后，仅在该次命令使用gh credential helper重试成功，未改持久认证配置。

核验：`git branch -avv`仅main及origin/main（另有origin/HEAD符号引用）；`git worktree list`为一个；GitHub branches API仅返回main。历史提交仍由main可达，无reset、rebase、历史压缩、tag删除、数据清理或垃圾回收。

相关合并：[PR #6](https://github.com/xrfc/dota2-timing/pull/6)、[PR #7](https://github.com/xrfc/dota2-timing/pull/7)；更早PR #1～5均为MERGED。lineup/model两个分支通过祖先关系证明已集成，不虚构独立PR。

## 日常工作与恢复

- 每轮先检查`git status --short --branch`与`git worktree list`；不恢复旧双分支模式。main是当前集成基线，不代表永远禁止按任务建立短期功能分支。新分支、提交、推送仍按任务授权串行协调。
- 后续已合并分支应核验**最新tip**是否被默认分支包含。squash/rebase导致祖先检查不通过时，单独核验，不使用强制删除掩盖不确定性。
- 如确需恢复某个引用，经确认后执行`git branch <原分支名> <表中完整tip>`。提交仍在main历史中，无须恢复数据或重建worktree；恢复远端还需要单独推送授权。
- 不为整理结构改写main上的历史merge commit；旧提交标题中的分支名不代表该分支仍存在。

## 文档与下一步

已同步AGENTS、README、贡献指南、文档索引、状态入口、总路线、日常操作和两份协作交接入口；10/16迁移收据与旧提示词明确标为历史，原始归档和实验结果不改。

产品顺序只维护在[总路线](roadmap.md)：COACH-01b新资源包接入→COACH-02实际浏览器案例验收→COACH-03小规模试标与任务确认。此次仅Git与文档维护，不实施新模型、真实训练、采集或浏览器验收。

本轮检查限定文档差异、链接目标、Git引用及历史可达性；纯文档修改不重跑全量代码测试，不借用旧测试数声称本轮通过。
