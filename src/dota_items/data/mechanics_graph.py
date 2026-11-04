"""MK-T5 derived layer: counter graph, item profiles and hero traits v2.

Everything is computed from reviewed facts and rules. Each graph entry carries its
evidence chain, and an entry only counts as confirmed when its evidence does: rows
that only two AIs agreed on stay unconfirmed. Rules state relations, never what to buy.
"""

from dota_items.data.mechanics_profiles import condition_label, confirmed

ACTIVE_ITEM_STATUS = {"purchasable", "other_source"}


def _row_evidence(row):
    return {
        "via": row["mechanism"],
        "basis": row["basis"],
        "confirmed": confirmed(row["basis"]),
        "condition": condition_label(row["condition"]),
        "quote": row["quotes"][0] if row["quotes"] else "",
    }


def _listed(rule):
    basis = f"user:{rule['decision']}"
    return {"via": "rule_list", "basis": basis, "confirmed": True, "condition": "", "quote": ""}


def side_evidence(rule, side, subject, rows_by_subject, doc):
    """Why `subject` sits on this side of the rule; empty means no recorded reason."""
    evidence = [
        _row_evidence(row)
        for row in rows_by_subject.get(subject, [])
        if row["mechanism"] in rule.get(f"{side}_mechanisms", [])
    ]
    if subject in rule.get(f"{side}_subjects", []):
        evidence.append(_listed(rule))
    if side == "source":
        for note in doc["skill_notes"]:
            if note["subject"] == subject and note["kind"] in rule.get("source_note_kinds", []):
                evidence.append(
                    {
                        "via": f"note:{note['kind']}",
                        "basis": f"user:{note['decision']}",
                        "confirmed": True,
                        "condition": "",
                        "quote": note["note_zh"],
                    }
                )
    else:
        for field, values in rule.get("target_enum", {}).items():
            for fact in doc["field_observations"]:
                if (
                    fact["subject"] == subject
                    and fact["evidence_kind"] == f"enum:{field}"
                    and int(fact["value"]) in values
                ):
                    evidence.append(
                        {
                            "via": f"enum:{field}={fact['value']}",
                            "basis": f"field:{field}",
                            "confirmed": True,
                            "condition": "",
                            "quote": "",
                        }
                    )
    return evidence


def node_index(registry_heroes, item_names, item_status):
    """Map each current subject to its hero or item; anything else is left out of the graph."""
    nodes = {}
    for hero in registry_heroes:
        for ability in hero["abilities"]:
            nodes[ability["name"]] = {
                "kind": "ability",
                "hero_id": hero["hero_id"],
                "hero_zh": hero["name_zh"],
                "name_zh": ability["name_zh"],
            }
    for subject, name_zh in item_names.items():
        if item_status.get(subject) in ACTIVE_ITEM_STATUS:
            nodes[subject] = {"kind": "item", "name_zh": name_zh}
    return nodes


def _side(rule, side, subjects, rows_by_subject, doc, nodes, excluded):
    entries = []
    for subject in subjects:
        node = nodes.get(subject)
        if node is None:
            excluded.add(subject)
            continue
        evidence = side_evidence(rule, side, subject, rows_by_subject, doc)
        if not evidence:
            raise ValueError(f"{rule['id']}: {subject} has no evidence on the {side} side")
        entries.append(
            {
                "subject": subject,
                **node,
                "confirmed": any(item["confirmed"] for item in evidence),
                "evidence": evidence,
            }
        )
    return entries


def build_graph(rules, evaluation, doc, nodes):
    """Rule-level graph with evidence, plus per-hero and per-item indexes."""
    rows_by_subject = {}
    for row in doc["rows"]:
        if row["decision"] == "accept":
            rows_by_subject.setdefault(row["subject"], []).append(row)
    evaluated = {rule["id"]: rule for rule in evaluation["rules"]}
    excluded = set()
    out_rules = []
    for rule in rules:
        result = evaluated[rule["id"]]
        out_rules.append(
            {
                "id": rule["id"],
                "zh": rule["zh"],
                "relation": rule["relation"],
                "decision": rule["decision"],
                "pending": rule.get("pending"),
                "note": rule.get("note"),
                "sources": _side(
                    rule, "source", result["sources"], rows_by_subject, doc, nodes, excluded
                ),
                "targets": _side(
                    rule, "target", result["targets"], rows_by_subject, doc, nodes, excluded
                ),
            }
        )
    return {
        "schema": "mechanics-counter-graph/1",
        "rules": out_rules,
        "item_to_hero": item_to_hero(out_rules),
        "excluded_subjects": sorted(excluded),
    }


