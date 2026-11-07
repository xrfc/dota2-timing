"""MK-T5 reviewed facts, version 11: v10 plus the full recall audit and the U83 rulings."""

from dota_items.data import mechanics_facts_v10 as v10

SCHEMA = "mechanics-facts/11"
VERSION = "mechanics-reviewed/11"
VOCABULARY = "knowledge/mechanics/vocabulary-v10.json"
CONDITIONS = {
    "base": {"context": "base", "requires_scepter": False, "requires_shard": False},
    "item": {"context": "item", "requires_scepter": False, "requires_shard": False},
    "scepter": {"context": "scepter_upgrade", "requires_scepter": True, "requires_shard": False},
    "shard": {"context": "shard_upgrade", "requires_scepter": False, "requires_shard": True},
}


def _key(subject, mechanism, condition):
    return subject, mechanism, condition["context"]


def _new_row(entry, zh_names, status):
    both = entry["origin"] == "full_audit_both"
    return {
        "review_id": f"audit:{entry['subject']}:{entry['mechanism']}:{entry['condition']}",
        "origin": entry["origin"],
        "subject": entry["subject"],
        "subject_zh": zh_names.get(entry["subject"], ""),
        "mechanism": entry["mechanism"],
        "condition": CONDITIONS[entry["condition"]],
        "decision": entry["decision"],
        "basis": entry["basis"],
        "claude": "accept" if entry["decision"] == "accept" else None,
        "codex": "accept" if both or entry["origin"] == "full_audit_sequential" else None,
        "notes_zh": [entry["note_zh"]],
        "break_conditions_en": [],
        "quotes": [entry["quote"]] if entry["quote"] else [],
        "item_status": status.get(entry["subject"]),
    }


def apply_adoptions(doc, adoptions, zh_names, status):
    """Update the matching row or add a new one; rows from user rulings replace AI rows."""
    rows = [dict(row) for row in doc["rows"]]
    notes = list(doc["skill_notes"])
    index = {_key(r["subject"], r["mechanism"], r["condition"]): r for r in rows}
    for entry in adoptions:
        if entry["kind"] == "note":
            notes.append(
                {
                    "subject": entry["subject"],
                    "subject_zh": zh_names.get(entry["subject"], ""),
                    "kind": entry["mechanism"],
                    "note_zh": entry["note_zh"],
                    "decision": entry["decision_ref"],
                }
            )
            continue
        key = _key(entry["subject"], entry["mechanism"], CONDITIONS[entry["condition"]])
        existing = index.get(key)
        if existing is None:
            row = _new_row(entry, zh_names, status)
            rows.append(row)
            index[key] = row
        elif entry["basis"].startswith("user:"):
            existing["decision"] = entry["decision"]
            existing["basis"] = entry["basis"]
            existing["notes_zh"] = [entry["note_zh"], *existing["notes_zh"]]
        else:
            raise ValueError(f"Audit row would overwrite an existing row: {entry}")
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    decisions, basis = {}, {}
    for row in rows:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
        name = row["basis"].split(":")[0]
        basis[name] = basis.get(name, 0) + 1
    counts = {**doc["counts"], "rows": len(rows), "decisions": decisions, "basis": basis}
    return {**doc, "rows": rows, "skill_notes": notes, "counts": counts}


def build_reviewed(sources):
    """v10 result with the audit adoptions applied."""
    doc = apply_adoptions(
        v10.build_reviewed(sources),
        sources["audit_adoptions"],
        sources["zh_names"],
        sources["item_status"],
    )
    return {**doc, "schema": SCHEMA, "extractor_version": VERSION, "vocabulary": VOCABULARY}
