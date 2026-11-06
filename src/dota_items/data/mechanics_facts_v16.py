"""MK-T5 reviewed facts, version 16: frozen v15, U101, and feedback resolved by identity.

The feedback-driven `basis` of every row is worked out again from all of its feedback with
`data.mechanics_feedback`, so a later wrong is never closed by an older correction.
"""

from dota_items.data import mechanics_facts_v12 as v12
from dota_items.data import mechanics_facts_v13 as v13
from dota_items.data.mechanics_feedback import claim_of, feedback_id, resolve

SCHEMA = "mechanics-facts/16"
VERSION = "mechanics-reviewed/16"
VOCABULARY = v13.VOCABULARY


def _entries(row, claims):
    return [
        {
            **entry,
            "feedback_id": feedback_id(entry),
            "claim": claims.get(row["review_id"], {}).get(entry.get("file")),
        }
        for entry in row.get("user_feedback", [])
    ]


def build_reviewed(base, inputs, corrections, claims):
    """Apply U101, then resolve feedback per row; nothing in v15 is rewritten."""
    rows = [{**row, "notes_zh": list(row["notes_zh"])} for row in base["rows"]]
    names = {entry["subject"]: entry.get("subject_zh", "") for entry in inputs["rulings"]}
    for entry in inputs["rulings"]:
        v12._set(rows, entry, names, {})
    for row in rows:
        row.setdefault("condition_notes", [])
        row.setdefault("condition_review", "none")
    by_review = {}
    for correction in corrections:
        by_review.setdefault(correction["review_id"], []).append(correction)
    changed = []
    for row in rows:
        entries = _entries(row, claims)
        row_corrections = by_review.get(row["review_id"], [])
        if not entries and not row_corrections:
            continue
        before = row["basis"]
        basis, open_wrongs, reason = resolve(row, entries, row_corrections)
        row["user_feedback"] = entries
        row["basis"] = basis
        row["feedback_status"] = {
            "open_wrongs": open_wrongs,
            "reason_zh": reason,
            "resolved_by": [c["from"] for c in row_corrections],
            "claim_now": claim_of(row),
            "basis_v15": before,
        }
        if basis != before:
            changed.append(
                {"review_id": row["review_id"], "from": before, "to": basis, "reason_zh": reason}
            )
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    return {
        **base,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "rows": rows,
        "skill_notes": [*base["skill_notes"], *inputs.get("notes", [])],
        "feedback_changes": changed,
        "counts": {
            **v13._counts(base, rows, base["unattached_feedback"]),
            "retired_rows": len(base["retired_rows"]),
            "retired_term_rows": len(base["retired_term_rows"]),
            "feedback_changes": len(changed),
        },
    }
