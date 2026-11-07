# 英雄特性整体抽查（MK结束前，2026-11-07）

页面：<https://claude.ai/artifact/2Q8vM6Vsv25nuEFuWpvWsw>（私有）。结果存在页面的`verdicts`集合，读回后写成`verdicts-<日期>.jsonl`。

- 用户要求：抽约1/4的英雄，并加看克制关系（2026-11-07）。
- 抽样（助手实现选择，`build_sample.py`）：用户常玩的4个（主宰、巫医、干扰者、神谕者）；每项特性数量最多的英雄和升级后增加最多的英雄；法力依赖例外名单、魔法爆发名单各2个；其余按固定哈希顺序补足到32个（127个的约1/4）。不是纯随机样本，偏向极端值，所以错误率不能外推。
- 每个英雄看三部分，每项标对、错、不确定：①12项特性的基础数和含升级数（列出算进去的技能、机制、条件和是否已确认；为0的特性折叠在下面，用来查漏）；②全部技能机制，每个技能一项，查英雄特有的机制有没有错或漏，如虚妄之诺的免死（U117加的）；③“可能克制它的”候选关联（每条规则涉及它的哪些技能、哪些装备）。共384项特性、180个技能、32组关联。
- 数据都通过`knowledge/mechanics/current.json`读取（事实v21、派生层v12）。

```bash
PYTHONPATH=src python knowledge/mechanics/reviews/traits-check-001/build_sample.py
python knowledge/mechanics/reviews/traits-check-001/build_page.py
python knowledge/mechanics/reviews/traits-check-001/export_verdicts.py <JSON目录> <输出.jsonl>
```

- 2026-11-07第一轮：49项，对44、错3、不确定2（`verdicts-2026-11-07.jsonl`），按U118调整。之后重建页面时沿用同一批32个英雄（`build_sample.py`读已有`sample.json`），已标结果按项目编号保留。
- 第二批（用户要“没抽查到的特性，少筛选点”）：`build_batch2.py`从还没标过的特性里，每项特性挑1–2个英雄（名单类特性1个），优先含未确认技能的，共19项，写在`batch2.json`；页面默认只显示这批。致盲在样本里只有一个英雄且已标过，没有进第二批。
- 第二批19项全部为对（`verdicts-2026-11-07b.jsonl`）。抽查于2026-11-07结束（U122），共68项。标的是特性数量和技能机制清单，不回写成逐行事实的用户确认。

标“错”的项按以前的办法处理：助手查原因（事实、映射还是规则），用户裁定，出新版本。
