"""Claude round 3 resolves exactly the Codex/Claude P1 disagreements without rewriting inputs."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "knowledge/mechanics/reviews"
DOC = json.loads((REVIEWS / "claude-round-003/resolution.json").read_text(encoding="utf-8"))


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_inputs_are_unchanged():
    for key in ("codex_round2", "claude_round1"):
        data = (ROOT / DOC["input"][key]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == DOC["input"][key + "_sha256"]


def test_rows_cover_exactly_the_disagreements():
    codex = jsonl(ROOT / DOC["input"]["codex_round2"])
    claude = {row["review_id"]: row for row in jsonl(ROOT / DOC["input"]["claude_round1"])}
    expected = {row["review_id"]: row for row in codex if row["decision"] != row["claude_decision"]}
    rows = {row["review_id"]: row for row in DOC["rows"]}
    assert set(rows) == set(expected) and len(DOC["rows"]) == len(rows) == 19
    for review_id, row in rows.items():
        source = expected[review_id]
        assert row["codex_decision"] == source["decision"]
        assert row["claude_round1_decision"] == claude[review_id]["decision"] == "reject"
        assert row["evidence_fact_ids"] == source["evidence_fact_ids"]


def test_only_codex_accepts_are_resolved_and_uncertain_go_to_user():
    for row in DOC["rows"]:
        if row["status"] == "resolved_ai_agreement":
            assert row["codex_decision"] == "accept" and row["claude_round3"] == "accept"
            assert row["question"] is None
        else:
            assert row["status"] == "needs_user_ruling"
            assert row["codex_decision"] == "uncertain"
            assert row["claude_round3"] == "pending_user"
            assert row["question"] in DOC["questions"]
    statuses = [row["status"] for row in DOC["rows"]]
    assert statuses.count("resolved_ai_agreement") == 3
