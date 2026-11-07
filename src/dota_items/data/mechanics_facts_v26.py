"""Reviewed facts, version 26 (U126): Huskar's Life Break rows, and the "无视减益免疫" wording.

Rows: one decision change and one basis update, applied with the v23 and v21 helpers, which
check that each named row exists with the stated old state. The wording change lives in
vocabulary v15, enums v2 and rules v13; mechanism ids are unchanged.
"""

from dota_items.data import mechanics_facts_v21 as v21
from dota_items.data import mechanics_facts_v23 as v23

SCHEMA = "mechanics-facts/26"
VERSION = "mechanics-reviewed/26"
VOCABULARY = "knowledge/mechanics/vocabulary-v15.json"
OLD, NEW = "穿透减益免疫", "无视减益免疫"


def build_reviewed(base, inputs):
    if inputs.get("condition_exceptions"):
        raise ValueError("v26 adds no condition exceptions")
    doc = v23.build_reviewed(base, {"decision_changes": inputs["decision_changes"]})
    doc = v21.build_reviewed(doc, {"basis_updates": inputs["basis_updates"]})
    rows = [_reword(row) for row in doc["rows"]]
    return {
        **doc,
        "rows": rows,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
    }


def _reword(row):
    """Notes written by AIs use the new wording; quoted source text stays as it was."""
    return {
        **row,
        "notes_zh": [n.replace(OLD, NEW) for n in row["notes_zh"]],
        "condition_notes": [
            {**note, "text": note["text"].replace(OLD, NEW)} for note in row["condition_notes"]
        ],
    }
