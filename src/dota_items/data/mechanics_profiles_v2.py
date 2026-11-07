"""Profile pages that keep each rule relation's status as data, not only in its title (U101).

Relations are candidates: a rule matched a source set with a target set. Two confirmed ends do
not make the pair verified. Pages say so, and programs read `status`, never the Chinese name.
"""

from dota_items.data.mechanics_graph_v2 import STATUS_PENDING

DRAFT = {
    "status": "draft",
    "relations": "candidate",
    "relation_verified": False,
    "note_zh": "规则算出的候选机制关联，未逐对核对条件和例外；两端事实都确认也不代表关联已验证",
}


def _rule_fields(rule):
    return {
        "rule": rule["id"],
        "zh": rule["zh"],
        "relation": rule["relation"],
        "status": rule["status"],
        "pending": rule.get("pending"),
        "not_evaluated": rule.get("not_evaluated", []),
        "relation_verified": False,
    }


def hero_relations(hero, graph, item_names):
    """Candidate relations touching one hero, with subject ids for tracing back to facts."""
    names = {ability["name"] for ability in hero["abilities"]}
    zh = {ability["name"]: ability["name_zh"] for ability in hero["abilities"]}
    exceptions = {
        (edge["rule"], edge["hero_id"]): edge["exception"]
        for edge in graph["item_to_hero"]
        if edge.get("exception")
    }
    targeted, targeting = [], []
    for rule in graph["rules"]:
        targets = [t for t in rule["targets"] if t["subject"] in names]
        sources = [s for s in rule["sources"] if s["subject"] in names]
        if targets:
            items = [s for s in rule["sources"] if s["kind"] == "item"]
            targeted.append(
                {
                    **_rule_fields(rule),
                    "own_subjects": [t["subject"] for t in targets],
                    "own_zh": [zh[t["subject"]] for t in targets],
                    "item_subjects": [s["subject"] for s in items],
                    "item_zh": sorted(item_names.get(s["subject"], s["name_zh"]) for s in items),
                    "ability_sources": sum(1 for s in rule["sources"] if s["kind"] == "ability"),
                    "own_facts_confirmed": any(t["confirmed"] for t in targets),
                    "exception": exceptions.get((rule["id"], hero["hero_id"])),
                }
            )
        if sources:
            targeting.append(
                {
                    **_rule_fields(rule),
                    "own_subjects": [s["subject"] for s in sources],
                    "own_zh": [zh[s["subject"]] for s in sources],
                    "own_facts_confirmed": any(s["confirmed"] for s in sources),
                }
            )
    return {"targeted_by": targeted, "targeting": targeting}


def item_relations(subject, graph):
    """Candidate relations touching one item."""
    targeting, targeted = [], []
    for rule in graph["rules"]:
        if any(s["subject"] == subject for s in rule["sources"]):
            heroes = sorted({t["hero_zh"] for t in rule["targets"] if t["kind"] == "ability"})
            targeting.append(
                {
                    **_rule_fields(rule),
                    "target_subjects": [t["subject"] for t in rule["targets"]],
                    "heroes_zh": heroes,
                }
            )
        if any(t["subject"] == subject for t in rule["targets"]):
            targeted.append(
                {
                    **_rule_fields(rule),
                    "item_sources": [s["subject"] for s in rule["sources"] if s["kind"] == "item"],
                    "ability_sources": sum(1 for s in rule["sources"] if s["kind"] == "ability"),
                }
            )
    return {"targeting": targeting, "targeted_by": targeted}


def _tag(entry):
    tags = ["待定" if entry["status"] == STATUS_PENDING else "候选"]
    if entry.get("not_evaluated"):
        tags.append("部分字段未计算")
    if entry.get("exception"):
        tags.append(f"{entry['exception']['condition']}时例外")
    return "【" + "，".join(tags) + "】"


HEADER = [
    "> 草稿。关联由规则算出，是候选，没有逐对核对条件和例外。",
    "> `?`表示这条事实只有AI一致；事实都确认也不代表这条关联已经验证。",
    "",
]


def render_hero_relations(lines, relations):
    """Append relation sections to an existing hero page; the fact part stays as before."""
    out = []
    for line in lines:
        if line in ("## 会被什么克制", "## 能克制什么"):
            break
        out.append(line)
    out += ["## 候选机制关联：可能针对本英雄的", "", *HEADER]
    for entry in relations["targeted_by"]:
        items = "、".join(entry["item_zh"][:8]) or "无装备来源"
        own = "、".join(entry["own_zh"][:8])
        out.append(f"- {entry['rule']} {_tag(entry)} {entry['zh']}：涉及{own}；装备：{items}")
    out += ["", "## 候选机制关联：本英雄可能针对的", ""]
    for entry in relations["targeting"]:
        out.append(
            f"- {entry['rule']} {_tag(entry)} {entry['zh']}：靠{'、'.join(entry['own_zh'][:8])}"
        )
    return "\n".join(out) + "\n"


def render_item_relations(lines, relations):
    out = []
    for line in lines:
        if line in ("## 能克制什么", "## 会被什么克制"):
            break
        out.append(line)
    out += ["## 候选机制关联：本装备可能针对的", "", *HEADER]
    for entry in relations["targeting"]:
        shown = "、".join(entry["heroes_zh"][:12]) or "规则未列出目标"
        more = f"等{len(entry['heroes_zh'])}人" if len(entry["heroes_zh"]) > 12 else ""
        out.append(f"- {entry['rule']} {_tag(entry)} {entry['zh']}：{shown}{more}")
    out += ["", "## 候选机制关联：可能针对本装备的", ""]
    for entry in relations["targeted_by"]:
        out.append(
            f"- {entry['rule']} {_tag(entry)} {entry['zh']}："
            f"装备来源{len(entry['item_sources'])}件；技能来源{entry['ability_sources']}个"
        )
    return "\n".join(out) + "\n"
