"""Profile relations with conditions (U104): which version of each ability a relation needs.

Builds on `mechanics_profiles_v2`; each relation entry gains `own_conditions` per ability and a
`conditional` flag, and pages show notes such as "需A杖" or "有A杖时不成立".
"""

from dota_items.data import mechanics_profiles_v2 as v2
from dota_items.data.mechanics_conditions import is_conditional, label

DRAFT = {**v2.DRAFT, "conditions": "每条关联带生效条件；条件由事实行和规则例外算出"}


def _conditions(graph):
    found = {}
    for rule in graph["rules"]:
        for side in ("sources", "targets"):
            for entry in rule[side]:
                found[(rule["id"], side, entry["subject"])] = entry.get("conditions", [])
    return found


def _with(entries, found, side):
    out = []
    for entry in entries:
        own = {s: found.get((entry["rule"], side, s), []) for s in entry["own_subjects"]}
        out.append(
            {
                **entry,
                "own_conditions": own,
                "conditional": all(is_conditional(c) for c in own.values()) if own else False,
            }
        )
    return out


def hero_relations(hero, graph, item_names):
    relations = v2.hero_relations(hero, graph, item_names)
    found = _conditions(graph)
    return {
        "targeted_by": _with(relations["targeted_by"], found, "targets"),
        "targeting": _with(relations["targeting"], found, "sources"),
    }


def item_relations(subject, graph):
    return v2.item_relations(subject, graph)


def _names(entry):
    shown = []
    for subject, name in zip(entry["own_subjects"], entry["own_zh"], strict=True):
        note = label(entry["own_conditions"][subject])
        shown.append(f"{name}（{note}）" if note else name)
    return "、".join(shown[:8])


def render_hero_relations(lines, relations):
    out = []
    for line in lines:
        if line in ("## 会被什么克制", "## 能克制什么"):
            break
        out.append(line)
    out += ["## 候选机制关联：可能针对本英雄的", "", *v2.HEADER]
    out.insert(
        len(out) - 1, "> 括号里是生效条件，如“需A杖”“有A杖时不成立”；没写就是基础版和装备都成立。"
    )
    for entry in relations["targeted_by"]:
        items = "、".join(entry["item_zh"][:8]) or "无装备来源"
        out.append(
            f"- {entry['rule']} {v2._tag(entry)} {entry['zh']}：涉及{_names(entry)}；装备：{items}"
        )
    out += ["", "## 候选机制关联：本英雄可能针对的", ""]
    for entry in relations["targeting"]:
        out.append(f"- {entry['rule']} {v2._tag(entry)} {entry['zh']}：靠{_names(entry)}")
    return "\n".join(out) + "\n"


render_item_relations = v2.render_item_relations
