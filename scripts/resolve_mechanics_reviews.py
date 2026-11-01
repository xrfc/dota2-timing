"""Combine review rounds into the current decision per review group.

Precedence: user decision file > Claude round 1 (which already carries U33/U35/U5
changes). Codex round 2 is checked against Claude: every difference must be settled
by a user decision, otherwise the build fails. Groups removed in evidence v3
(stale upgrade text) are flagged, not re-judged. Inputs are never modified.

    python scripts/resolve_mechanics_reviews.py \
        --output knowledge/mechanics/reviews/resolution-001
"""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = "knowledge/mechanics/cross-review/v1/cases.jsonl"
CLAUDE = "knowledge/mechanics/reviews/claude-round-001/claude-review.jsonl"
NEW_V2 = "knowledge/mechanics/reviews/claude-round-002/new-in-v2.jsonl"
CODEX = "knowledge/mechanics/reviews/codex-round-002/codex-review.jsonl"
V3_DELTA = "knowledge/mechanics/extractions/v3/delta-vs-v2.json"
V3_REVIEW = "knowledge/mechanics/extractions/v3/review.csv"
USER = ("knowledge/mechanics/reviews/user-decisions/U37.json",)
INPUTS = (CASES, CLAUDE, NEW_V2, CODEX, V3_DELTA, V3_REVIEW) + USER


def lines(repo, name):
    return [json.loads(x) for x in (repo / name).read_text(encoding="utf-8").splitlines()]


def resolve(repo=ROOT):
    cases = {c["review_id"]: c for c in lines(repo, CASES)}
    with (repo / V3_REVIEW).open(encoding="utf-8", newline="") as stream:
        current = {r["review_id"]: r for r in csv.DictReader(stream)}
    claude = {r["review_id"]: r for r in lines(repo, CLAUDE)}
    claude_round1 = set(claude)
    for row in lines(repo, NEW_V2):
        if row["review_id"] in claude or row["review_id"] not in current:
            raise ValueError(f"New-in-v2 decision does not match v3 groups {row['review_id']}")
        claude[row["review_id"]] = row
        r = current[row["review_id"]]
        cases[row["review_id"]] = {
            "subject": r["subject"],
            "name_zh": r["name_zh"],
            "mechanism": r["mechanism"],
            "condition": json.loads(r["condition"]),
        }
    codex = {r["review_id"]: r for r in lines(repo, CODEX)}
    stale = {
        r["review_id"] for r in json.loads((repo / V3_DELTA).read_text(encoding="utf-8"))["removed"]
    }
    user, additions = {}, []
    for name in USER:
        doc = json.loads((repo / name).read_text(encoding="utf-8"))
        for row in doc["decisions"]:
            if row["review_id"] not in cases or row["review_id"] in user:
                raise ValueError(f"Unknown or repeated user decision {row['review_id']}")
            user[row["review_id"]] = {**row, "by": doc["decision"]}
        additions += [{**a, "by": doc["decision"]} for a in doc.get("additions", [])]
    if set(claude) != set(cases) or not set(current) <= set(cases):
        raise ValueError("Claude rounds 1-2 must cover every v1 and v3 group")
    rows = []
    for rid in sorted(cases):
        c, x, u = claude[rid], codex.get(rid), user.get(rid)
        if x and x["decision"] != c["decision"] and not u:
            raise ValueError(f"Unsettled Claude/Codex difference {rid}")
        rows.append(
            {
                "review_id": rid,
                "subject": cases[rid]["subject"],
                "name_zh": cases[rid]["name_zh"],
                "mechanism": cases[rid]["mechanism"],
                "condition": cases[rid]["condition"],
                "decision": u["decision"] if u else c["decision"],
                "decided_by": u["by"]
                if u
                else "claude-round-001"
                if rid in claude_round1
                else "claude-round-002",
                "claude": c["decision"],
                "codex": x["decision"] if x else None,
                "user_reason_zh": u["reason_zh"] if u else None,
                "in_current_evidence": rid in current,
                "not_current_reason": None
                if rid in current
                else "stale_upgrade_text"
                if rid in stale
                else "dropped_by_v2_rules",
            }
        )
    live = [r for r in rows if r["in_current_evidence"]]
    summary = {
        "schema": "mechanics-resolution/1",
        "patch_verified": False,
        "groups": len(rows),
        "decisions": dict(Counter(r["decision"] for r in rows)),
        "current_evidence_groups": len(live),
        "current_decisions": dict(Counter(r["decision"] for r in live)),
        "not_current": dict(
            Counter(r["not_current_reason"] for r in rows if r["not_current_reason"])
        ),
        "decided_by": dict(Counter(r["decided_by"] for r in rows)),
        "codex_reviewed": sum(r["codex"] is not None for r in rows),
        "codex_differences": sum(r["codex"] not in (None, r["claude"]) for r in rows),
        "user_additions": len(additions),
        "note": (
            "Claude round 1 already includes user answers U33/U35 and U5 spot-check changes. "
            "Codex reviewed P1 only; P2/P3 rest on Claude plus user spot-checks. "
            "current_* counts only groups in evidence v3 (review.csv); the rest were dropped "
            "by v2 rules or rest only on stale upgrade text."
        ),
    }
    return rows, additions, summary


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    rows, additions, summary = resolve(repo)
    output.mkdir(parents=True)
    (output / "resolved.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    )
    for name, value in (("additions.json", additions), ("summary.json", summary)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n")
    digest = {n: hashlib.sha256((repo / n).read_bytes()).hexdigest() for n in INPUTS}
    digest["scripts/resolve_mechanics_reviews.py"] = hashlib.sha256(
        (repo / "scripts/resolve_mechanics_reviews.py").read_bytes()
    ).hexdigest()
    manifest = {
        "schema": "mechanics-resolution-receipt/1",
        "input_sha256": digest,
        "output_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    print(json.dumps(run(parser.parse_args().output), ensure_ascii=False))


if __name__ == "__main__":
    main()
