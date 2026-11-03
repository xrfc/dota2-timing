"""MK-T4 mechanism rules: validate them and work out which subjects they connect.

Rules state relations between mechanisms, never what to buy. Inputs are the reviewed
facts; a rule with `pending` still needs a user definition and yields no targets.
"""

RELATIONS = {"removes", "blocks", "disables", "counters", "reduces", "amplifies", "context"}


def load_rules(doc, terms):
    """Validate the rule file; return its rules."""
    if doc.get("schema") != "mechanics-rules/1":
        raise ValueError("Unsupported mechanics rules schema")
    seen = set()
    for rule in doc["rules"]:
        if rule["id"] in seen:
            raise ValueError(f"Duplicate rule: {rule['id']}")
        seen.add(rule["id"])
        if rule["relation"] not in RELATIONS:
            raise ValueError(f"{rule['id']}: unknown relation {rule['relation']}")
        if not rule.get("decision"):
            raise ValueError(f"{rule['id']}: needs a decision reference")
        for key in ("source_mechanisms", "target_mechanisms", "target_exempt_mechanisms"):
            for mechanism in rule.get(key, []):
                if mechanism not in terms:
                    raise ValueError(f"{rule['id']}: unknown mechanism {mechanism}")
    return doc["rules"]


def _subjects(rows, mechanisms):
    return {row["subject"] for row in rows if row["mechanism"] in mechanisms}


def evaluate_rule(rule, doc, game_field_subjects=None):
    """Return sorted source and target subjects for one rule."""
    rows = [row for row in doc["rows"] if row["decision"] == "accept"]
    notes = doc["skill_notes"]
    source = _subjects(rows, set(rule.get("source_mechanisms", [])))
    source |= set(rule.get("source_subjects", []))
    source |= {n["subject"] for n in notes if n["kind"] in rule.get("source_note_kinds", [])}
    target = _subjects(rows, set(rule.get("target_mechanisms", [])))
    target |= set(rule.get("target_subjects", []))
    for field, values in rule.get("target_enum", {}).items():
        target |= {
            fact["subject"]
            for fact in doc["field_observations"]
            if fact["evidence_kind"] == f"enum:{field}" and int(fact["value"]) in values
        }
    if rule.get("target_game_field"):
        target &= (game_field_subjects or {}).get(rule["target_game_field"], set())
    target -= set(rule.get("target_exclude", []))
    target -= {
        n["subject"] for n in notes if n["kind"] in rule.get("target_exclude_note_kinds", [])
    }
    return {"sources": sorted(source), "targets": sorted(target)}
