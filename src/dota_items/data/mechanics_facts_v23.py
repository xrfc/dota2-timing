"""Reviewed facts, version 23: decision changes from the hero trait spot check (U118).

Each change must name an existing row with the stated subject, mechanism and old decision.
The row gets the new decision, the user basis and a note; counts are recomputed.
"""

SCHEMA = "mechanics-facts/23"
VERSION = "mechanics-reviewed/23"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"


def build_reviewed(base, inputs):
    if inputs.get("condition_exceptions"):
        raise ValueError("v23 adds no condition exceptions")
    changes = {c["review_id"]: c for c in inputs["decision_changes"]}
    if len(changes) != len(inputs["decision_changes"]):
        raise ValueError("Duplicate review_id in decision changes")
    rows, seen = [], set()
    for row in base["rows"]:
        change = changes.get(row["review_id"])
        if change:
            if (row["subject"], row["mechanism"], row["decision"]) != (
                change["subject"],
                change["mechanism"],
                change["from"],
            ):
                raise ValueError(f"{row['review_id']}: row does not match the change")
            if not change["basis"].startswith("user:"):
                raise ValueError("Decision changes need a user basis")
            row = {
                **row,
                "decision": change["to"],
                "basis": change["basis"],
                "notes_zh": [*row["notes_zh"], change["note_zh"]],
            }
            seen.add(row["review_id"])
        rows.append(row)
    missing = sorted(set(changes) - seen)
    if missing:
        raise ValueError(f"Decision changes without a matching row: {missing}")
    decisions, basis = {}, {}
    for row in rows:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
        key = row["basis"].split(":")[0]
        basis[key] = basis.get(key, 0) + 1
    return {
        **base,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "rows": rows,
        "counts": {**base["counts"], "decisions": decisions, "basis": basis},
    }
