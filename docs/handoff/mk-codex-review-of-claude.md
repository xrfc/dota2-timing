# 交接：请Codex复核Claude第1轮结果（U34，可选）

用户先说“你不用非得交给codex”（U34），随后说“这个可以给他复核”。所以：**Codex可以复核Claude的结果，但不是必须环节**；Claude不会等待Codex才继续后续修正。本文件是Codex的入口。

## 1. 复核对象

- PR #12，分支`claude-temp`；结果目录`knowledge/mechanics/reviews/claude-round-001/`
- 复核包：已随PR #11并入main的`knowledge/mechanics/cross-review/v1`（packet_id `26dff7e706583c96ff4aced460fad135c32620c840be5f4745c99851b56d18cf`）
- 当前结论（按用户U33、U35改判后）：接受1,264、排除286、不确定1；对照`check-003/`。`check-001/`是改判前的原始结果，`check-002/`是U33后的结果。

先读：`review-summary.md`（方法与局限）、`coverage-findings.md`、`user-questions.md`、`docs/decisions/2026-11-01-round1-user-answers.md`（U33）和本文件。

## 2. 优先级清单

`codex-review-queue.csv`列出Codex尚未审过的1,527组（已排除Codex原先审过的24组），按风险排序：

| 优先级 | 组数 | 内容 |
|---|---|---|
| P1 | 389 | Claude排除或不确定的组（误排除会丢掉真实机制），以及按U33/U35改判的组（核对是否与用户原话一致） |
| P2 | 448 | 用统一表述批量接受的组：受破坏影响、减速、单体指向、施加强/弱驱散，重点找个别误收 |
| P3 | 690 | 逐条写理由的接受 |

建议至少完成P1；P2按机制抽查。

## 3. 已知需要注意的点

- Claude逐组只读首条原文（英文优先）及上下文，同组其余证据没有逐条重读；约20组读了完整说明。
- 受破坏影响：按U33，被动（含先天）除美杜莎·魔法盾外都算可被破坏；小小·长大、米波·分则能成与维基指引冲突，保留不确定。“怕破坏”是另一件事，名单草案见`user-questions.md`，未写入复核结果。
- 单体指向：法球/攻击附加类按“可对敌施放或自动施放”接受；用户报告连击、天界箭袋、影武长刀不触发法术反制/莲花/林肯，尚未写入U31交互记录。
- 定义边界已由用户决定（U33）：固定值反击算反伤、不可控召唤单位算召唤物、盛宴算吸血、延迟伤害算减伤、虚妄之诺不算治疗。U35又定：夺取控制归召唤物、虚妄之诺算减伤、长大/分则能成不能被破坏、怕破坏英雄6个（`knowledge/mechanics/break-vulnerable-heroes-v1.json`）。

## 4. 回传方式

- 在`codex-temp`上工作（U25），不要改写`claude-temp`。从最新main开始；PR #12若尚未合并，可按PR #11交接中的`git archive`方法只读导出`origin/claude-temp`。
- 结果写到新目录，例如`knowledge/mechanics/reviews/codex-round-002/`：每组至少记录`review_id`、Codex结论（accept/reject/uncertain）、解释、条件、理由、引用的`fact_id`。现有`scripts/mechanics_cross_review.py compare`只比较“Claude结果↔codex-prior”，如需比较“Codex第2轮↔Claude第1轮”，请扩展工具或另写对照，并说明。
- 与Claude不同的判断逐条写明原因；与用户既有结论冲突的保留给用户裁定。同标签不等于事实认证。
- 不授权合并、推送main、训练或联网采集。

## 5. Claude同时在做的事（避免重复）

> 2026-11-01：漏抽修正、词表v3与v2证据已完成（`knowledge/mechanics/extractions/v2/`，见`docs/knowledge-framework.md`§6）。

按U34，Claude在`claude-temp`上继续：修正漏抽（斯嘉蒂之眼、辉耀闪避、天堂之戟、希瓦光环、斧王·反击螺旋）与抽取规则、按U28–U33出词表v3、补交互记录，再生成第2版证据。Codex复核第1轮结果时不需要处理这些。
