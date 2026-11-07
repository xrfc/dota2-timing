你在只读复核Dota 2项目知识库的一次工程修复。不要修改任何文件。当前目录是仓库，改动未提交（用`git status`和`git diff`可看已跟踪文件，未跟踪文件直接读）。

边界：只读下面列出的文件和它们导入的`src/`模块。不要读`configs/`、`data/`、`reports/`，不要读任何`.local`文件，不要联网。可以运行只读命令和`.venv/bin/python`的只读检查，但不要写入仓库；需要输出时不要写文件。

背景：事实v13和派生层v3要修5个问题。

1. 生效条件说明不再丢失（`condition_notes`、`condition_review`）。
2. 待定规则的状态传到克制关系和档案。
3. 克制关系写明只是候选，每条边带`relation`和`status`，程序默认读不到待定规则（`usable_edges`）。
4. 用户标“错”不算确认：`ok`才算抽查确认，`wrong`记`disputed_by_user`，`unsure`不变，原话保留，找不到行的进`unattached_feedback`。
5. 依赖记录补全：manifest记录构建实际读到的全部文件，构建前后比对哈希，中途变化就报错。

要读的文件：
- src/dota_items/data/mechanics_facts_v13.py
- src/dota_items/data/mechanics_graph_v2.py
- scripts/build_mechanics_facts_v13.py
- scripts/build_mechanics_derived_v3.py
- tests/test_mechanics_facts_v13.py
- knowledge/mechanics/reviews/v13-inputs-001.json
- knowledge/mechanics/extra-abilities-v1.json
- knowledge/mechanics/extractions/v13/（facts-v13.json、rules-evaluation.json、manifest.json、README.md）
- knowledge/mechanics/profiles/derived-v3/（counter-graph.json、manifest.json，抽看几个heroes/*.md，如hero-60、hero-80、hero-1）
- knowledge/mechanics/README.md的“当前数据流”、knowledge/mechanics/profiles/README.md、CHANGELOG.md最上面一节

请核对：
- 这5项是否真的做到，有没有哪条路径仍会丢信息、把待定当确定、把标错当确认，或漏记依赖。
- 用实际数据举证，不要只读代码。例如`basis`统计、条件说明是否挂对了行、`user_feedback`是否对应正确、`item_to_hero`的`status`是否与规则一致、manifest的输入是否覆盖实际读取。
- 测试是否真的能在代码退回错误行为时失败。
- 文档里的数字和说法是否与文件一致。
- 新代码有没有破坏旧版本复现（v12、derived-v2应不受影响）。

规则：
- 只报有证据的问题。每条写文件、行或字段、复现方法和实际影响。“可能有风险”要标`confirmed=false`。
- 不评价Dota机制判断对错，那是用户的事。不提大改建议，不建议数据库或框架。
- 没问题的项也要说明你是怎么验证的。
