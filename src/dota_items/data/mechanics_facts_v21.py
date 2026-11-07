"""MK-T6g reviewed facts, version 21: U114 moves small passive regen rows to the user's basis.

The user ruled that small passive health regeneration counts as healing (U114). The listed
rows already said so with `two_ai`; only their basis changes to `user:U114`. Each update must
name an existing accepted row with the stated subject, mechanism and old basis.
"""

SCHEMA = "mechanics-facts/21"
VERSION = "mechanics-reviewed/21"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"
NOTE = "用户U114：小额被动生命恢复算治疗（对线回血，时间长了有价值）"


def build_reviewed(base, inputs):
    """Same rows as v20; listed rows get the new basis and a note."""
    if inputs.get("condition_exceptions"):
        raise ValueError("v21 adds no condition exceptions")
    updates = {u["review_id"]: u for u in inputs["basis_updates"]}
    if len(updates) != len(inputs["basis_updates"]):
        raise ValueError("Duplicate review_id in basis updates")
    rows, seen = [], set()
    for row in base["rows"]:
        update = updates.get(row["review_id"])
        if update and (row["subject"], row["mechanism"]) == (
            update["subject"],
            update["mechanism"],
        ):
            if row["decision"] != "accept" or row["basis"] != update["from"]:
                raise ValueError(f"{row['review_id']}: expected an accepted {update['from']} row")
            row = {**row, "basis": update["to"], "notes_zh": [*row["notes_zh"], NOTE]}
            seen.add(row["review_id"])
        rows.append(row)
    missing = sorted(set(updates) - seen)
    if missing:
        raise ValueError(f"Basis updates without a matching row: {missing}")
    basis = {}
    for row in rows:
        key = row["basis"].split(":")[0]
        basis[key] = basis.get(key, 0) + 1
    return {
        **base,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "rows": rows,
        "counts": {**base["counts"], "basis": basis},
    }
