# MK-T3交接：请Claude复核全部机制证据（U32）

用户要求：“能不能让两个ai相互复核，你把这些都列出来推送pr，我交给Claude复核”。本文件是交接入口；当前源PR为 **[PR #11](https://github.com/xrfc/dota2-timing/pull/11)**，分支`codex-temp`。Claude由用户另行启动，本仓库没有自动调用Claude，也没有Claude已完成复核的结果。

## 1. 完整清单在哪里

入口：[复核包README](../../knowledge/mechanics/cross-review/v1/README.md)。所有旧输入和原始事实保留，包的`manifest.json`给出输入、实现、输出的SHA-256及`packet_id`。

| 文件（都在`knowledge/mechanics/cross-review/v1/`） | 内容 |
|---|---|
| `index.csv` | **1,551组**完整索引：编号、英雄名、技能/装备名、机制、生效条件、Codex是否已人工审过 |
| `mechanisms/*.md` | **45个机制分册**，列出全部候选、中文名、原文及来源指针，适合逐册阅读 |
| `cases.jsonl` | 1,551组机器可读记录，完整承载**2,801条**待语义复核证据；每条保留原字段值/完整来源文本与截取引用 |
| `subjects.jsonl` | **943个对象**的完整上下文：734技能、209装备清单候选；含中英文说明、注释、升级文字、原始字段等 |
| `field-observations.jsonl` | 其余**2,006条**结构化观测，附中文名；与候选证据合计覆盖全部**4,807条**原始事实记录 |
| `coverage.json` | 45个机制覆盖情况、107个无命中对象、63个无可扫描文字对象；“没命中”不是“没有机制” |
| `vocabulary.json` | 当前词表v2，包含U31的指向方式/林肯/莲花拆分定义 |
| `claude-template.jsonl` | 全部1,551组的空白回传模板；`decision=null`表示尚未审阅 |
| `codex-prior.json` | Codex已人工复核的**24组**及合并解释，未覆盖的**1,527组明确未审** |
| `known-user-feedback.json` | 已收到的8条用户抽查、并列条件澄清、魂断交互补充及其来源 |
| `summary.json` / `manifest.json` | 数量汇总和完整性收据 |

这不是“Codex已经审完1,551组”的交付。Claude审阅后，没有Codex判定的1,527组要回到Codex继续审；比较工具不会凭空补出Codex同意。

## 2. 复核顺序与判定要求

1. 读`AGENTS.md`、本文件、当前词表和[U31](../decisions/2026-11-01-targeting-interactions.md)。定义已经由用户决定，不能为了提高一致率临时改定义。
2. 按机制或英雄阅读`cases.jsonl`和`subjects.jsonl`，**先独立写判断与条件**，再看`codex-prior.json`及用户反馈对照。仓库并未技术隔离这些文件，不能把这称为正式盲评。
3. 每组判断是否由该对象施加该机制：分清主语/宾语、作用方向、基础能力/升级能力、施法触发/外部中断条件、正面事实/否定描述。要阅读完整来源文本，不能只看截取引用。
4. `accept`＝来源支持这一组附条件解释；`reject`＝这段证据不支持此归类或归属；`uncertain`＝证据不足、存在冲突或需要用户游戏知识。排除一条证据不等于证明所有版本都无此机制。
5. 检查字段附表的语义边界和覆盖缺口。结构化值核验通过不等于游戏机制自动认证。发现遗漏/新候选写独立`coverage-findings.md`，带对象、机制、原文、文件及JSON指针，不改现有case ID，也不把新候选硬塞进其他组。
6. 写完独立判断再与Codex/用户记录比较。用户已经确认的结论仍保留原来源；若当前文本与用户知识冲突，报告版本/来源差异，不静默覆盖。两AI同标签后仍要核对条件和解释，不能自动升级成“真值”或训练许可。

## 3. 必须注意的具体问题

- 幻影长矛手（猴子）·并列：基础被动无魔晶也能攻击产生幻象；魔晶另增主动隐身并产生复制幻象。局部升级条件不能限制整个技能。
- 恐怖利刃（TB）·魂断：指向方式、林肯、莲花各记一项。用户已报告会触发林肯和莲花，标为`user_reported`；不是原快照文字。魂断不提供减益免疫已获用户确认。
- 影之灵龛、魂之灵瓮：社区快照同时写`Unit Target`、`Both`与“不触发spell block/spell reflect”，是定义拆分的例子。用户所说“大中小骨灰”尚未逐一映射，不猜测第三种。
- 蝙蝠骑士·燃烧枷锁：被闪烁打断不是自己提供闪烁；拖行敌人和自身位移是两类机制。
- 沉默术士·全领域静默、斯拉达·侵蚀雾霭：影响/揭示隐身目标，不等于给予隐身。
- 修补匠·激光：降低当前/最大生命值不等于降低治疗。`health`被`heal`宽泛匹配会误报。
- 玛西·特快专递与陨星锤：召来已有信使、召来伤害效果不自动等于创造可控召唤物。
- 驱散：施加强/弱驱散与自身效果可驱散性分别记录；`dispellable=0`不是不可驱散。
- 破坏：施加破坏与自身关键被动受破坏影响分别记录；有被动位不足以认证关键被动。海妖外壳/法力损毁的用户例子不能伪装成官方文字。
- 减益免疫与穿透免疫分开，熊战士·激怒不应从穿透枚举推出自身免疫；闪避与致盲分开。
- 文本处理已知缺陷：小数`0.75`可能被截为`0.`；`don't`等否定可能漏识别。`cases.jsonl`的`evidence[].value`和对象上下文保留完整文本，不能只靠`quote`判断。
- 全部快照`patch_verified=false`；装备说明是OpenDota社区来源；209个装备条目只是价格/中立/图纸筛选代理，包含历史/特殊条目，不认证当前商店范围。

## 4. Claude如何读取尚未合并的PR

用户尚未要求合并PR #11。按U25维护自己的`claude-temp`，不要推送或改写`codex-temp`，也不要直接把另一个AI的临时分支作为开发基线。可以把PR头部导出到只读输入目录：

```bash
set -e
git fetch origin
review_snapshot_dir=$(mktemp -d)
git rev-parse origin/codex-temp > "$review_snapshot_dir/source-commit.txt"
git archive origin/codex-temp | tar -x -C "$review_snapshot_dir"
review_packet_dir="$review_snapshot_dir/knowledge/mechanics/cross-review/v1"
PYTHONPATH="$review_snapshot_dir/src" python "$review_snapshot_dir/scripts/mechanics_cross_review.py" verify --packet "$review_packet_dir"
```

此处`python`使用已配置的项目解释器；复用环境，不为复核添加新依赖。该工具只使用标准库及仓库模块；完整工程检查仍按项目既有环境执行。若输入哈希不符，先核对拿到的PR快照，不修改收据来绕过。

选择一个不存在的结果目录，在自己的工作分支保存结果。示例：

```bash
mkdir -p knowledge/mechanics/reviews
review_output_dir="$PWD/knowledge/mechanics/reviews/claude-round-001"
mkdir "$review_output_dir"
cp "$review_packet_dir/claude-template.jsonl" "$review_output_dir/claude-review.jsonl"
```

逐组编辑模板副本，保留`packet_id`、`review_id`、`reviewer`，填写：

```json
{
  "packet_id": "保留模板中的实际值",
  "review_id": "保留模板中的实际值",
  "reviewer": "Claude",
  "decision": "accept",
  "interpretation_zh": "该对象施加什么机制，作用于谁",
  "conditions_zh": "基础/魔晶/A杖、目标类型、触发时机；未知也明确写出",
  "reason_zh": "原文如何支持或不支持上述解释；补充来源用路径和原文注明",
  "evidence_fact_ids": ["引用本组已有的实际fact_id"]
}
```

不要批量把空白填成accept。接受/排除至少引用本组一个证据ID，字段变动、其他组证据、未知/重复ID会被拒绝。证据不足可以写`uncertain`并说明缺口；原模板null仍表示未审。额外新证据/缺漏放在`coverage-findings.md`，与本组判断理由互相引用。

## 5. 校验、对照与回传

允许中途交部分结果，但必须报告实际已判定数量。每次校验使用新的输出目录：

```bash
PYTHONPATH="$review_snapshot_dir/src" python "$review_snapshot_dir/scripts/mechanics_cross_review.py" compare \
  --packet "$review_packet_dir" \
  --review "$review_output_dir/claude-review.jsonl" \
  --output "$review_output_dir/check-001"
```

正式宣告全量完成时，使用一个新目录并加`--require-complete`；该参数要求1,551组都有accept/reject/uncertain判断，缺行、null或重复行均不能冒充完成。`uncertain`算已审阅，仍不算事实已认证。

比对结果逐项给出：

| 状态 | 含义/下一步 |
|---|---|
| `pending_claude` | Claude缺行或未判定 |
| `needs_codex_review` | Claude有判断、Codex未审；回给Codex复核 |
| `needs_evidence_review` | 存在uncertain，补读来源或汇总待决 |
| `same_label_check_conditions` | 标签相同，但仍须比对解释/条件；不能自动关闭 |
| `label_disagreement` | 标签不同，逐项读证据定位原因 |
| `conflicts_with_user_label=true` | 与用户既有二元结论冲突，保留分歧供用户裁定 |

回传以下文件及自己的PR链接：

- `claude-review.jsonl`：完整或明确标注部分完成的判断。
- `coverage-findings.md`：字段观测异常、漏抽机制、新证据、补丁/来源冲突；没有发现也明确说明检查范围。
- `review-summary.md`：审阅数量、各结论数、主要错误类型、未决问题、包ID和源提交。
- 最后一次`comparison.json`与对照README；报告中相同标签数不是游戏准确率。

Codex拿到回传后复核Claude独有判断，检查双方条件差异并汇总分歧。本轮改为先交叉复核，不再在交接前逐24组要求用户答题；定义改变与无法据来源解决的分歧仍交用户。U32没有明确取消长期U5抽查比例，不自动把两个AI同意视为用户批准。

所有结果提交自己的临时分支并开/更新PR；本任务不授权合并、推送main、训练或联网数据采集。
