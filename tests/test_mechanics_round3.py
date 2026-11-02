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


ROUND4 = json.loads((REVIEWS / "claude-round-004/resolution.json").read_text(encoding="utf-8"))


def test_round4_applies_user_rulings_to_every_pending_row():
    assert (
        hashlib.sha256((ROOT / ROUND4["input"]["round3"]).read_bytes()).hexdigest()
        == (ROUND4["input"]["round3_sha256"])
    )
    pending = {row["review_id"]: row for row in DOC["rows"]}
    rows = {row["review_id"]: row for row in ROUND4["rows"]}
    assert set(rows) == set(pending)
    expected = {"innate_break": "reject", "damage_return": "accept", "invisibility": "reject"}
    for review_id, row in rows.items():
        source = pending[review_id]
        if source["status"] == "resolved_ai_agreement":
            assert row["final_decision"] == "accept" and row["basis"] == "ai_agreement"
        elif source["question"] == "summons":
            wisp = row["subject"] == "keeper_of_the_light_will_o_wisp"
            assert row["final_decision"] == ("accept" if wisp else "reject")
        else:
            assert row["final_decision"] == expected[source["question"]]
            assert row["basis"] == "user_ruling"


def test_round4_totals_follow_from_round1():
    round1 = jsonl(ROOT / ROUND4["input"]["claude_round1"])
    final = {row["review_id"]: row["decision"] for row in round1}
    final.update({row["review_id"]: row["final_decision"] for row in ROUND4["rows"]})
    counts = {}
    for decision in final.values():
        counts[decision] = counts.get(decision, 0) + 1
    assert counts == ROUND4["totals_after"] == {"accept": 1271, "reject": 280}


ROUND5 = json.loads((REVIEWS / "claude-round-005/resolution.json").read_text(encoding="utf-8"))


def test_round5_flips_exactly_the_confirmed_innate_proposal():
    for key in ("proposal", "round4"):
        data = (ROOT / ROUND5["input"][key]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == ROUND5["input"][key + "_sha256"]
    proposal = json.loads((ROOT / ROUND5["input"]["proposal"]).read_text(encoding="utf-8"))
    subjects = {row["subject"] for row in ROUND5["rows"]}
    assert subjects == {item["subject"] for item in proposal["candidates"]}
    assert len(ROUND5["rows"]) == 24
    assert all(
        row["mechanism"] == "break_sensitive"
        and (row["previous_decision"], row["final_decision"]) == ("accept", "reject")
        for row in ROUND5["rows"]
    )
    round1 = jsonl(ROOT / ROUND4["input"]["claude_round1"])
    final = {row["review_id"]: row["decision"] for row in round1}
    final.update({row["review_id"]: row["final_decision"] for row in ROUND4["rows"]})
    final.update({row["review_id"]: row["final_decision"] for row in ROUND5["rows"]})
    counts = {}
    for decision in final.values():
        counts[decision] = counts.get(decision, 0) + 1
    assert counts == ROUND5["totals_after"] == {"accept": 1247, "reject": 304}


SPOT = REVIEWS / "u5-spot-check"


def test_codex_spot_check_queue_is_sample_minus_user_marks_and_codex_p1():
    queue = json.loads((SPOT / "codex-queue.json").read_text(encoding="utf-8"))
    for name, digest in queue["input_sha256"].items():
        assert hashlib.sha256((REVIEWS / name).read_bytes()).hexdigest() == digest
    sample = json.loads(
        (REVIEWS / "claude-round-001/spot-check-sample.json").read_text(encoding="utf-8")
    )
    marked = json.loads((SPOT / "user-verdicts-2026-11-02.json").read_text(encoding="utf-8"))
    codex = {row["review_id"] for row in jsonl(REVIEWS / "codex-round-002/codex-review.jsonl")}
    current = {
        line.split(",", 1)[0]
        for line in (ROOT / "knowledge/mechanics/extractions/v3/review.csv")
        .read_text(encoding="utf-8")
        .splitlines()[1:]
    }
    remaining = [
        group["id"]
        for group in sample["groups"]
        if group["id"] not in marked["verdicts"] and group["id"] not in codex
    ]
    expected = [review_id for review_id in remaining if review_id in current]
    excluded = [review_id for review_id in remaining if review_id not in current]
    assert [group["review_id"] for group in queue["groups"]] == expected
    assert [group["review_id"] for group in queue["excluded_not_in_v3"]] == excluded
    assert (len(expected), len(excluded), len(marked["verdicts"])) == (379, 8, 93)
    assert set(marked["verdicts"]) <= {group["id"] for group in sample["groups"]}
    assert all(group["current_decision"] in ("accept", "reject") for group in queue["groups"])
