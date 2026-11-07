"""Rule relations that know when they hold (U104).

Fact rows already carry a condition (base, scepter, shard, item). A rule match is kept per
condition: `when` says which version of the ability has the mechanism, `unless` says which upgrade
turns it off. Exceptions that switch a mechanism off come from `condition_exceptions` in the
facts or from a rule's conditional hero exceptions; a rejected upgrade row is never read as one,
because it usually only means the upgrade adds nothing new.
"""

from dota_items.data.mechanics_facts_v12 import condition_label

ALWAYS = {"base", "item", "any"}
UPGRADES = {"scepter", "shard"}
LABELS = {"scepter": "需A杖", "shard": "需魔晶"}
UNLESS_LABELS = {"scepter": "有A杖时不成立", "shard": "有魔晶时不成立"}


def _whens(doc, subject, mechanisms):
    return sorted(
        {
            condition_label(row["condition"])
            for row in doc["rows"]
            if row["subject"] == subject
            and row["mechanism"] in mechanisms
            and row["decision"] == "accept"
        }
    )


def _side(rule, side, subjects, doc, unless):
    mechanisms = set(rule.get(f"{side}_mechanisms", []))
    listed = set(rule.get(f"{side}_subjects", []))
    out = {}
    for subject in subjects:
        whens = _whens(doc, subject, mechanisms) if mechanisms else []
        if subject in listed or not whens:
            whens = sorted({*whens, "any"})
        offs = sorted(unless.get(subject, set()))
        out[subject] = [{"when": when, "unless": offs if when in ALWAYS else []} for when in whens]
    return out


def _unless(rule, doc, heroes):
    offs = {}
    for entry in doc.get("condition_exceptions", []):
        if entry["mechanism"] in rule.get("target_mechanisms", []):
            offs.setdefault(entry["subject"], set()).add(entry["unless"])
    owner = {a["name"]: hero["hero_id"] for hero in heroes for a in hero["abilities"]}
    for entry in rule.get("target_heroes", {}).get("conditional", []):
        upgrade = {"A杖": "scepter", "魔晶": "shard"}[entry["condition"]]
        for subject, hero_id in owner.items():
            if hero_id == entry["hero_id"]:
                offs.setdefault(subject, set()).add(upgrade)
    return offs


def add_conditions(evaluation, rules, doc, heroes):
    """Give every evaluated rule the conditions of each source and target."""
    by_id = {rule["id"]: rule for rule in rules}
    out = []
    for entry in evaluation["rules"]:
        rule = by_id[entry["id"]]
        unless = _unless(rule, doc, heroes)
        out.append(
            {
                **entry,
                "source_conditions": _side(rule, "source", entry["sources"], doc, {}),
                "target_conditions": _side(rule, "target", entry["targets"], doc, unless),
            }
        )
    return {**evaluation, "schema": "mechanics-rules-evaluation/3", "rules": out}


def holds(entries, upgrades=None):
    """True, False or None (unknown) for one subject, given which upgrades are known.

    `upgrades` is a set such as {"scepter"}; None means nothing is known about upgrades.
    """
    results = []
    for entry in entries:
        if entry["when"] in ALWAYS:
            if not entry["unless"]:
                return True
            if upgrades is None:
                results.append(None)
            else:
                results.append(not (set(entry["unless"]) & upgrades))
        elif upgrades is None:
            results.append(None)
        else:
            results.append(entry["when"] in upgrades)
    if any(result is True for result in results):
        return True
    return None if None in results else False


def is_conditional(entries):
    return holds(entries) is not True


def label(entries):
    """Short Chinese note such as "需A杖" or "有A杖时不成立"; empty when it always holds."""
    if not is_conditional(entries):
        return ""
    parts = []
    for entry in entries:
        if entry["when"] in LABELS:
            parts.append(LABELS[entry["when"]])
        parts += [UNLESS_LABELS[off] for off in entry["unless"]]
    return "，".join(dict.fromkeys(parts))


def annotate_graph_conditions(graph, evaluation):
    """Carry conditions onto graph entries and edges; an edge holds if any target ability does."""
    by_id = {rule["id"]: rule for rule in evaluation["rules"]}
    rules = []
    for rule in graph["rules"]:
        found = by_id[rule["id"]]
        sides = {}
        for side, key in (("sources", "source_conditions"), ("targets", "target_conditions")):
            sides[side] = [
                {**entry, "conditions": found[key].get(entry["subject"], [])}
                for entry in rule[side]
            ]
        rules.append({**rule, **sides})
    edges = []
    for edge in graph["item_to_hero"]:
        found = by_id[edge["rule"]]
        targets = {a: found["target_conditions"].get(a, []) for a in edge["abilities"]}
        source = found["source_conditions"].get(edge["item"], [])
        always = not is_conditional(source) and any(not is_conditional(t) for t in targets.values())
        edges.append(
            {
                **edge,
                "conditions": {"source": source, "targets": targets},
                "conditional": not always,
            }
        )
    return {**graph, "schema": "mechanics-counter-graph/3", "rules": rules, "item_to_hero": edges}


def edge_holds(edge, upgrades=None):
    """Whether an item-to-hero edge holds given the target hero's known upgrades.

    The item side has no hero upgrades, so it is read as known; None means it depends.
    """
    if holds(edge["conditions"]["source"], set()) is False:
        return False
    results = [holds(entries, upgrades) for entries in edge["conditions"]["targets"].values()]
    if True in results:
        return True
    return None if None in results else False
