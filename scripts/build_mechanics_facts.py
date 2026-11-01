"""Build MK-T3 evidence and a review queue from existing snapshots, without network access."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from dota_items.data.mechanics_facts import INPUTS, VOCAB, build_facts, coverage, digest, load_facts
from dota_items.data.source_io import parse_source_json, read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = (
    "src/dota_items/data/mechanics.py",
    "src/dota_items/data/mechanics_facts.py",
    "src/dota_items/data/mechanics_rules.py",
    "scripts/build_mechanics_facts.py",
)


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    raw = {name: read_source_bytes(repo / name) for name in INPUTS}
    sources = {
        name: parse_source_json(value)
        if name.endswith(".json")
        else {"text": value.decode("utf-8")}
        for name, value in raw.items()
    }
    doc = build_facts(sources)
    load_facts(doc, sources)
    terms = {m["id"]: m for m in sources[VOCAB]["mechanisms"]}
    report = coverage(doc, terms)
    # Group repeated language/quote evidence into one semantic judgment.
    groups = {}
    for fact in doc["facts"]:
        if fact["review"] != "needs_review":
            continue
        key = digest([fact["subject_type"], fact["subject"], fact["mechanism"], fact["condition"]])
        groups.setdefault(key, []).append(fact)
    ordered = sorted(groups)
    selected = set(ordered[::3])  # deterministic ~1/3; not an independent quality estimate
    review = []
    names = {s["subject"]: s for s in doc["subjects"]}
    for key in ordered:
        rows = groups[key]
        first = rows[0]
        subject = names[first["subject"]]
        review.append(
            {
                "review_id": key[:20],
                "sample": "yes" if key in selected else "no",
                "subject": first["subject"],
                "hero_zh": subject.get("hero_name_zh", ""),
                "name_zh": subject["name_zh"],
                "mechanism": first["mechanism"],
                "mechanism_zh": terms[first["mechanism"]]["zh"],
                "condition": json.dumps(first["condition"], ensure_ascii=False, sort_keys=True),
                "fact_ids": " | ".join(f["fact_id"] for f in rows),
                "quotes": " | ".join(dict.fromkeys(f["quote"] for f in rows)),
                "sources": " | ".join(
                    f["pointer"]["file"] + "#" + f["pointer"]["path"] for f in rows
                ),
                "decision": "",
                "reason": "",
            }
        )
    report["review_groups"] = len(review)
    report["sample_groups"] = len(selected)
    report["sample_method"] = (
        "SHA256-sorted subject/mechanism/condition groups, every third; U5 review aid"
    )
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("facts-v1.json", doc), ("coverage.json", report)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n")
    fields = [
        "review_id",
        "sample",
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
    ]
    for filename, rows in (
        ("review.csv", review),
        ("review-sample.csv", [r for r in review if r["sample"] == "yes"]),
    ):
        with (output / filename).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "patch_verified": False,
        "input_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()},
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
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=True, type=Path, help="New output directory (never overwritten)"
    )
    args = parser.parse_args()
    result = run(args.output)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("subjects", "facts", "review", "review_groups", "sample_groups")
            },
            ensure_ascii=False,
        )
    )
