"""MK-T5 reviewed facts, version 9: v8 plus corrections found while reading profiles."""

from dota_items.data import mechanics_facts_v8 as v8

SCHEMA = "mechanics-facts/9"
VERSION = "mechanics-reviewed/9"
VOCABULARY = "knowledge/mechanics/vocabulary-v9.json"
BASE = {"context": "base", "requires_scepter": False, "requires_shard": False}


def _added_row(correction):
    return {
        "review_id": f"t5:{correction['subject']}:{correction['mechanism']}",
        "origin": "t5_correction",
        "subject": correction["subject"],
        "subject_zh": correction.get("subject_zh", correction["subject"]),
        "mechanism": correction["mechanism"],
        "condition": correction.get("condition", BASE),
        "decision": "accept",
        "basis": f"user:{correction['decision_ref']}",
        "claude": None,
        "codex": None,
        "notes_zh": [correction["note_zh"]],
        "break_conditions_en": [],
        "quotes": [correction["source_quote"]],
        "item_status": None,
    }


def apply_corrections(doc, corrections, zh_names):
    """Apply T5 corrections; a correction matching no row fails loudly."""
    rows = [dict(row) for row in doc["rows"]]
    fields = list(doc["field_observations"])
    notes = list(doc["skill_notes"])
    for correction in corrections:
        kind = correction["kind"]
        if kind in ("confirm", "reject"):
            matched = [
                row
                for row in rows
                if row["subject"] == correction["subject"]
                and row["mechanism"] == correction["mechanism"]
            ]
            if not matched:
                raise ValueError(f"No row for correction: {correction}")
            for row in matched:
                row["basis"] = f"user:{correction['decision_ref']}"
                row["notes_zh"] = [correction["note_zh"], *row["notes_zh"]]
                if kind == "reject":
                    row["decision"] = "reject"
        elif kind == "add":
            added = {**correction, "subject_zh": zh_names.get(correction["subject"], "")}
            rows.append(_added_row(added))
        elif kind == "note":
            notes.append(
                {
                    "subject": correction["subject"],
                    "subject_zh": zh_names.get(correction["subject"], ""),
                    "kind": correction["mechanism"],
                    "note_zh": correction["note_zh"],
                    "decision": correction["decision_ref"],
                }
            )
        elif kind == "field_fix":
            fields = [
                fact
                for fact in fields
                if not (
                    fact["subject"] == correction["subject"]
                    and fact["evidence_kind"] == correction["evidence_kind"]
                )
            ]
        elif kind not in ("rule", "definition"):
            raise ValueError(f"Unknown correction kind: {kind}")
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    decisions, basis = {}, {}
    for row in rows:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
        key = row["basis"].split(":")[0]
        basis[key] = basis.get(key, 0) + 1
    return {
        **doc,
        "rows": rows,
        "field_observations": fields,
        "skill_notes": notes,
        "counts": {**doc["counts"], "rows": len(rows), "decisions": decisions, "basis": basis},
    }


def build_reviewed(sources):
    """v8 result with T5 corrections applied."""
    doc = apply_corrections(
        v8.build_reviewed(sources), sources["t5_corrections"], sources["zh_names"]
    )
    return {**doc, "schema": SCHEMA, "extractor_version": VERSION, "vocabulary": VOCABULARY}
