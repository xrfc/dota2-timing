"""MK-T5 derived layer additions: say what a rule edge is, and what it is not.

A rule yields a source set and a target set, so an edge is a candidate for review. It does not
prove the pair works under every condition. Edges from pending rules are labelled and left out
of `usable_edges` by default, so a consumer cannot take them for settled relations by accident.
"""

STATUS_CANDIDATE = "candidate"
STATUS_PENDING = "pending"
SEMANTICS = "候选：规则只算来源集合和目标集合，没有逐对核对条件和例外，不等于每一对都成立"
NOT_EVALUATED = ("pairs", "target_exempt_mechanisms", "parameters")


def rule_status(rule):
    return STATUS_PENDING if rule.get("pending") else STATUS_CANDIDATE


def annotate_evaluation(evaluation, rules):
    """Add relation, status and unevaluated fields to each evaluated rule."""
    by_id = {rule["id"]: rule for rule in rules}
    annotated = []
    for entry in evaluation["rules"]:
        rule = by_id[entry["id"]]
        annotated.append(
            {
                **entry,
                "relation": rule["relation"],
                "status": rule_status(rule),
                "pending": rule.get("pending"),
                "not_evaluated": [name for name in NOT_EVALUATED if name in rule],
            }
        )
    return {
        **evaluation,
        "schema": "mechanics-rules-evaluation/2",
        "semantics": SEMANTICS,
        "rules": annotated,
    }


def _condition_notes(doc):
    """Condition notes per accepted row, in the order the graph lists that row's evidence."""
    notes = {}
    for row in doc["rows"]:
        if row["decision"] == "accept":
            notes.setdefault((row["subject"], row["mechanism"]), []).append(
                [note["text"] for note in row["condition_notes"]]
            )
    return notes


def _with_condition_notes(entry, notes):
    """Give each evidence item the notes of its own row, not of every row on that mechanism."""
    used = {}
    evidence = []
    for item in entry["evidence"]:
        rows = notes.get((entry["subject"], item["via"]), [])
        index = used.get(item["via"], 0)
        used[item["via"]] = index + 1
        evidence.append({**item, "condition_notes": rows[index] if index < len(rows) else []})
    return {**entry, "evidence": evidence}


def annotate_graph(graph, rules, doc):
    """Carry relation and status onto edges, and condition notes onto evidence."""
    by_id = {rule["id"]: rule for rule in rules}
    notes = _condition_notes(doc)
    out_rules = []
    for rule in graph["rules"]:
        source = by_id[rule["id"]]
        sides = {
            side: [_with_condition_notes(entry, notes) for entry in rule[side]]
            for side in ("sources", "targets")
        }
        out_rules.append(
            {
                **rule,
                **sides,
                "status": rule_status(source),
                "not_evaluated": [name for name in NOT_EVALUATED if name in source],
            }
        )
    edges = [
        {
            **edge,
            "relation": by_id[edge["rule"]]["relation"],
            "status": rule_status(by_id[edge["rule"]]),
            "pending": by_id[edge["rule"]].get("pending"),
        }
        for edge in graph["item_to_hero"]
    ]
    return {
        **graph,
        "schema": "mechanics-counter-graph/2",
        "semantics": SEMANTICS,
        "rules": out_rules,
        "item_to_hero": edges,
    }


def usable_edges(graph, *, confirmed_only=False, include_pending=False):
    """Edges a consumer may read; pending ones need an explicit request."""
    if graph.get("schema") != "mechanics-counter-graph/2":
        raise ValueError("Needs a counter graph that records edge status")
    return [
        edge
        for edge in graph["item_to_hero"]
        if (include_pending or edge["status"] != STATUS_PENDING)
        and (edge["confirmed"] or not confirmed_only)
    ]


def hero_relations(graph, source_hero, target_hero, *, include_pending=False):
    """Rules where one hero's abilities act on another's, with relation and status."""
    if graph.get("schema") != "mechanics-counter-graph/2":
        raise ValueError("Needs a counter graph that records edge status")
    found = []
    for rule in graph["rules"]:
        if rule["status"] == STATUS_PENDING and not include_pending:
            continue
        sources = [s for s in rule["sources"] if s.get("hero_id") == source_hero]
        targets = [t for t in rule["targets"] if t.get("hero_id") == target_hero]
        if sources and targets:
            found.append(
                {
                    "rule": rule["id"],
                    "zh": rule["zh"],
                    "relation": rule["relation"],
                    "status": rule["status"],
                    "sources": [s["subject"] for s in sources],
                    "targets": [t["subject"] for t in targets],
                    "confirmed": any(s["confirmed"] for s in sources)
                    and any(t["confirmed"] for t in targets),
                }
            )
    return found


def _readable(note):
    """The part of a condition note worth showing; template text alone says nothing."""
    text = note["text"].removeprefix("基础技能；A杖要求=False，魔晶要求=False。")
    if note["round"] == 2 or len(text) > 70:
        return ""
    for word in (
        "夜",
        "白天",
        "血量",
        "生命值低",
        "层",
        "概率",
        "几率",
        "形态",
        "近战",
        "远程",
        "击杀",
        "死亡",
        "如果",
        "持续施法期间",
    ):
        if word in text:
            return text
    return ""


def display_doc(doc):
    """Copy of the facts for profile pages, with a readable condition note first."""
    rows = []
    for row in doc["rows"]:
        shown = [text for text in map(_readable, row["condition_notes"]) if text]
        notes = [f"AI说明条件：{shown[-1]}", *row["notes_zh"]] if shown else row["notes_zh"]
        rows.append({**row, "notes_zh": notes})
    return {**doc, "rows": rows}


def display_evaluation(evaluation):
    """Copy of the evaluation with pending rules labelled in their names."""
    rules = [
        {**rule, "zh": f"【待定】{rule['zh']}"} if rule["status"] == STATUS_PENDING else rule
        for rule in evaluation["rules"]
    ]
    return {**evaluation, "rules": rules}
