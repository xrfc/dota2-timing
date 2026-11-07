"""User feedback on fact rows, resolved by identity instead of by input order (U101).

Every feedback entry gets a stable id from its content, so importing it twice changes nothing.
A correction names the feedback ids it resolves; a wrong it does not name stays open. Feedback
records what the row claimed when the user looked; an "ok" only confirms a row that still claims
the same thing.
"""

import hashlib

DISPUTED = "disputed_by_user"
SPOT_CHECK = "user_spot_check"
KEPT_PREFIXES = ("user:", "field")


def feedback_id(entry):
    text = "|".join(str(entry.get(key, "")) for key in ("review_id", "verdict", "note", "at"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def claim_of(row):
    """What a row asserts; a confirmation only carries over while this stays the same."""
    return {"mechanism": row["mechanism"], "decision": row["decision"]}


def _ordered(entries):
    unique = {}
    for entry in entries:
        unique.setdefault(entry["feedback_id"], entry)
    return sorted(unique.values(), key=lambda e: (e.get("at", ""), e["feedback_id"]))


def resolve(row, entries, corrections):
    """Return (basis, open wrong ids, explanation) for one row from all its feedback.

    The row's own user ruling or field basis is kept unless an open wrong disputes it; any other
    basis is treated as AI-only before feedback is applied.
    """
    entries = _ordered(entries)
    wrongs = [e for e in entries if e["verdict"] == "wrong"]
    resolved = {fid for c in corrections for fid in c["resolves"]}
    open_wrongs = [e["feedback_id"] for e in wrongs if e["feedback_id"] not in resolved]
    if open_wrongs:
        return DISPUTED, open_wrongs, "有未解决的标错"
    covering = [c for c in corrections if set(c["resolves"]) & {e["feedback_id"] for e in wrongs}]
    standalone = [c for c in corrections if not c["resolves"]]
    if covering or standalone:
        latest = max(
            (e for e in wrongs if any(e["feedback_id"] in c["resolves"] for c in covering)),
            key=lambda e: (e.get("at", ""), e["feedback_id"]),
            default=None,
        )
        chosen = (
            next(c for c in covering if latest["feedback_id"] in c["resolves"])
            if latest
            else standalone[-1]
        )
        return chosen["basis"], [], "按纠正记录"
    if row["basis"].startswith(KEPT_PREFIXES) and not row["basis"].startswith("user_"):
        return row["basis"], [], "保留原有裁定"
    current = claim_of(row)
    if any(e["verdict"] == "ok" and e.get("claim") == current for e in entries):
        return SPOT_CHECK, [], "抽查确认，且事实内容和当时一致"
    if any(e["verdict"] == "ok" and e.get("claim") is None for e in entries):
        return "two_ai", [], "抽查时的内容无法确认，暂不算确认"
    if any(e["verdict"] == "ok" for e in entries):
        return "two_ai", [], "事实内容在抽查后变了，旧确认不沿用"
    return "two_ai", [], "没有能确认的反馈"
