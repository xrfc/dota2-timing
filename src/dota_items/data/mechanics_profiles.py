"""MK-T5 derived layer: hero mechanism profiles built from reviewed facts and rules.

Nothing here is judged by hand. Every entry points back to a fact row (`basis`, quote)
or a rule id, and unconfirmed rows stay marked so readers can tell them apart.
"""

from collections import defaultdict

CONTEXT_LABELS = {"base": "", "scepter_upgrade": "A杖", "shard_upgrade": "魔晶", "item": ""}
DISPEL_LABELS = {1: "仅强驱散", 2: "弱驱散可驱散", 3: "不可驱散"}
DAMAGE_LABELS = {1: "物理", 2: "魔法", 4: "纯粹"}


def confirmed(basis):
    return basis.startswith(("user", "field"))


def condition_label(condition):
    label = CONTEXT_LABELS.get(condition.get("context"), "")
    if not label and condition.get("requires_scepter"):
        return "A杖"
    if not label and condition.get("requires_shard"):
        return "魔晶"
    return label


def _ability_entry(ability, rows, numeric, dispel, terms, extras):
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
        for row in rows
    ]
    return {
        "subject": ability["name"],
        "name_zh": ability["name_zh"],
        "dispellable": DISPEL_LABELS.get(dispel),
        "mechanisms": sorted(mechanisms, key=lambda m: (m["condition"], m["id"])),
        "numeric_upgrades": numeric,
        **extras,
    }


def build_hero_profile(hero, doc, evaluation, terms, item_names):
    """Profile one registry hero; rules name which of its abilities they touch."""
    names = {ability["name"] for ability in hero["abilities"]}
    rows = defaultdict(list)
    for row in doc["rows"]:
        if row["decision"] == "accept" and row["subject"] in names:
            rows[row["subject"]].append(row)
    numeric = defaultdict(list)
    for row in doc["numeric_upgrades"]:
        if row["subject"] in names:
            numeric[row["subject"]].append(
                {
                    "kind": terms[row["kind"]]["zh"],
                    "condition": condition_label(row["condition"]),
                    "field_values": row["field_values"],
                }
            )
    dispel = {
        fact["subject"]: int(fact["value"])
        for fact in doc["field_observations"]
        if fact["evidence_kind"] == "enum:dispellable" and fact["subject"] in names
    }
    field_facts = defaultdict(dict)
    for fact in doc["field_observations"]:
        if fact["subject"] not in names:
            continue
        if fact["evidence_kind"] == "enum:immunity" and int(fact["value"]) == 3:
            field_facts[fact["subject"]]["pierces_debuff_immunity"] = True
        if fact["evidence_kind"] == "enum:damage" and int(fact["value"]) in DAMAGE_LABELS:
            field_facts[fact["subject"]]["damage_type"] = DAMAGE_LABELS[int(fact["value"])]
    skill_notes = defaultdict(list)
    for note in doc.get("skill_notes", []):
        if note["subject"] in names:
            skill_notes[note["subject"]].append(note["note_zh"])
    abilities = []
    for ability in hero["abilities"]:
        name = ability["name"]
        if not (rows[name] or numeric[name] or skill_notes[name]):
            continue
        extras = {**field_facts[name], "skill_notes": skill_notes[name]}
        abilities.append(
            _ability_entry(ability, rows[name], numeric[name], dispel.get(name), terms, extras)
        )
    zh = {ability["name"]: ability["name_zh"] for ability in hero["abilities"]}
    countered_by = []
    can_counter = []
    for rule in evaluation["rules"]:
        targets = sorted(names & set(rule["targets"]))
        sources = sorted(names & set(rule["sources"]))
        if targets:
            items = sorted(item_names[s] for s in rule["sources"] if s in item_names)
            countered_by.append(
                {
                    "rule": rule["id"],
                    "zh": rule["zh"],
                    "own_abilities": [zh[name] for name in targets],
                    "items": items,
                    "hero_sources": sum(1 for s in rule["sources"] if s not in item_names),
                }
            )
        if sources:
            can_counter.append(
                {"rule": rule["id"], "zh": rule["zh"], "own_abilities": [zh[n] for n in sources]}
            )
    return {
        "hero_id": hero["hero_id"],
        "name_zh": hero["name_zh"],
        "abilities": abilities,
        "countered_by": countered_by,
        "can_counter": can_counter,
    }


def render_markdown(profile):
    """Readable sample; `?` marks facts that only AIs agreed on."""
    lines = [
        f"# {profile['name_zh']}",
        "",
        "`?`表示只有AI一致，你还没确认。",
        "",
        "## 技能机制",
        "",
    ]
    for ability in profile["abilities"]:
        tags = [ability["dispellable"], ability.get("damage_type")]
        if ability.get("pierces_debuff_immunity"):
            tags.append("穿透减益免疫")
        shown = "、".join(tag for tag in tags if tag)
        lines.append(f"**{ability['name_zh']}**" + (f"（{shown}）" if shown else ""))
        for item in ability["mechanisms"]:
            prefix = f"{item['condition']}：" if item["condition"] else ""
            mark = "" if item["confirmed"] else " ?"
            note = f" — {item['notes'][0]}" if item["notes"] else ""
            lines.append(f"- {prefix}{item['zh']}{mark}{note}")
        for upgrade in ability["numeric_upgrades"]:
            lines.append(f"- {upgrade['condition']}只改数值：{upgrade['kind']}")
        for note in ability.get("skill_notes", []):
            lines.append(f"- 备注：{note}")
        lines.append("")
    lines += ["## 会被什么克制", ""]
    for rule in profile["countered_by"]:
        items = "、".join(rule["items"][:8]) or "无装备来源"
        own = "、".join(rule["own_abilities"][:8])
        lines.append(f"- {rule['rule']} {rule['zh']}：涉及{own}；装备：{items}")
    lines += ["", "## 能克制什么", ""]
    for rule in profile["can_counter"]:
        lines.append(f"- {rule['rule']} {rule['zh']}：靠{'、'.join(rule['own_abilities'][:8])}")
    return "\n".join(lines) + "\n"
