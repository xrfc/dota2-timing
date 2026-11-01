"""Validate round-2 coverage and provenance offline; never adjudicate game semantics."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def resolve(pointer, cache):
    file = pointer["file"]
    if file not in cache:
        cache[file] = json.loads((ROOT / file).read_text(encoding="utf-8"))
    value = cache[file]
    for part in pointer["path"].strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def main():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    for file, expected in manifest["source_sha256"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == expected, file
    packet = ROOT / "knowledge/mechanics/cross-review/v1"
    cases = {r["review_id"]: r for r in read_lines(packet / "cases.jsonl")}
    first = ROOT / "knowledge/mechanics/reviews/claude-round-001"
    claude = {r["review_id"]: r for r in read_lines(first / "claude-review.jsonl")}
    with (first / "codex-review-queue.csv").open(encoding="utf-8", newline="") as stream:
        queue = list(csv.DictReader(stream))
    p1 = [r["review_id"] for r in queue if r["priority"] == "P1"]
    delta = json.loads(
        (ROOT / "knowledge/mechanics/extractions/v3/delta-vs-v2.json").read_text(encoding="utf-8")
    )
    removed = {r["review_id"] for r in delta["removed"]}
    rows = read_lines(OUT / "codex-review.jsonl")
    stale = read_lines(OUT / "stale-upgrade-review.jsonl")
    assert [r["review_id"] for r in rows] == [rid for rid in p1 if rid not in removed]
    assert len(p1) == 389 and len(rows) == 387 and len(stale) == 19
    assert len({r["review_id"] for r in rows}) == len(rows)
    assert {r["review_id"] for r in stale} == removed
    assert len(set(p1) & removed) == 2
    sources = read_lines(OUT / "source-reads.jsonl")
    source_map = {r["ref"]: r for r in sources}
    assert len(source_map) == len(sources)
    cache = {}
    for source in sources:
        assert resolve(source["pointer"], cache) == source["value"], source["ref"]
    for row in rows + stale:
        rid = row["review_id"]
        assert row["decision"] in {"accept", "reject", "uncertain"}
        assert row["reason_zh"] and row["conditions_zh"]
        assert row["evidence_fact_ids"] == [e["fact_id"] for e in cases[rid]["evidence"]]
        assert all(ref in source_map for ref in row["source_read_refs"])
    for row in rows:
        rid = row["review_id"]
        assert row["claude_decision"] == claude[rid]["decision"]
        differs = row["decision"] != claude[rid]["decision"]
        assert (row["comparison"] == "label_disagreement") == differs
        assert bool(row["difference_reason_zh"]) == differs
        assert row["needs_user_ruling"] == (row["decision"] == "uncertain")
        assert queue[row["queue_position"] - 1]["review_id"] == rid
    for row in stale:
        assert row["review_scope"] == "stale_upgrade_policy_only"
        assert row["semantic_decision"] is None
        assert row["has_upgrade"] is False and row["granted_by_upgrade"] is False
        flags = [
            source_map[ref]["value"]
            for ref in row["source_read_refs"]
            if "/ability_has_" in ref or "/ability_is_granted_by_" in ref
        ]
        assert len(flags) == 4 and all(value is False for value in flags)
    controls = json.loads((OUT / "granted-ability-controls.json").read_text(encoding="utf-8"))
    assert controls
    for control in controls:
        raw = source_map[control["source_read_ref"]]["value"]
        kind = control["upgrade"]
        assert raw["ability_has_" + kind] is False
        assert raw["ability_is_granted_by_" + kind] is True
        assert control["not_removed"]
    comparison = json.loads((OUT / "comparison.json").read_text(encoding="utf-8"))["results"]
    assert [r["review_id"] for r in comparison] == [r["review_id"] for r in rows]
    for compared, row in zip(comparison, rows, strict=True):
        assert all(row[key] == value for key, value in compared.items())
    assert dict(Counter(r["decision"] for r in rows)) == manifest["decision_counts"]
    for key, value in {
        "disagreements": sum(r["comparison"] == "label_disagreement" for r in rows),
        "needs_user_ruling": sum(r["needs_user_ruling"] for r in rows),
        "user_decision_conflicts": sum(r["user_decision_conflict"] for r in rows),
    }.items():
        assert manifest[key] == value
    print(
        "Round 2 validated: P1 389 covered (387 semantic + 2 policy-only); "
        "19 stale checks; 19 label differences; 16 pending rulings; source hashes match."
    )


if __name__ == "__main__":
    main()
