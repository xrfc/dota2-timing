"""Reviewed facts, version 25: the new "haste" mechanism (U120, U121).

Rows come from reviews/haste-001 (Codex proposed, Claude checked the evidence), so their
basis is `two_ai`. Each row must name the new mechanism, a known ability or item, one of
the standard conditions, and must not duplicate a row. The vocabulary moves to v14.
"""

SCHEMA = "mechanics-facts/25"
VERSION = "mechanics-reviewed/25"
VOCABULARY = "knowledge/mechanics/vocabulary-v14.json"
CONDITIONS = (
    {"context": "base", "requires_scepter": False, "requires_shard": False},
    {"context": "scepter_upgrade", "requires_scepter": True, "requires_shard": False},
    {"context": "shard_upgrade", "requires_scepter": False, "requires_shard": True},
    {"context": "item", "requires_scepter": False, "requires_shard": False},
)
NOTE_KEYS = ("review_id", "subject", "subject_zh", "mechanism", "decision", "basis", "condition")


def build_reviewed(base, inputs, terms, known_subjects):
    added, seen = [], {(r["subject"], r["mechanism"]) for r in base["rows"]}
    ids = {row["review_id"] for row in base["rows"]}
    for spec in inputs["added_rows"]:
        if spec["mechanism"] != "haste" or "haste" not in terms:
            raise ValueError("v25 only adds haste rows, and the vocabulary must define haste")
        if spec["subject"] not in known_subjects:
            raise ValueError(f"Unknown subject {spec['subject']}")
        if spec["condition"] not in CONDITIONS:
            raise ValueError(f"{spec['subject']}: unexpected condition")
        if (spec["subject"], "haste") in seen or spec["review_id"] in ids:
            raise ValueError(f"Duplicate haste row for {spec['subject']}")
        seen.add((spec["subject"], "haste"))
        added.append(
            {
                **{key: spec[key] for key in NOTE_KEYS},
                "origin": "haste_review",
                "claude": "accept",
                "codex": "accept",
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
