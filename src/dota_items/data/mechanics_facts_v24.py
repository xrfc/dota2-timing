"""Reviewed facts, version 24: user-added rows that carry their own condition (U119).

Like v22, but each added row states its condition (for example a Shard-only ability), and
the condition must match one the subject already has. Duplicates and non-user bases raise.
"""

SCHEMA = "mechanics-facts/24"
VERSION = "mechanics-reviewed/24"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"


def build_reviewed(base, inputs, terms):
    if inputs.get("condition_exceptions"):
        raise ValueError("v24 adds no condition exceptions")
    conditions = {}
    for row in base["rows"]:
        conditions.setdefault(row["subject"], []).append(row["condition"])
    existing = {(r["subject"], r["mechanism"], r["condition"]["context"]) for r in base["rows"]}
    ids = {row["review_id"] for row in base["rows"]}
    added = []
    for spec in inputs["added_rows"]:
        if spec["mechanism"] not in terms:
            raise ValueError(f"Unknown mechanism {spec['mechanism']}")
        if spec["subject"] not in conditions:
            raise ValueError(f"Unknown subject {spec['subject']}")
        if spec["condition"] not in conditions[spec["subject"]]:
            raise ValueError(f"{spec['subject']}: condition not used by its other rows")
        if not spec["basis"].startswith("user:"):
            raise ValueError("Added rows need a user basis")
        key = (spec["subject"], spec["mechanism"], spec["condition"]["context"])
        if key in existing or spec["review_id"] in ids:
            raise ValueError(f"Row already exists: {key}")
        added.append(
            {
                "review_id": spec["review_id"],
                "origin": "user_added",
                "subject": spec["subject"],
                "subject_zh": spec["subject_zh"],
                "mechanism": spec["mechanism"],
                "condition": dict(spec["condition"]),
                "decision": spec["decision"],
                "basis": spec["basis"],
                "claude": None,
                "codex": None,
                "notes_zh": list(spec["notes_zh"]),
                "break_conditions_en": [],
                "quotes": list(spec["quotes"]),
                "item_status": None,
                "condition_notes": [],
                "condition_review": "none",
            }
        )
    rows = sorted(
        [*base["rows"], *added], key=lambda r: (r["mechanism"], r["subject"], r["review_id"])
    )
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
        "counts": {**base["counts"], "rows": len(rows), "decisions": decisions, "basis": basis},
    }
