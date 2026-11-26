# AI临时分支契约（U25，2026-10-31用户确认）

适用对象：所有在**临时环境**（云端容器、会被回收的沙箱等）里改动本仓库的AI助手（Claude、Codex、Copilot等）。本地OpenClaw工作区仍只用`main`，不受本契约影响（见AGENTS.md）。

## 1. 为什么要有

临时环境被回收时，未推送的提交会一起丢失。但用户规则是“只在用户要求时推送`main`”（U19、U24）。专用临时分支解决这两者的矛盾：

- 提交随时推送到远端专用分支，防丢失；
- `main`保持不变，进不进`main`由用户在PR上决定。

## 2. 分支命名

- 每个AI一个长期分支：`<ai名>-temp`，小写。例：`claude-temp`、`codex-temp`、`copilot-temp`。
- 只在自己的分支上提交；**不得推送、改写或删除其他AI的temp分支**。
- 同一AI同时有多个会话时，共用自己的temp分支；开始前先拉取，发现远端有本会话不知道的提交时以远端为准（rebase到其上），不强推覆盖。

## 3. 权限

| 操作 | 是否需要用户每次同意 |
|---|---|
| 在自己的temp分支提交、推送 | 不需要（本契约授权，用于防丢失） |
| 开PR：`<ai名>-temp` → `main` | 不需要（本契约授权） |
| 合并PR、直接推送`main` | **需要**：由用户在GitHub网页上合并，或用户明确说“合并”“推送main” |
| 强推（force push）自己的temp分支 | 仅限§4“重置”情形，且只用`--force-with-lease` |
| 删除任何远端分支、改写`main`历史 | **需要** |

本契约不扩大其他权限：真实训练、联网采集、新数据用途、依赖变更等仍按AGENTS.md与计划§2逐项询问。

## 4. 每次会话流程

**开始**

```bash
git status --short          # 必须为空；有未提交改动先问用户，不得丢弃
git fetch origin            # 远端还没有该分支时，按名字fetch会报错，故整体fetch
# 若远端还没有该分支：从最新main创建
git checkout -B <ai名>-temp origin/main
# 若已有：切到远端版本，再检查是否已全部并入main
git checkout -B <ai名>-temp origin/<ai名>-temp
git log --oneline origin/main..<ai名>-temp   # 列出尚未进入main的提交
```

- 输出为空（全部已合并）：**重置**到最新main：`git reset --hard origin/main`，之后首次推送用`git push --force-with-lease origin <ai名>-temp`。
- 输出非空（有未合并提交）：`git rebase origin/main`；有冲突则停下告诉用户，不自行取舍他人改动。
- 然后按计划§6.1检查工作区，读§7当前任务。

**开发中**

- 每完成一件事：运行相关检查→提交→`git push -u origin <ai名>-temp`。
- 文档按U24同步维护（相关文档、计划§7/§8、CHANGELOG、决策记录、学习笔记）。
- 提交身份用所在环境要求的身份（Claude云端为`Claude <noreply@anthropic.com>`）。

**结束 / 需要进main时**

1. 推送前运行全量检查`scripts/check.py --scope all`，结果写进PR描述。
2. 开PR（若该分支已有未合并的PR，直接推送更新它，不重复开）。PR描述列出：改了什么、为什么、对应决策编号、检查结果、未验证点。
3. 告诉用户PR链接；**由用户合并**。建议用“Create a merge commit”或“Rebase and merge”；用“Squash”也可以，下次会话开始时按上面的“重置”处理。
4. 按计划§6.2写交接备注。

## 5. 冲突与安全

- 本地`main`与temp分支同时改同一文件时，PR会显示冲突：AI停下来说明冲突位置，由用户决定保留哪边。
- 不提交`configs/*.local.json`、账号ID、凭据、`data/`、`reports/`（`.gitignore`已排除，提交前再检查一次）。
- 临时分支不是发布分支：不打tag，不作为其他工作的基础。

## 6. 记录

- 决策：[U25](../decisions/2026-10-31-ai-temp-branch.md)
- 入口：AGENTS.md“AI临时分支”一节；计划§6、§7“运行与交接备注”。