def item_to_hero(rules):
    """Which item touches which hero through which rule; confirmed needs both ends."""
    edges = []
    for rule in rules:
        targets = {}
        for target in rule["targets"]:
            if target["kind"] == "ability":
                targets.setdefault(target["hero_id"], []).append(target)
        for source in rule["sources"]:
            if source["kind"] != "item":
                continue
            for hero_id, abilities in sorted(targets.items()):
                edges.append(
                    {
                        "item": source["subject"],
                        "item_zh": source["name_zh"],
                        "hero_id": hero_id,
                        "hero_zh": abilities[0]["hero_zh"],
                        "rule": rule["id"],
                        "abilities": [a["subject"] for a in abilities],
                        "confirmed": source["confirmed"] and any(a["confirmed"] for a in abilities),
                    }
                )
    return edges


def edges_between(graph, source_hero, target_hero):
    """Rules where one hero's abilities act on another's; computed, not stored."""
    found = []
    for rule in graph["rules"]:
        sources = [s for s in rule["sources"] if s.get("hero_id") == source_hero]
        targets = [t for t in rule["targets"] if t.get("hero_id") == target_hero]
        if sources and targets:
            found.append(
                {
                    "rule": rule["id"],
                    "zh": rule["zh"],
                    "sources": [s["subject"] for s in sources],
                    "targets": [t["subject"] for t in targets],
                    "confirmed": any(s["confirmed"] for s in sources)
                    and any(t["confirmed"] for t in targets),
                }
            )
    return found


def build_item_profile(subject, name_zh, status, doc, graph, terms):
    """One item: its mechanisms, attributes and where the rules place it."""
    mechanisms = [
        {
            "id": row["mechanism"],
            "zh": terms[row["mechanism"]]["zh"],
            "condition": condition_label(row["condition"]),
            "basis": row["basis"],
            "confirmed": confirmed(row["basis"]),
            "notes": row["notes_zh"],
            "partial_break": row["break_conditions_en"],
            "quote": row["quotes"][0] if row["quotes"] else "",
        }
        for row in doc["rows"]
        if row["subject"] == subject and row["decision"] == "accept"
    ]
    attributes = [
        {"name": fact["evidence_kind"].removeprefix("item_attr:"), "value": fact["value"]}
        for fact in doc["field_observations"]
        if fact["subject"] == subject and fact["evidence_kind"].startswith("item_attr:")
    ]
    can_counter, countered_by = [], []
    for rule in graph["rules"]:
        if any(source["subject"] == subject for source in rule["sources"]):
            heroes = sorted({t["hero_zh"] for t in rule["targets"] if t["kind"] == "ability"})
            can_counter.append({"rule": rule["id"], "zh": rule["zh"], "heroes": heroes})
        if any(target["subject"] == subject for target in rule["targets"]):
            items = sorted(s["name_zh"] for s in rule["sources"] if s["kind"] == "item")
            countered_by.append(
                {
                    "rule": rule["id"],
                    "zh": rule["zh"],
                    "items": items,
                    "hero_sources": sum(1 for s in rule["sources"] if s["kind"] == "ability"),
                }
            )
    return {
        "subject": subject,
        "name_zh": name_zh,
        "status": status,
        "mechanisms": sorted(mechanisms, key=lambda m: (m["condition"], m["id"])),
        "attributes": attributes,
        "can_counter": can_counter,
        "countered_by": countered_by,
    }


