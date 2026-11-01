"""Cross-review identity, provenance and incomplete-review regressions."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from dota_items.data.mechanics_cross_review import compare_reviews, make_cases, template_rows
from dota_items.data.mechanics_facts import digest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def small():
    cases = [
        {
            "review_id": str(n),
            "queue_index": n,
            "hero_zh": "英雄",
            "name_zh": "技能",
            "mechanism": "stun",
            "condition": {"requires_shard": n == 2},
            "evidence": [{"fact_id": f"f{n}"}],
        }
        for n in (1, 2)
    ]
    prior = [
        {
            "review_id": "1",
            "assistant_decision": "accept",
            "user_decision": "accept",
            "interpretation_zh": "对敌眩晕",
            "conditions_zh": "命中",
        }
    ]
    rows = template_rows(cases, "packet")
    for n, row in enumerate(rows, 1):
        row.update(
            decision="accept",
            interpretation_zh="对敌眩晕",
            conditions_zh="命中",
            reason_zh="原文明确说明",
            evidence_fact_ids=[f"f{n}"],
        )
    return cases, prior, rows


def test_unreviewed_codex_is_not_fabricated_agreement(small):
    cases, prior, rows = small
    result = compare_reviews(cases, prior, rows, "packet", require_complete=True)
    assert result["claude_complete"]
    assert result["counts"] == {"same_label_check_conditions": 1, "needs_codex_review": 1}
    assert result["comparisons"][1]["codex_decision"] is None


def test_partial_and_uncertain_never_pass_as_consensus(small):
    cases, prior, rows = small
    rows[0]["decision"] = "uncertain"
    result = compare_reviews(cases, prior, rows[:1], "packet")
    assert result["counts"] == {"needs_evidence_review": 1, "pending_claude": 1}
    assert result["claude_reviewed"] == 1
    with pytest.raises(ValueError, match="incomplete"):
        compare_reviews(cases, prior, rows[:1], "packet", require_complete=True)
    empty = template_rows(cases, "packet")
    assert compare_reviews(cases, prior, empty, "packet")["claude_reviewed"] == 0


def test_conflict_with_user_label_is_preserved(small):
    cases, prior, rows = small
    rows[0]["decision"] = "reject"
    result = compare_reviews(cases, prior, rows, "packet")
    assert result["user_label_conflicts"] == 1
    assert result["comparisons"][0]["status"] == "label_disagreement"
    assert prior[0]["user_decision"] == "accept"


@pytest.mark.parametrize(
    "change", ["packet", "id", "duplicate", "citation", "reason", "reviewer", "fields"]
)
def test_returned_wrong_identity_and_evidence_rejected(small, change):
    cases, prior, rows = small
    rows = copy.deepcopy(rows)
    if change == "packet":
        rows[0]["packet_id"] = "old-packet"
    elif change == "id":
        rows[0]["review_id"] = "unknown"
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif change == "citation":
        rows[0]["evidence_fact_ids"] = ["f2"]
    elif change == "reason":
        rows[0]["reason_zh"] = ""
    elif change == "reviewer":
        rows[0]["reviewer"] = "Codex"
    else:
        rows[0]["condition"] = "changed"
    with pytest.raises(ValueError):
        compare_reviews(cases, prior, rows, "packet")


def test_grouping_rejects_missing_or_wrong_group_facts():
    fact = {
        "fact_id": "f",
        "subject_type": "item",
        "subject": "x",
        "mechanism": "stun",
        "condition": {},
        "review": "needs_review",
    }
    rid = digest(["item", "x", "stun", {}])[:20]
    row = {
        "review_id": rid,
        "fact_ids": "f",
        "subject": "x",
        "mechanism": "stun",
        "hero_zh": "",
        "name_zh": "物品",
        "mechanism_zh": "眩晕",
    }
    vocab = {"stun": {"definition": "眩晕"}}
    assert len(make_cases({"facts": [fact]}, [row], vocab)[0]) == 1
    with pytest.raises(ValueError, match="coverage"):
        make_cases({"facts": [fact]}, [], vocab)
    with pytest.raises(ValueError):
        make_cases({"facts": [fact]}, [{**row, "review_id": "wrong"}], vocab)


def cli_module():
    spec = importlib.util.spec_from_file_location(
        "cross_review_cli", ROOT / "scripts/mechanics_cross_review.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_packet_complete_listing_no_overwrite_and_empty_return(tmp_path):
    script = cli_module()
    packet = tmp_path / "packet"
    summary = script.build(packet)
    assert summary == {
        "groups": 1551,
        "pending_evidence_rows": 2801,
        "field_observations": 2006,
        "total_evidence_rows": 4807,
        "subjects": 943,
        "mechanisms": 45,
        "codex_semantically_reviewed": 24,
        "codex_not_yet_reviewed": 1527,
        "claude_reviewed": 0,
        "prior_user_audit_rows": 8,
    }
    manifest = script.verify(packet)
    assert len(list((packet / "mechanisms").glob("*.md"))) == 45
    assert len(script.read_lines(packet / "subjects.jsonl")) == 943
    returned = packet / "claude-template.jsonl"
    comparison = script.compare(packet, returned, tmp_path / "comparison")
    assert comparison["claude_reviewed"] == 0
    assert comparison["counts"] == {"pending_claude": 1551}
    with pytest.raises(ValueError, match="incomplete"):
        script.compare(packet, returned, tmp_path / "bad", require_complete=True)
    assert not (tmp_path / "bad").exists()
    with pytest.raises(ValueError, match="exists"):
        script.build(packet)
    assert script.verify(packet) == manifest
    (packet / "cases.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="changed"):
        script.verify(packet)


def test_packet_verifier_rejects_outside_path_before_read(tmp_path):
    script = cli_module()
    packet = tmp_path / "packet"
    script.build(packet)
    manifest = json.loads((packet / "manifest.json").read_text())
    manifest["output_sha256"] = {"../secret": "0" * 64}
    (packet / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsafe"):
        script.verify(packet)
