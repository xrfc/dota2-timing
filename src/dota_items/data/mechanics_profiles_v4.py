"""Item profiles with conditions (review of PR #17): what each related ability needs.

`mechanics_profiles_v3` gave hero profiles per-ability conditions but item profiles kept the
v2 entries, so Linken's Sphere listed Gush without "有A杖时不成立". Here every item relation
carries the conditions of each subject on the other side, and of the item itself, and the
page shows the conditional ones. Hero profiles are unchanged from v3.
"""

from dota_items.data import mechanics_profiles_v2 as v2
from dota_items.data.mechanics_conditions import is_conditional, label
from dota_items.data.mechanics_profiles_v3 import DRAFT, hero_relations, render_hero_relations

__all__ = ["DRAFT", "hero_relations", "item_relations", "render_hero_relations"]


def _side(rule, side):
    return {entry["subject"]: entry.get("conditions", []) for entry in rule[side]}


def item_relations(subject, graph):
    """v2 item relations, each with the conditions of every subject it names."""
    base = v2.item_relations(subject, graph)
    rules = {rule["id"]: rule for rule in graph["rules"]}
    targeting = []
    for entry in base["targeting"]:
        rule = rules[entry["rule"]]
        conditions = _side(rule, "targets")
        targeting.append(
            {
                **entry,
                "own_conditions": _side(rule, "sources").get(subject, []),
                "target_conditions": {s: conditions[s] for s in entry["target_subjects"]},
                "conditional_targets": [
                    s for s in entry["target_subjects"] if is_conditional(conditions[s])
                ],
            }
        )
    targeted = []
    for entry in base["targeted_by"]:
        rule = rules[entry["rule"]]
        conditions = _side(rule, "sources")
        targeted.append(
            {
                **entry,
                "own_conditions": _side(rule, "targets").get(subject, []),
                "source_conditions": {s: conditions[s] for s in entry["item_sources"]},
            }
        )
    return {"targeting": targeting, "targeted_by": targeted}


def _conditional_names(entry, graph_names):
    shown = [
        f"{graph_names.get(s, s)}（{label(entry['target_conditions'][s])}）"
        for s in entry["conditional_targets"][:8]
    ]
    more = (
        f"等{len(entry['conditional_targets'])}个" if len(entry["conditional_targets"]) > 8 else ""
    )
    return "、".join(shown) + more


def render_item_relations(lines, relations, names):
    """v2 page plus a line per relation listing the targets that only hold under a condition.

    `names` maps a subject to "英雄·技能" so the condition line can be read on its own.
    """
    page = v2.render_item_relations(lines, relations).rstrip("\n").split("\n")
    out = []
    targeting = iter(relations["targeting"])
    in_targeting = False
    for line in page:
        out.append(line)
        if line == "## 候选机制关联：本装备可能针对的":
            in_targeting = True
        elif line.startswith("## "):
            in_targeting = False
        elif in_targeting and line.startswith("- "):
            entry = next(targeting)
            if entry["conditional_targets"]:
                out.append(f"  - 有条件的目标：{_conditional_names(entry, names)}")
    return "\n".join(out) + "\n"
