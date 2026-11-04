# MK-T5 英雄机制档案

由`scripts/build_mechanics_profiles.py`从`extractions/v9/`和`rules-v3`自动生成，不手填。`?`表示只有AI一致，用户尚未确认。

- `derived-v1/`（当前，草稿）：由`scripts/build_mechanics_derived.py`从事实v10和规则v4生成。
  - `heroes/`、`hero-profiles.json`：127个英雄。
  - `items/`、`item-profiles.json`：132件有机制记录的现役装备。
  - `counter-graph.json`：20条规则的来源、目标和证据链；`item_to_hero`是装备到英雄的边，两端都有用户或字段依据才算`confirmed`。
  - `hero-traits-v2.json`：映射见`knowledge/hero-traits/trait-mapping-v2.json`，含与v1的差异。
  - 局限：事实层有漏记（`reviews/recall-check-001/`），2,561条装备到英雄的边只有9条两端都确认，不能当结论用。
- `heroes-v1/`：基于v9的127个英雄档案，已被取代，保留不改。
- `sample-2026-11-07/`：早期3个样例，已被取代，保留不改。

规则只说机制关系，不说“该出”。
