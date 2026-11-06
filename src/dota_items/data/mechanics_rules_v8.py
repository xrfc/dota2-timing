"""Rule additions for rules v8: targets named by hero, with exceptions the user listed (U100).

`target_heroes` names the abilities of every hero except the listed ones. Conditional exceptions
stay targets, and their edges carry the condition, so a reader knows the relation depends on it.
"""

WITH_MANA_COST = "with_mana_cost"


def _mana_cost_subjects(doc):
    return {
        fact["subject"]
        for fact in doc["field_observations"]
        if fact["evidence_kind"] == "field:mana_costs" and any(value > 0 for value in fact["value"])
    }


def expand_rules(rules, heroes, doc):
    """Turn `target_heroes` into explicit target subjects; other rules are returned unchanged."""
    costly = _mana_cost_subjects(doc)
    expanded = []
    for rule in rules:
        spec = rule.get("target_heroes")
        if not spec:
            expanded.append(rule)
            continue
        if spec["abilities"] != WITH_MANA_COST:
            raise ValueError(
                f"{rule['id']}: unsupported target_heroes abilities {spec['abilities']}"
            )
        known = {hero["hero_id"] for hero in heroes}
        named = {*spec["except"], *(entry["hero_id"] for entry in spec.get("conditional", []))}
        if named - known:
            raise ValueError(f"{rule['id']}: unknown hero ids {sorted(named - known)}")
        subjects = sorted(
            ability["name"]
            for hero in heroes
            if hero["hero_id"] not in spec["except"]
            for ability in hero["abilities"]
            if ability["name"] in costly
        )
        expanded.append({**rule, "target_subjects": [*rule.get("target_subjects", []), *subjects]})
    return expanded


def conditional_exceptions(rules):
    """{(rule id, hero id): condition entry} for exceptions that only hold under a condition."""
    return {
        (rule["id"], entry["hero_id"]): entry
        for rule in rules
        for entry in rule.get("target_heroes", {}).get("conditional", [])
    }


def mark_conditional_edges(graph, rules):
    """Edges whose hero is an exception only under a condition get that condition attached."""
    marks = conditional_exceptions(rules)
    edges = []
    for edge in graph["item_to_hero"]:
        mark = marks.get((edge["rule"], edge["hero_id"]))
        edges.append({**edge, "exception": mark} if mark else edge)
    return {**graph, "item_to_hero": edges}
