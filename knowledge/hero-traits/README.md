# 英雄特性表（U23）

- `hero-traits-v1.json`：9个维度的英雄标签（助手标注v1，待用户抽查）。每条有技能证据与置信度；`targeted_spells`不在文件中标注，由`dota_items.data.hero_traits.targeted()`按官方原始枚举计算。
- 读取一律用`dota_items.data.hero_traits.load_traits(doc, registry_heroes)`：校验英雄、技能名均在`knowledge/hero-capabilities/hero-registry.json`中，禁止重复。
- 分析与抽查清单：`docs/hero-traits-analysis.md`。修改须记决策并升版本（v2…），旧版本不覆盖。
- `trait-mapping-v4.json`（当前，U105、U106）：特性存数量，每个英雄每个特性都有“基础数”和“含升级数”，0也记。硬控只算眩晕、妖术、嘲讽、睡眠、蛊惑、恐惧；沉默单列；机动性=自身位移＋无视地形；法力依赖来自R12的例外名单；魔法爆发是用户列的33个英雄（U107）。结果在`knowledge/mechanics/profiles/derived-v11/hero-traits-v3.json`（v8–v10中相同）。
- `trait-mapping-v3.json`（已被取代）：v2各维度由哪些机制算出（助手草稿，待用户看）。结果在`knowledge/mechanics/profiles/derived-v8/hero-traits-v2.json`，并含与v1的差异。映射未经用户审阅，不能替代v1。
