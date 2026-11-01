# 交接：请Codex复核Claude第1轮结果（U34，可选）

用户先说“你不用非得交给codex”（U34），随后说“这个可以给他复核”。所以：**Codex可以复核Claude的结果，但不是必须环节**；Claude不会等待Codex才继续后续修正。本文件是Codex的入口。

## 本次Codex复核回传（2026-11-01）

P1队列389项已覆盖（387语义＋2过时升级处理）；19个v3移除组均只核对处理依据。结果见[Codex第2轮](../../knowledge/mechanics/reviews/codex-round-002/README.md)：114接受、257排除、16不确定，与Claude不同19组（3接受建议、16待裁定）。9组先天例外涉及U33适用范围，交用户裁定。P2/P3未审；旧结果不改写。

## 1. 复核对象

- PR #12，分支`claude-temp`；结果目录`knowledge/mechanics/reviews/claude-round-001/`
- 复核包：已随PR #11并入main的`knowledge/mechanics/cross-review/v1`（packet_id `26dff7e706583c96ff4aced460fad135c32620c840be5f4745c99851b56d18cf`）
- 当前结论（2026-11-01，U33、U35及U5抽查改判后）：**接受1,265、排除286、不确定0**，以`claude-review.jsonl`为准。`check-003/`是U35后的对照（1,264/286/1），之后U5抽查又改了两组：潮汐猎人·利维坦的渔获伤害格挡改为接受（第1轮只读截断片段漏看），冥魂大帝·吸血灵魂A杖吸血改为排除（用户实测）。`check-001/`是改判前原始结果，`check-002/`是U33后结果。
- U5抽查进度：497组样本（`spot-check-sample.json`）已回读76组，用户判对68、不确定5、错3；其余用户仍在标，结果出来后Claude再改判。

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

- **截断片段**：利维坦的渔获说明错在只读了截断的首条原文。复核排除组时请读完整原文（`hero-registry.json`或dotaconstants对应字段），这是P1的重点。
- **已失效的A杖/魔晶文字**：Valve接口对29个技能保留了升级文字，但`ability_has_scepter/shard`为false（当前没有这项升级），清单`knowledge/mechanics/stale-upgrade-text-v1.json`。第3版证据`knowledge/mechanics/extractions/v3/`去掉了19组（`delta-vs-v2.json`的`removed`，其中第1轮接受17组）。这19组不必再判语义，只需核对“标记为false就视为过时”这条处理是否有误判（如由该升级授予的技能是否被错排）。
- **版本**：U36重新抓取（2026-11-01）确认英文技能数据与10-09快照零改动，最新补丁7.41f（2026-09-15），技能说明就是Valve官网当前文本，很可能对应7.41f（`knowledge/hero-capabilities/snapshots/2026-11-01/`）。若某组原文与你所知的游戏表现不符，按原文判断，并在理由中注明“官网说明可能与游戏实现不符”，留给用户实测，不要按记忆改判。

## 4. 回传方式

- 在`codex-temp`上工作（U25），不要改写`claude-temp`。从最新main开始；PR #12若尚未合并，可按PR #11交接中的`git archive`方法只读导出`origin/claude-temp`。
- 结果写到新目录，例如`knowledge/mechanics/reviews/codex-round-002/`：每组至少记录`review_id`、Codex结论（accept/reject/uncertain）、解释、条件、理由、引用的`fact_id`。现有`scripts/mechanics_cross_review.py compare`只比较“Claude结果↔codex-prior”，如需比较“Codex第2轮↔Claude第1轮”，请扩展工具或另写对照，并说明。
- 与Claude不同的判断逐条写明原因；与用户既有结论冲突的保留给用户裁定。同标签不等于事实认证。
- 不授权合并、推送main、训练或联网采集。

## 5. Claude同时在做的事（避免重复）

> 2026-11-01：漏抽修正、词表v3与v2证据已完成（`knowledge/mechanics/extractions/v2/`，见`docs/knowledge-framework.md`§6）。

按U34，Claude在`claude-temp`上继续：修正漏抽（斯嘉蒂之眼、辉耀闪避、天堂之戟、希瓦光环、斧王·反击螺旋）与抽取规则、按U28–U33出词表v3、补交互记录，再生成第2版证据。Codex复核第1轮结果时不需要处理这些。

## 6. 给Codex的提示词（用户可直接粘贴）

> 请复核Claude第1轮机制证据判断（可选复核，U34）。先读`docs/handoff/mk-codex-review-of-claude.md`和`AGENTS.md`，再读`knowledge/mechanics/reviews/claude-round-001/review-summary.md`。按`codex-review-queue.csv`的顺序，至少完成P1（Claude排除的组和按U33/U35改判的组），排除组要读完整原文，不能只看截断片段。`knowledge/mechanics/extractions/v3/delta-vs-v2.json`里去掉的19组只核对“过时升级文字”这条处理。在`codex-temp`分支工作，从最新main开始；PR #12若未合并，用`git archive origin/claude-temp`只读导出Claude的结果，不要改`claude-temp`。结果写到新目录`knowledge/mechanics/reviews/codex-round-002/`，每组记录review_id、结论（accept/reject/uncertain）、解释、条件、理由、引用的fact_id；与Claude不同的逐条写原因，与用户既有决定冲突的留给用户裁定。技能文字以快照为准（U36确认与官网当前一致，很可能对应7.41f），与记忆不符的注明后留给用户。完成后开PR到main，不要合并，不要推送main，不要联网采集或训练。
