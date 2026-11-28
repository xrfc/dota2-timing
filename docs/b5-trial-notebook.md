# 记录 B5 玩家试用反馈

用本机 B5 工作台看录像片段，再回到记录页写下哪些信息帮你作了判断、哪些说明仍然难懂。每条文字都随原报告的 SHA-256、比赛、英雄、场景和决策秒保存，便于开发者按原片段复核。

## 生成记录页

在已有 B5 工作台和三场报告的电脑上启动工作台。生成器通过回环地址读取已解析的片段清单，只需要 Python 标准库。工作台需要提供含 `report_sha256` 的 `/api/reports` 接口。[工作台来源与版本](https://github.com/xrfc/dota2-timing/pull/40)

若两项都在当前版本，可在仓库根目录的两个终端分别运行以下命令，试用时保持工作台运行。

```bash
.venv/bin/python scripts/outcome_viewer.py
.venv/bin/python scripts/b5_trial_notebook.py
```

若本分支只有生成器，可在同一工作区使用 PR #40 已验收的工作台。以下命令适用于保存有三场本机报告的 Linux 或 WSL 环境。首次准备时在仓库根目录运行，以新的空目录存放该版本的页面资源。

```bash
git fetch origin codex/b5-review-explanations-20261123
mkdir -p reports/b5-trial-notebook
mkdir reports/b5-trial-notebook/upstream
git archive 171e42dea59254d1dd774b027962425f6d172fd7 scripts/outcome_viewer.py scripts/outcome_viewer_assets | tar -x -C reports/b5-trial-notebook/upstream
ln -s ../../../data reports/b5-trial-notebook/upstream/data
```

已准备过的工作区可直接用下列命令启动。然后用另一个终端运行生成器。

```bash
.venv/bin/python reports/b5-trial-notebook/upstream/scripts/outcome_viewer.py \
  --report-root reports/b5-three-replay-20261123 --hero-dir reports/outcome-viewer-heroes
```

打开生成器打印的文件地址。默认文件为 `reports/b5-trial-notebook/index.html`，已有文件可直接打开。另一批报告用 `--output reports/b5-trial-notebook/下一批.html` 生成新页。工作台端口默认 8796，可用两个脚本各自的 `--port` 指向同一端口。

## 记录一次试用

1. 选择比赛和片段，打开工作台，核对所选英雄、场景和游戏时刻。三场试用中，第二场有 24 个可复盘片段，第三场有 20 个，可按下拉框的片段数识别。同秒片段由它在原报告中的位置区分。
2. 回到记录页写下原话，点击保存。切换片段会保留本页未保存的草稿，回到原片段可继续写。各场的进度只统计已保存意见的片段数。
3. 需要带走记录时导出 JSON。同一片段再次保存会更新其文字。请将导出的文件保存在本机。浏览器能否跨次打开本地 HTML 恢复记录，取决于浏览器、文件位置和存储权限；页面提示存储失败时，在关闭前导出。

记录页可离线填写，跳转复盘需要原工作台加载同一份报告。报告指纹在生成记录页时取得；工作台期间换过报告，应为新报告重新生成记录页。已导出的 `b5-trial-feedback/1` 文件包含 `records`，每条含 `match`、`report_sha256`、`hero`、`domain`、`time`、`seconds` 和 `feedback`。其中比赛标识及自由文本保留在本机。

本轮工具选型由执行者决定。片段来自工作台已接纳的报告，沿用它的筛选和排除结果。试用意见用于改进复盘展示。第二、三场的玩家反馈要等实际试用后才能登记。[前一轮三场试用记录](https://github.com/xrfc/dota2-timing/blob/171e42d/docs/outcome-autotrain.md#三场玩家试用)

## 工程验收（2026-11-24）

用本机三份原报告核对 SHA-256，在 Windows Chrome 中从生成页逐条选择 65 个片段，工作台显示的比赛、游戏时刻、英雄和场景均与报告标题一致。390 像素视口可完整显示记录页。在单独的合成报告上实际保存原话、刷新并下载 JSON，核对了文字空格与片段身份。本机收据目录为 `reports/b5-trial-notebook-20261124/`。
