# MK-T5 英雄机制档案

全部由脚本生成，不手填，当前版本见下。`?`表示只有AI一致，用户尚未确认。

- `derived-v17/`（当前，草稿，U126）：由`scripts/build_mechanics_derived_v17.py`从事实v26生成；标签改为“无视减益免疫”（`data.mechanics_profiles_v5`）。
- `derived-v16/`（已被v17取代，U120、U121）：由`scripts/build_mechanics_derived_v16.py`从事实v25和特性映射v6生成；新增加速，保命特性加上用户确认的逃跑技能。
- `derived-v15/`（已被v16取代，U119）：由`scripts/build_mechanics_derived_v15.py`从事实v24生成；动能栅栏记了减速。
- `derived-v14/`（已被v15取代，U118）：由`scripts/build_mechanics_derived_v14.py`从事实v23和特性映射v5生成；神谕者加入魔法爆发，狼人不再算自身闪避。
- `derived-v13/`（已被v14取代，U117）：由`scripts/build_mechanics_derived_v13.py`从事实v22和规则v12生成；虚妄之诺加了免死，新增R24（淘汰之刃克制免死）。
- `derived-v12/`（已被v13取代，U114）：由`scripts/build_mechanics_derived_v12.py`从事实v21生成；只有17行治疗事实的依据变为用户确认，关联边不变。
- `derived-v11/`（已被v12取代，U113）：由`scripts/build_mechanics_derived_v11.py`从事实v20生成；内容和v10相同，只换来源版本。
- `derived-v10/`（已被v11取代）：由`scripts/build_mechanics_derived_v10.py`生成；在v9基础上，装备档案的每条关联保留逐个技能的生效条件（PR #17复核）。英雄档案、克制关系图、英雄特性和v9相同。
- `derived-v9/`（已被v10取代，U113）：由`scripts/build_mechanics_derived_v9.py`从事实v19和规则v11生成；内容和v8相同，只换来源版本（规则字段改为严格检查）。
- `derived-v8/`（已被v9取代）：由`scripts/build_mechanics_derived_v8.py`从事实v18和规则v10生成；英雄特性改为`hero-traits-v3.json`（数量，见`knowledge/hero-traits/README.md`）；R12例外增加后共3,575条关联。
- `derived-v7/`（已被取代）：由`scripts/build_mechanics_derived_v7.py`从事实v17生成，关联带生效条件，页面在技能名后写“需A杖”“有A杖时不成立”等；3,605条关联中211条带条件。
- `derived-v6/`（已被取代）：由`scripts/build_mechanics_derived_v6.py`从事实v16和规则v9（展开后）生成。关联条目带结构化状态（见`knowledge/mechanics/README.md`），页面写“候选机制关联”。
- `derived-v5/`（已被取代）：由`scripts/build_mechanics_derived_v5.py`从事实v15、词表v13和规则v8（展开后）生成，结构同v3。3,607条边，140条两端都确认，没有待定规则了；R12边上若带`exception`，表示该英雄有A杖时是例外。档案页还不显示`exception`。Black Grimoire已移出装备。
- `derived-v4/`：基于v14，已被取代，保留不改。3,376条边只有124条两端都确认，204条来自待定规则。
- `derived-v3/`：基于v13，已被取代，保留不改。由`scripts/build_mechanics_derived_v3.py`从事实v13、词表v13和规则v7生成。127个英雄，143件现役装备。比v2多了：每条边的`relation`和`status`；证据里的`condition_notes`；档案里的“【待定】”和部分“AI说明条件”；熊灵的技能。
  - 局限：3,376条边只有17条两端都确认，其中204条来自待定规则R13；只是候选。档案只显示含夜晚、层数、概率等关键词的条件说明，完整文字在`facts-v13.json`。U5抽查还没做完。
- `derived-v2/`：基于v12，已被取代，保留不改。由`scripts/build_mechanics_derived_v2.py`从事实v12、词表v11和规则v5生成。127个英雄，143件现役装备，文件结构同`derived-v1/`。
  - 局限：3,421条装备到英雄的边只有9条两端都确认，不能当结论用；U5抽查还没做。
- `derived-v1/`：基于v10，已被取代，保留不改。
  - `heroes/`、`hero-profiles.json`：127个英雄。
  - `items/`、`item-profiles.json`：132件有机制记录的现役装备。
  - `counter-graph.json`：20条规则的来源、目标和证据链；`item_to_hero`是装备到英雄的边，两端都有用户或字段依据才算`confirmed`。
  - `hero-traits-v2.json`：映射见`knowledge/hero-traits/trait-mapping-v2.json`，含与v1的差异。
  - 局限：事实层有漏记（`reviews/recall-check-001/`），2,561条装备到英雄的边只有8条两端都确认（此处原写9条，2026-11-04按文件核对改正），不能当结论用。
- `heroes-v1/`：基于v9的127个英雄档案，已被取代，保留不改。
- `sample-2026-11-07/`：早期3个样例，已被取代，保留不改。

规则只说机制关系，不说“该出”。
