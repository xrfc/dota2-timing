你在只读复核Dota 2项目知识库，提交是`a40b7be`（当前分支`claude/mk-t5-derived-2026-11-04`）。不要修改任何文件。

边界：只读下面列出的文件和它们导入的`src/`模块。不要读`configs/`、`data/`、`reports/`，不要读任何`.local`文件，不要联网。可以运行只读命令和`.venv/bin/python`的只读检查；需要输出时不要写进仓库。

目的是筛查这次改动有没有把用户裁定写错、丢信息、把不确定说成确定，或文档和数据对不上。

要读的文件：
- docs/decisions/2026-11-04-recheck-rulings.md（U85–U98用户原话和记录，是判断写入对错的依据）
- src/dota_items/data/mechanics_facts_v12.py、mechanics_facts_v13.py、mechanics_graph_v2.py、mechanics_interactions.py
- scripts/build_mechanics_facts_v13.py、scripts/build_mechanics_derived_v3.py
- tests/test_mechanics_facts_v13.py
- knowledge/mechanics/vocabulary-v13.json、rules-v7.json、extra-abilities-v1.json
- knowledge/mechanics/reviews/v13-inputs-001.json、slow-rulings-001.jsonl、terrain-rulings-001.jsonl、full-audit-005/、full-audit-006/、full-audit-007/、full-audit-008/ 的README、make_rulings.py和results/*.json
- knowledge/mechanics/reviews/u5-spot-check-002/（README、verdicts-2026-11-05.jsonl、build_page.py、page.template.html）
- knowledge/mechanics/extractions/v13/（facts-v13.json、rules-evaluation.json、manifest.json、README.md）
- knowledge/mechanics/profiles/derived-v3/（counter-graph.json、manifest.json，抽看heroes/*.md）
- knowledge/mechanics/README.md的“当前数据流”、knowledge/mechanics/profiles/README.md、CHANGELOG.md最上面一节

请逐项核对，用实际数据举证：
1. 决定记录里每条U93–U98裁定，是否都正确写进了`facts-v13.json`：技能、机制、条件、结论、`basis`。后面的裁定取代前面的时，最终结果是否是最新的。例如逃生技、重如铁锚、动能力场。
2. 改名和拆分有没有漏：词表已没有的词条（forced_action、mobility_lock、flying）是否还出现在`rows`、规则、派生层或页面；规则v7每个机制是否都在词表里；R11、R21、R22的来源和目标是否符合裁定。
3. 用户规则“跳跃和冲刺都算无视地形”的写入：`full-audit-007`分类为`jump_dash`的对象是否都写了，例外是否都有记录；闪烁和传送是否被误写。
4. 用户反馈：标“错”的记录最终状态是否和原话一致；`disputed_by_user`是否确实为0且合理；有没有标“错”却仍算确认、原话丢失的。
5. 条件：`condition_notes`是否挂在对的行；新增行的`condition`是否和来源一致；有没有基础和升级混淆。
6. 待定和候选：204条pending边是否与规则一致；`usable_edges`、`hero_relations`是否仍有效；档案里是否标了待定。
7. 依赖与复现：manifest是否覆盖实际读取；代码或输入变化是否会被发现；测试能否在代码退回错误行为时失败。不要运行会写入仓库的构建，可写到系统临时目录。
8. 文档里的数字和说法是否与文件一致（行数、basis统计、词表项数、规则数、边数、抽查数）。

规则：
- 只报有证据的问题。每条写文件、行或字段、复现方法和实际影响。“可能有风险”要标`confirmed=false`。
- 不评价Dota机制判断本身对错，那是用户的事；只查有没有如实写入。
- 不提大改建议，不建议数据库或框架。
- `items`里的`item`用上面的编号，没问题的项也要说明怎么验证的。
