"""Transport and compare MK-T3 human/AI judgments without deciding game semantics."""

from collections import Counter

from dota_items.data.mechanics_facts import canonical, digest

REVIEW_FIELDS = {
    "packet_id",
    "review_id",
    "reviewer",
    "decision",
    "interpretation_zh",
    "conditions_zh",
    "reason_zh",
    "evidence_fact_ids",
}


def make_cases(facts_doc, queue, vocabulary):
    """Preserve every pending fact exactly once in its original review group."""
    facts = {f["fact_id"]: f for f in facts_doc["facts"]}
    if len(facts) != len(facts_doc["facts"]):
        raise ValueError("Duplicate fact IDs")
    cases, used, ids = [], set(), set()
    for index, row in enumerate(queue, 1):
        rid = row["review_id"]
        if rid in ids:
            raise ValueError("Duplicate review ID")
        ids.add(rid)
        evidence = []
        for fid in row["fact_ids"].split(" | "):
            if fid not in facts or fid in used:
                raise ValueError("Unknown or repeated fact")
            fact = facts[fid]
            expected = digest(
                [fact["subject_type"], fact["subject"], fact["mechanism"], fact["condition"]]
            )[:20]
            if rid != expected or fact["review"] != "needs_review":
                raise ValueError("Fact belongs to a different review group")
            if fact["subject"] != row["subject"] or fact["mechanism"] != row["mechanism"]:
                raise ValueError("Queue identity mismatch")
            evidence.append(fact)
            used.add(fid)
        first = evidence[0]
        cases.append(
            {
                "review_id": rid,
                "queue_index": index,
                "subject_type": first["subject_type"],
                "subject": first["subject"],
                "hero_zh": row["hero_zh"],
                "name_zh": row["name_zh"],
                "mechanism": first["mechanism"],
                "mechanism_zh": row["mechanism_zh"],
                "definition": vocabulary[first["mechanism"]]["definition"],
                "condition": first["condition"],
                "evidence": evidence,
            }
        )
    pending = {f["fact_id"] for f in facts.values() if f["review"] == "needs_review"}
    if used != pending:
        raise ValueError("Incomplete pending-fact coverage")
    fields = [f for f in facts.values() if f["review"] == "auto"]
    if len(used) + len(fields) != len(facts):
        raise ValueError("Unsupported fact review state")
    return cases, fields


def template_rows(cases, packet_id):
    return [
        {
            "packet_id": packet_id,
            "review_id": case["review_id"],
            "reviewer": "Claude",
            "decision": None,
            "interpretation_zh": "",
            "conditions_zh": "",
            "reason_zh": "",
            "evidence_fact_ids": [],
        }
        for case in cases
    ]


def compare_reviews(cases, codex_rows, claude_rows, packet_id, *, require_complete=False):
    """Validate a return file and list label comparisons, not semantic consensus.

    Missing/null rows remain pending. A Claude-only judgment goes to Codex for
    review; it is never filled in as a fictitious Codex agreement.
    """
    lookup = {c["review_id"]: c for c in cases}
    if len(lookup) != len(cases):
        raise ValueError("Duplicate packet case")
    codex = {}
    for row in codex_rows:
        rid = row["review_id"]
        if rid not in lookup or rid in codex:
            raise ValueError("Invalid Codex review ID")
        if row["assistant_decision"] not in {"accept", "reject", "uncertain"}:
            raise ValueError("Invalid Codex decision")
        codex[rid] = row
    claude = {}
    for row in claude_rows:
        if not isinstance(row, dict) or set(row) != REVIEW_FIELDS:
            raise ValueError("Return row must use the exact review template fields")
        if row["packet_id"] != packet_id or row["reviewer"] != "Claude":
            raise ValueError("Wrong packet or declared reviewer")
        rid = row["review_id"]
        if not isinstance(rid, str) or rid not in lookup or rid in claude:
            raise ValueError("Unknown or duplicate returned review ID")
        decision = row["decision"]
        if decision not in (None, "accept", "reject", "uncertain"):
            raise ValueError("Invalid returned decision")
        for key in ("reason_zh", "interpretation_zh", "conditions_zh"):
            if not isinstance(row[key], str):
                raise ValueError("Review explanations must be strings")
            if decision is not None and not row[key].strip():
                raise ValueError("Every judgment needs interpretation, conditions and reason")
        cited = row["evidence_fact_ids"]
        allowed = {f["fact_id"] for f in lookup[rid]["evidence"]}
        if not isinstance(cited, list) or any(not isinstance(f, str) for f in cited):
            raise ValueError("Evidence IDs must be a string list")
        if len(set(cited)) != len(cited) or not set(cited) <= allowed:
            raise ValueError("Duplicate or cross-case evidence citation")
        if decision in ("accept", "reject") and not cited:
            raise ValueError("Acceptance/rejection needs evidence; use uncertain for a source gap")
        claude[rid] = row
    reviewed = sum(row["decision"] is not None for row in claude.values())
    if require_complete and reviewed != len(cases):
        raise ValueError(f"Review incomplete: {reviewed}/{len(cases)} judgments")
    comparisons = []
    for case in cases:
        rid = case["review_id"]
        prior, returned = codex.get(rid), claude.get(rid)
        first = prior["assistant_decision"] if prior else None
        second = returned["decision"] if returned else None
        if second is None:
            status = "pending_claude"
        elif second == "uncertain" or first == "uncertain":
            status = "needs_evidence_review"
        elif first is None:
            status = "needs_codex_review"
        elif first == second:
            status = "same_label_check_conditions"
        else:
            status = "label_disagreement"
        user_decision = prior.get("user_decision") if prior else None
        comparisons.append(
            {
                "review_id": rid,
                "queue_index": case["queue_index"],
                "hero_zh": case["hero_zh"],
                "name_zh": case["name_zh"],
                "mechanism": case["mechanism"],
                "condition": case["condition"],
                "codex_decision": first,
                "claude_decision": second,
                "status": status,
                "user_decision": user_decision,
                "conflicts_with_user_label": bool(
                    user_decision and second in ("accept", "reject") and user_decision != second
                ),
                "codex_interpretation": prior.get("interpretation_zh") if prior else None,
                "codex_conditions": prior.get("conditions_zh") if prior else None,
                "claude_return": returned,
            }
        )
    return {
        "schema": "mechanics-cross-review-comparison/1",
        "packet_id": packet_id,
        "total_groups": len(cases),
        "codex_reviewed": len(codex),
        "claude_reviewed": reviewed,
        "claude_complete": reviewed == len(cases),
        "counts": dict(Counter(c["status"] for c in comparisons)),
        "user_label_conflicts": sum(c["conflicts_with_user_label"] for c in comparisons),
        "note": "Same labels do not certify conditions or game truth; facts stay unchanged.",
        "comparisons": comparisons,
    }


def json_lines(rows):
    return "".join(canonical(row) + "\n" for row in rows)
