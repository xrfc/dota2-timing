"""MK-T5 reviewed facts, version 13: v12 plus kept condition notes and honest user feedback.

Condition notes are AI text kept for reading and never used for inference. A user marking a
row wrong no longer counts as confirming it; the row waits for a ruling.
"""

from dota_items.data import mechanics_facts_v12 as v12

SCHEMA = "mechanics-facts/13"
VERSION = "mechanics-reviewed/13"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"
RETIRED_HERE = {"flying"}
BASIS_DISPUTED = "disputed_by_user"
CONDITION_POLICY = "AI写的文字说明，只供阅读；不能用于自动推理。没有说明不代表无条件。"
PREFIX_ROUND_2 = "基础技能；A杖要求=False，魔晶要求=False。"


def attach_condition_notes(rows, reviews):
    """Keep every reviewer's condition text on its row; say so when a row has none."""
    notes = {}
    for review in reviews:
        text = review.get("condition_zh") or review.get("conditions_zh")
        if text:
            notes.setdefault(review["review_id"], []).append(
                {"text": text, "round": review["round"], "reviewer": review["reviewer"]}
            )
    for row in rows:
        row["condition_notes"] = notes.get(row["review_id"], [])
        row["condition_review"] = "ai_note" if row["condition_notes"] else "none"


def apply_feedback(rows, feedback, corrections):
    """Attach user feedback to rows and set basis by what the feedback actually said.

    `ok` confirms an AI-only row. `wrong` disputes the row whatever its basis was, a user ruling or
    a game field included, until a correction is listed.
    `unsure` changes nothing. Feedback whose row no longer exists is returned, not dropped.
    """
    by_id = {row["review_id"]: row for row in rows}
    resolved = {entry["review_id"]: entry for entry in corrections}
    unattached = []
    for entry in feedback:
        row = by_id.get(entry["review_id"])
        if row is None:
            unattached.append(entry)
            continue
        row.setdefault("user_feedback", []).append(entry)
        if entry["verdict"] == "ok" and row["basis"] == "two_ai":
            row["basis"] = "user_spot_check"
        elif entry["verdict"] == "wrong":
            row["basis"] = BASIS_DISPUTED
    for review_id, entry in resolved.items():
        row = by_id[review_id]
        row["basis"] = entry["basis"]
        row["notes_zh"] = [entry["note_zh"], *row["notes_zh"]]
    return unattached


def _counts(doc, rows, unattached):
    decisions, basis = {}, {}
    for row in rows:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
        name = row["basis"].split(":")[0]
        basis[name] = basis.get(name, 0) + 1
    with_note = sum(1 for row in rows if row["condition_review"] == "ai_note")
    return {
        **doc["counts"],
        "rows": len(rows),
        "decisions": decisions,
        "basis": basis,
        "rows_with_condition_note": with_note,
        "unattached_feedback": len(unattached),
    }


def build_reviewed(sources):
    """v12 result with bear rulings, condition notes and user feedback applied."""
    base = v12.build_reviewed(sources)
    doc = v12.apply_rulings(
        base, sources["v13_rulings"], sources["zh_names"], sources["item_status"]
    )
    rows = [row for row in doc["rows"] if row["mechanism"] not in RETIRED_HERE]
    retired = [
        *base["retired_term_rows"],
        *(row for row in doc["rows"] if row["mechanism"] in RETIRED_HERE),
    ]
    attach_condition_notes(rows, sources["condition_reviews"])
    unattached = apply_feedback(rows, sources["user_feedback"], sources["feedback_corrections"])
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    return {
        **doc,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "rows": rows,
        "retired_term_rows": retired,
        "skill_notes": [*doc["skill_notes"], *sources["v13_notes"]],
        "condition_policy": CONDITION_POLICY,
        "unattached_feedback": unattached,
        "counts": {
            **_counts(doc, rows, unattached),
            "retired_term_rows": len(retired),
        },
    }
