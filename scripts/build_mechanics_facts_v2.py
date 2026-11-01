"""Build MK-T3 evidence v2 and compare it with v1 and Claude's round-1 review.

Writes to a new directory only. v1 (scripts/build_mechanics_facts.py) is untouched.

    PYTHONPATH=src python scripts/build_mechanics_facts_v2.py \
        --output knowledge/mechanics/extractions/v2
"""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from dota_items.data.mechanics_facts import coverage
from dota_items.data.mechanics_facts_v2 import (
    INPUTS,
    VOCAB,
    build_facts,
    group_key,
    load_facts,
)
from dota_items.data.source_io import parse_source_json, read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
V1_CASES = "knowledge/mechanics/cross-review/v1/cases.jsonl"
ROUND1 = "knowledge/mechanics/reviews/claude-round-001/claude-review.jsonl"
IMPLEMENTATION = (
    "src/dota_items/data/mechanics.py",
    "src/dota_items/data/mechanics_facts.py",
    "src/dota_items/data/mechanics_rules.py",
    "src/dota_items/data/mechanics_facts_v2.py",
    "src/dota_items/data/mechanics_rules_v2.py",
    "scripts/build_mechanics_facts_v2.py",
)
FIELDS = (
    "review_id",
    "status_vs_v1",
    "round1_decision",
    "subject",
    "hero_zh",
    "name_zh",
    "mechanism",
    "mechanism_zh",
    "condition",
    "fact_ids",
    "quotes",
    "sources",
    "decision",
    "reason",
)


def read_jsonl(path):
    return [json.loads(line) for line in read_source_bytes(path).decode().splitlines()]


def load_sources(repo):
    raw = {name: read_source_bytes(repo / name) for name in INPUTS}
    sources = {
        name: parse_source_json(value)
        if name.endswith(".json")
        else {"text": value.decode("utf-8")}
        for name, value in raw.items()
    }
    return raw, sources


def review_rows(doc, terms, v1_ids, round1):
    groups = {}
    for fact in doc["facts"]:
        if fact["review"] == "needs_review":
            groups.setdefault(group_key(fact), []).append(fact)
    names = {s["subject"]: s for s in doc["subjects"]}
    rows = []
    for key in sorted(groups):
        facts = groups[key]
        first = facts[0]
        subject = names[first["subject"]]
        rows.append(
            {
                "review_id": key,
                "status_vs_v1": "same_group" if key in v1_ids else "new_in_v2",
                "round1_decision": round1.get(key, ""),
                "subject": first["subject"],
                "hero_zh": subject.get("hero_name_zh", ""),
                "name_zh": subject["name_zh"],
                "mechanism": first["mechanism"],
                "mechanism_zh": terms[first["mechanism"]]["zh"],
                "condition": json.dumps(first["condition"], ensure_ascii=False, sort_keys=True),
                "fact_ids": " | ".join(f["fact_id"] for f in facts),
                "quotes": " | ".join(dict.fromkeys(f["quote"] for f in facts)),
                "sources": " | ".join(
                    f["pointer"]["file"] + "#" + f["pointer"]["path"] for f in facts
                ),
                "decision": "",
                "reason": "",
            }
        )
    return rows


def delta(rows, v1_cases, round1):
    v2_ids = {r["review_id"] for r in rows}
    dropped = [c for c in v1_cases if c["review_id"] not in v2_ids]
    return {
        "schema": "mechanics-extraction-delta/1",
        "patch_verified": False,
        "v1_groups": len(v1_cases),
        "v2_groups": len(rows),
        "same_groups": sum(r["status_vs_v1"] == "same_group" for r in rows),
        "new_in_v2": [
            {k: r[k] for k in ("review_id", "subject", "name_zh", "mechanism", "quotes")}
            for r in rows
            if r["status_vs_v1"] == "new_in_v2"
        ],
        "dropped_from_v1_by_round1_decision": dict(
            Counter(round1.get(c["review_id"], "unreviewed") for c in dropped)
        ),
        "dropped_from_v1": [
            {
                "review_id": c["review_id"],
                "subject": c["subject"],
                "name_zh": c["name_zh"],
                "mechanism": c["mechanism"],
                "round1_decision": round1.get(c["review_id"], ""),
            }
            for c in dropped
        ],
        "kept_by_round1_decision": dict(
            Counter(
                r["round1_decision"] or "new" for r in rows if r["status_vs_v1"] == "same_group"
            )
        ),
        "note": (
            "Round-1 decisions are Claude's, partly revised by user answers U33/U35; "
            "they are not user approval of every group. Dropping a group v1 produced is only "
            "safe where round 1 rejected it; see dropped_from_v1_by_round1_decision."
        ),
    }


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    raw, sources = load_sources(repo)
    doc = build_facts(sources)
    load_facts(doc, sources)
    terms = {m["id"]: m for m in sources[VOCAB]["mechanisms"]}
    report = coverage(doc, terms)
    v1_cases = read_jsonl(repo / V1_CASES)
    round1 = {row["review_id"]: row["decision"] for row in read_jsonl(repo / ROUND1)}
    rows = review_rows(doc, terms, {c["review_id"] for c in v1_cases}, round1)
    report["review_groups"] = len(rows)
    changes = delta(rows, v1_cases, round1)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (
        ("facts-v2.json", doc),
        ("coverage.json", report),
        ("delta-vs-v1.json", changes),
    ):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n")
    with (output / "review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    inputs = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
    for name in (V1_CASES, ROUND1):
        inputs[name] = hashlib.sha256(read_source_bytes(repo / name)).hexdigest()
    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": doc["extractor_version"],
        "patch_verified": False,
        "input_sha256": inputs,
        "implementation_sha256": {
            name: hashlib.sha256(read_source_bytes(repo / name)).hexdigest()
            for name in IMPLEMENTATION
        },
        "output_sha256": {
            p.name: hashlib.sha256(read_source_bytes(p)).hexdigest()
            for p in sorted(output.iterdir())
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return report, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=True, type=Path, help="New directory, never overwritten"
    )
    args = parser.parse_args()
    report, changes = run(args.output)
    summary = {k: report[k] for k in ("subjects", "facts", "review", "review_groups")}
    summary.update(
        {
            "new_in_v2": len(changes["new_in_v2"]),
            "dropped_from_v1": changes["dropped_from_v1_by_round1_decision"],
        }
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
