"""MK-T5 reviewed facts, version 15: frozen v14 plus U99-U100 and the last spot check marks."""

from dota_items.data import mechanics_facts_v12 as v12
from dota_items.data import mechanics_facts_v13 as v13

SCHEMA = "mechanics-facts/15"
VERSION = "mechanics-reviewed/15"
VOCABULARY = v13.VOCABULARY


def build_reviewed(base, inputs, feedback):
    """Apply rulings and feedback to a copy of v14, then retire items the user said are gone."""
    rows = [{**row, "notes_zh": list(row["notes_zh"])} for row in base["rows"]]
    for entry in inputs["rulings"]:
        v12._set(rows, entry, {}, {})
    unattached = [
        *base["unattached_feedback"],
        *v13.apply_feedback(rows, feedback, inputs.get("corrections", [])),
    ]
    gone = set(inputs.get("retired_subjects", []))
    retired = [{**row, "item_status": "obsolete"} for row in rows if row["subject"] in gone]
    rows = [row for row in rows if row["subject"] not in gone]
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    return {
        **base,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "rows": rows,
        "retired_rows": [*base["retired_rows"], *retired],
        "unattached_feedback": unattached,
        "counts": {
            **v13._counts(base, rows, unattached),
            "retired_rows": len(base["retired_rows"]) + len(retired),
            "retired_term_rows": len(base["retired_term_rows"]),
        },
    }
