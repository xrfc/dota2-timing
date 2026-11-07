"""MK reviewed facts, version 22: rows the user added after the trait spot check (U117).

Each added row must name a mechanism in the vocabulary and a subject that already has rows,
must not duplicate an existing (subject, mechanism, condition) row, and must cite a user basis.
Rows stay sorted as before, and counts are recomputed.
"""

SCHEMA = "mechanics-facts/22"
VERSION = "mechanics-reviewed/22"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"
BASE_CONDITION = {"context": "base", "requires_scepter": False, "requires_shard": False}


def build_reviewed(base, inputs, terms):
    if inputs.get("condition_exceptions"):
        raise ValueError("v22 adds no condition exceptions")
    subjects = {row["subject"] for row in base["rows"]}
    existing = {(r["subject"], r["mechanism"], r["condition"]["context"]) for r in base["rows"]}
    ids = {row["review_id"] for row in base["rows"]}
    added = []
    for spec in inputs["added_rows"]:
        if spec["mechanism"] not in terms:
            raise ValueError(f"Unknown mechanism {spec['mechanism']}")
        if spec["subject"] not in subjects:
            raise ValueError(f"Unknown subject {spec['subject']}")
        if not spec["basis"].startswith("user:"):
            raise ValueError("Added rows need a user basis")
        key = (spec["subject"], spec["mechanism"], BASE_CONDITION["context"])
        if key in existing or spec["review_id"] in ids:
            raise ValueError(f"Row already exists: {key}")
        added.append(
            {
                "review_id": spec["review_id"],
                "origin": "user_added",
                "subject": spec["subject"],
                "subject_zh": spec["subject_zh"],
                "mechanism": spec["mechanism"],
                "condition": dict(BASE_CONDITION),
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
