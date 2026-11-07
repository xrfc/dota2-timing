"""MK-T5 reviewed facts, version 14: frozen v13 plus rulings it missed and newer spot checks."""

from dota_items.data import mechanics_facts_v12 as v12
from dota_items.data import mechanics_facts_v13 as v13

SCHEMA = "mechanics-facts/14"
VERSION = "mechanics-reviewed/14"
VOCABULARY = v13.VOCABULARY


def build_reviewed(base, inputs, feedback):
    """Apply rulings and new feedback to a copy of v13; v13 itself is never rewritten."""
    rows = [{**row, "notes_zh": list(row["notes_zh"])} for row in base["rows"]]
    names = {entry["subject"]: entry.get("subject_zh", "") for entry in inputs["rulings"]}
    for entry in inputs["rulings"]:
        v12._set(rows, entry, names, {})
    for row in rows:
        row.setdefault("condition_notes", [])
        row.setdefault("condition_review", "none")
    unattached = [
        *base["unattached_feedback"],
        *v13.apply_feedback(rows, feedback, inputs.get("corrections", [])),
    ]
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    return {
        **base,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "rows": rows,
        "unattached_feedback": unattached,
        "counts": {
            **v13._counts(base, rows, unattached),
            "retired_term_rows": len(base["retired_term_rows"]),
        },
    }
