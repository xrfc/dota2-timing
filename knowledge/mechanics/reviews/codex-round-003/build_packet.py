"""Build blind Codex batches for U5 sample groups no prior Codex round reviewed.

Input deliberately omits Claude's decisions so round 3 is independent; run from repo root.
"""

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
R = ROOT / "knowledge/mechanics"
BATCH_SIZE = 30
CONTEXT_KEYS = (
    "name_en",
    "name_zh",
    "description_en",
    "description_zh",
    "notes_en",
    "notes_zh",
    "scepter_loc",
    "shard_loc",
    "upgrade_text",
    "innate",
    "granted_by_scepter",
    "granted_by_shard",
    "raw_mechanics",
    "description",
    "notes",
    "lore",
)


def read_lines(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def facts_by_group():
    """Evidence for v2-only groups comes from the v3 fact package, keyed by fact id."""
    data = json.loads((R / "extractions/v3/facts-v3.json").read_text(encoding="utf-8"))
    facts = data.get("facts", data)
    return {fact["fact_id"]: fact for fact in facts}


def slim_context(subject):
    context = subject["context"]
    return {key: context[key] for key in CONTEXT_KEYS if context.get(key) not in (None, "", [], {})}


def main(verdict_dir):
    sample = json.loads(
        (R / "reviews/claude-round-001/spot-check-sample.json").read_text(encoding="utf-8")
    )
    marked = {Path(p).stem for p in glob.glob(str(Path(verdict_dir) / "*.json"))}
    prior = {r["review_id"] for r in read_lines(R / "reviews/codex-round-002/codex-review.jsonl")}
    stale = {
        r["review_id"] for r in read_lines(R / "reviews/codex-round-002/stale-upgrade-review.jsonl")
    }
    cases = {r["review_id"]: r for r in read_lines(R / "cross-review/v1/cases.jsonl")}
    subjects = read_lines(R / "cross-review/v1/subjects.jsonl")
    by_subject = {}
    for subject in subjects:
        by_subject.setdefault(subject["subject"], []).append(subject)
    v2 = {r["review_id"]: r for r in read_lines(R / "reviews/claude-round-002/new-in-v2.jsonl")}
    facts = facts_by_group()
    vocabulary = {
        m["id"]: m
        for m in json.loads((R / "vocabulary-v3.json").read_text(encoding="utf-8"))["mechanisms"]
    }

    groups, skipped = [], []
    for group in sample["groups"]:
        rid = group["id"]
        if rid in marked or rid in prior:
            continue
        if rid in stale:
            skipped.append({"review_id": rid, "why": "v3已隔离过时升级文字；第2轮只做过时处理核对"})
            continue
        if rid in cases:
            case = cases[rid]
            evidence = case["evidence"]
        else:
            evidence = [facts[f] for f in v2[rid]["evidence_fact_ids"] if f in facts]
            if not evidence:
                skipped.append({"review_id": rid, "why": "v3事实包中找不到证据"})
                continue
            first = evidence[0]
            case = {
                "subject": first["subject"],
                "subject_type": first["subject_type"],
                "mechanism": first["mechanism"],
                "condition": first["condition"],
                "name_zh": group.get("n", ""),
                "hero_zh": "",
            }
        context = by_subject.get(case["subject"], [])
        mechanism = vocabulary[case["mechanism"]]
        groups.append(
            {
                "review_id": rid,
                "subject": case["subject"],
                "subject_zh": group.get("n", ""),
                "mechanism": case["mechanism"],
                "mechanism_zh": mechanism["zh"],
                "definition": mechanism["definition"],
                "definition_note": mechanism.get("note", ""),
                "condition": case["condition"],
                "evidence": [
                    {"quote": e.get("quote"), "value": e.get("value"), "pointer": e.get("pointer")}
                    for e in evidence
                ],
                "context": [slim_context(s) for s in context[:2]],
            }
        )
    for old in (OUT / "batches").glob("*.json"):
        old.unlink()
    for index in range(0, len(groups), BATCH_SIZE):
        name = OUT / "batches" / f"batch-{index // BATCH_SIZE:03d}.json"
        name.write_text(
            json.dumps(groups[index : index + BATCH_SIZE], ensure_ascii=False, indent=0) + "\n",
            encoding="utf-8",
        )
    (OUT / "packet-summary.json").write_text(
        json.dumps(
            {
                "groups": len(groups),
                "batch_size": BATCH_SIZE,
                "skipped": skipped,
                "excluded_marked": len(marked),
                "blind_to_claude": True,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(len(groups), "groups", len(skipped), "skipped")


if __name__ == "__main__":
    main(sys.argv[1])
