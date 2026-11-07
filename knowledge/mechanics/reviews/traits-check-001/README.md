# 英雄特性整体抽查（MK结束前，2026-11-07）

页面：<https://claude.ai/artifact/2Q8vM6Vsv25nuEFuWpvWsw>（私有）。结果存在页面的`verdicts`集合，读回后写成`verdicts-<日期>.jsonl`。

- 用户要求：抽约1/4的英雄，并加看克制关系（2026-11-07）。
- 抽样（助手实现选择，`build_sample.py`）：用户常玩的4个（主宰、巫医、干扰者、神谕者）；每项特性数量最多的英雄和升级后增加最多的英雄；法力依赖例外名单、魔法爆发名单各2个；其余按固定哈希顺序补足到32个（127个的约1/4）。不是纯随机样本，偏向极端值，所以错误率不能外推。
- 每个英雄看两部分：12项特性的基础数和含升级数（列出算进去的技能、机制、条件和是否已确认；为0的特性折叠在下面，用来查漏），以及“可能克制它的”候选关联（每条规则涉及它的哪些技能、哪些装备）。每项标对、错、不确定。
- 数据都通过`knowledge/mechanics/current.json`读取（事实v21、派生层v12）。

```bash
PYTHONPATH=src python knowledge/mechanics/reviews/traits-check-001/build_sample.py
python knowledge/mechanics/reviews/traits-check-001/build_page.py
python knowledge/mechanics/reviews/traits-check-001/export_verdicts.py <JSON目录> <输出.jsonl>
```

标“错”的项按以前的办法处理：助手查原因（事实、映射还是规则），用户裁定，出新版本。