def render_item_markdown(profile):
    """Readable item page; `?` marks facts that only AIs agreed on."""
    lines = [f"# {profile['name_zh']}", "", "`?`表示只有AI一致，你还没确认。", "", "## 机制", ""]
    for item in profile["mechanisms"]:
        prefix = f"{item['condition']}：" if item["condition"] else ""
        mark = "" if item["confirmed"] else " ?"
        note = f" — {item['notes'][0]}" if item["notes"] else ""
        lines.append(f"- {prefix}{item['zh']}{mark}{note}")
    for attribute in profile["attributes"]:
        lines.append(f"- 字段 {attribute['name']}：{attribute['value']}")
    lines += ["", "## 能克制什么", ""]
    for rule in profile["can_counter"]:
        shown = "、".join(rule["heroes"][:12]) or "规则未列出目标"
        more = f"等{len(rule['heroes'])}人" if len(rule["heroes"]) > 12 else ""
        lines.append(f"- {rule['rule']} {rule['zh']}：{shown}{more}")
    lines += ["", "## 会被什么克制", ""]
    for rule in profile["countered_by"]:
        items = "、".join(rule["items"][:8]) or "无装备来源"
        lines.append(
            f"- {rule['rule']} {rule['zh']}：装备{items}；技能来源{rule['hero_sources']}个"
        )
    return "\n".join(lines) + "\n"


def build_traits(mapping, doc, registry_heroes):
    """Hero traits v2: which abilities give each hero each trait, with confirmation state."""
    owner = {ability["name"]: hero for hero in registry_heroes for ability in hero["abilities"]}
    zh = {
        ability["name"]: ability["name_zh"]
        for hero in registry_heroes
        for ability in hero["abilities"]
    }
    accepted = [row for row in doc["rows"] if row["decision"] == "accept"]
    dispel = {
        fact["subject"]: int(fact["value"])
        for fact in doc["field_observations"]
        if fact["evidence_kind"] == "enum:dispellable"
    }
    traits = {}
    for trait_id, spec in mapping["traits"].items():
        if spec.get("pending"):
            traits[trait_id] = {"zh": spec["zh"], "pending": spec["pending"], "heroes": []}
            continue
        wanted = set(spec["mechanisms"])
        heroes = {}
        for row in accepted:
            hero = owner.get(row["subject"])
            if hero is None or row["mechanism"] not in wanted:
                continue
            if "dispellable" in spec and dispel.get(row["subject"]) not in spec["dispellable"]:
                continue
            entry = heroes.setdefault(
                hero["hero_id"],
                {"hero_id": hero["hero_id"], "name_zh": hero["name_zh"], "abilities": {}},
            )
            ability = entry["abilities"].setdefault(
                row["subject"],
                {"subject": row["subject"], "name_zh": zh[row["subject"]], "evidence": []},
            )
            ability["evidence"].append(_row_evidence(row))
        listed = []
        for hero_id in sorted(heroes):
            entry = heroes[hero_id]
            abilities = sorted(entry["abilities"].values(), key=lambda a: a["subject"])
            has_base = any(not e["condition"] for a in abilities for e in a["evidence"])
            listed.append(
                {
                    **entry,
                    "abilities": abilities,
                    "ability_count": len(abilities),
                    "only_with_upgrade": not has_base,
                    "confirmed": any(e["confirmed"] for a in abilities for e in a["evidence"]),
                }
            )
        traits[trait_id] = {
            "zh": spec["zh"],
            "note": spec.get("note"),
            "threshold": spec.get("threshold"),
            "heroes": listed,
        }
    return {"schema": "hero-traits/2", "status": mapping["status"], "traits": traits}


def compare_with_v1(traits, v1_doc, mapping):
    """Heroes each v2 trait adds or drops against the hand-labelled v1 table."""
    diff = {}
    for trait_id, spec in mapping["traits"].items():
        old_id = spec.get("v1")
        if not old_id or spec.get("pending"):
            continue
        subtype = spec.get("v1_subtype")
        old = {
            label["hero"]
            for label in v1_doc["labels"].get(old_id, [])
            if subtype is None or label.get("subtype") == subtype
        }
        new = {hero["name_zh"] for hero in traits["traits"][trait_id]["heroes"]}
        diff[trait_id] = {
            "v1": old_id,
            "kept": len(old & new),
            "added": sorted(new - old),
            "dropped": sorted(old - new),
        }
    return diff
