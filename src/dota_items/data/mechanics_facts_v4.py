"""MK-T3 reviewed facts, version 4: v3 evidence with all recorded decisions applied.

v4 does not re-extract text. It overlays Claude, Codex and user decisions on the frozen
v3 review groups, adds groups the game-file audit found, and marks retired items.
Precedence: user ruling, then IsBreakable for break_sensitive, then the AI decision.
"""

from collections import Counter

SCHEMA = "mechanics-facts/4"
VERSION = "mechanics-reviewed/4"
RETIRED = {"obsolete", "retired_candidate"}
DEFERRED = {"neutral_pool"}  # U27: neutral items come later; U55: kept aside, not deleted.
EXTRA_NOTES = {
    (
        "nullifier",
        "applies_basic_dispel",
    ): "持续驱散，推推推不出去、吹风吹不起来（U51，user_reported）",
}


def _tier(ruling, verdict, codex, claude, decision):
    if ruling:
        return f"user:{ruling['decision_ref']}"
    if verdict in ("ok", "wrong"):
        return "user_spot_check"
    if codex == decision and claude == decision:
        return "two_ai"
    if codex is None:
        return "claude_only"
    return "ai_conflict"


def _review_rows(sources, status):
    rulings = sources["rulings"]
    conditions = sources["break_conditions"]
    rows = []
    for group in sources["review_rows"]:
        rid = group["review_id"]
        claude = sources["claude"][rid]["decision"]
        ruling = rulings.get(rid)
        decision = ruling["decision"] if ruling else claude
        notes = [ruling["note_zh"]] if ruling else []
        codex = sources["codex"].get(rid)
        tier = _tier(ruling, sources["verdicts"].get(rid), codex, claude, decision)
        if group["mechanism"] == "break_sensitive":
            tagged = sources["break_tags"].get(group["subject"]) == "1"
            if decision != ("accept" if tagged else "reject"):
                raise ValueError(f"break decision differs from IsBreakable: {group['subject']}")
            tier = tier if ruling else "field:IsBreakable"
        extra = EXTRA_NOTES.get((group["subject"], group["mechanism"]))
        if extra:
            notes.append(extra)
        rows.append(
            {
                "review_id": rid,
                "origin": "v3_review",
                "subject": group["subject"],
                "subject_zh": "·".join(n for n in (group["hero_zh"], group["name_zh"]) if n),
                "mechanism": group["mechanism"],
                "condition": group["condition"],
                "decision": decision,
                "basis": tier,
                "claude": claude,
                "codex": codex,
                "notes_zh": notes,
                "break_conditions_en": conditions.get(rid, []),
                "quotes": group["quotes"],
                "item_status": status.get(group["subject"]),
            }
        )
    return rows


def _audit_rows(sources, status, known):
    rows = []
    for candidate in sources["audit"]:
        pair = (candidate["subject"], candidate["mechanism"])
        if pair in known:
            continue
        rid = candidate["review_id"]
        ruling = sources["rulings"].get(rid)
        claude, codex = candidate["claude_decision"], candidate["decision"]
        if ruling:
            decision, basis, notes = ruling["decision"], f"user:{ruling['decision_ref']}", None
            notes = [ruling["note_zh"]]
        elif claude == codex and claude != "uncertain":
            decision, basis, notes = claude, "two_ai", []
        else:
            decision, basis, notes = "uncertain", "ai_conflict", []
        if status.get(candidate["subject"]) in RETIRED:
            basis = "retired"
        rows.append(
            {
                "review_id": rid,
                "origin": "audit_round4",
                "subject": candidate["subject"],
                "subject_zh": candidate["subject_zh"],
                "mechanism": candidate["mechanism"],
                "condition": candidate["condition"],
                "decision": decision,
                "basis": basis,
                "claude": claude,
                "codex": codex,
                "notes_zh": notes,
                "break_conditions_en": [],
                "quotes": [candidate["reason_zh"]],
                "item_status": status.get(candidate["subject"]),
            }
        )
    return rows


def _user_added_rows(sources, status, known):
    rows = []
    for row in sources["user_added"]:
        if (row["subject"], row["mechanism"]) in known:
            continue
        rows.append(
            {
                "review_id": row["review_id"],
                "origin": "user_added",
                "subject": row["subject"],
                "subject_zh": row["subject_zh"],
                "mechanism": row["mechanism"],
                "condition": row["condition"],
                "decision": row["decision"],
                "basis": f"user:{row['decision_ref']}",
                "claude": None,
                "codex": None,
                "notes_zh": [row["note_zh"]],
                "break_conditions_en": row.get("condition_en", []),
                "quotes": [row["source_quote"]],
                "item_status": status.get(row["subject"]),
            }
        )
    return rows


def build_reviewed(sources):
    """Return the v4 document from plain inputs; deterministic and side-effect free."""
    status = sources["item_status"]
    rows = _review_rows(sources, status)
    known = {(row["subject"], row["mechanism"]) for row in rows}
    rows += _audit_rows(sources, status, known)
    known |= {(row["subject"], row["mechanism"]) for row in rows}
    rows += _user_added_rows(sources, status, known)
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    retired = [row for row in rows if row["item_status"] in RETIRED]
    deferred = [row for row in rows if row["item_status"] in DEFERRED]
    active = [row for row in rows if row["item_status"] not in RETIRED | DEFERRED]
    open_rows = [row["review_id"] for row in active if row["basis"] == "ai_conflict"]
    return {
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "patch_verified": False,
        "vocabulary": "knowledge/mechanics/vocabulary-v4.json",
        "counts": {
            "rows": len(active),
            "decisions": dict(Counter(row["decision"] for row in active)),
            "basis": dict(Counter(row["basis"].split(":")[0] for row in active)),
            "retired_rows": len(retired),
            "deferred_rows": len(deferred),
            "open_ai_conflicts": len(open_rows),
        },
        "open_ai_conflicts": open_rows,
        "rows": active,
        "retired_rows": retired,
        "deferred_rows": deferred,
        "field_observations": sources["field_observations"],
    }
