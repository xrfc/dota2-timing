"""Build MK-T3 evidence v3: v2 without upgrade text whose Valve flag is false.

Writes to a new directory only; v1/v2 packages are untouched.

    PYTHONPATH=src python scripts/build_mechanics_facts_v3.py \
        --output knowledge/mechanics/extractions/v3
"""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_mechanics_facts_v2 as v2script  # noqa: E402

from dota_items.data.mechanics_facts import coverage  # noqa: E402
from dota_items.data.mechanics_facts_v3 import (  # noqa: E402
    INPUTS,
    VOCAB,
    build_facts,
    group_key,
    load_facts,
)
from dota_items.data.source_io import parse_source_json, read_source_bytes  # noqa: E402

ROOT = v2script.ROOT
IMPLEMENTATION = v2script.IMPLEMENTATION + (
    "src/dota_items/data/mechanics_facts_v3.py",
    "scripts/build_mechanics_facts_v3.py",
)


def load_sources(repo):
    raw = {name: read_source_bytes(repo / name) for name in INPUTS}
    sources = {
        name: parse_source_json(value) if name.endswith(".json") else {"text": value.decode()}
        for name, value in raw.items()
    }
    return raw, sources


def excluded_groups(doc, round1):
    groups = {}
    for fact in doc["excluded_facts"]:
        if fact["review"] == "needs_review":
            groups.setdefault(group_key(fact), []).append(fact)
    names = {s["subject"]: s for s in doc["subjects"]}
    return [
        {
            "review_id": key,
            "subject": facts[0]["subject"],
            "hero_zh": names[facts[0]["subject"]].get("hero_name_zh", ""),
            "name_zh": names[facts[0]["subject"]]["name_zh"],
            "mechanism": facts[0]["mechanism"],
            "context": facts[0]["condition"]["context"],
            "round1_decision": round1.get(key, ""),
            "reason": "upgrade_flag_false",
            "quotes": list(dict.fromkeys(f["quote"] for f in facts)),
        }
        for key, facts in sorted(groups.items())
    ]


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    raw, sources = load_sources(repo)
    doc = build_facts(sources)
    load_facts(doc, sources)
    terms = {m["id"]: m for m in sources[VOCAB]["mechanisms"]}
    report = coverage(doc, terms)
    v1_cases = v2script.read_jsonl(repo / v2script.V1_CASES)
    round1 = {r["review_id"]: r["decision"] for r in v2script.read_jsonl(repo / v2script.ROUND1)}
    rows = v2script.review_rows(doc, terms, {c["review_id"] for c in v1_cases}, round1)
    report["review_groups"] = len(rows)
    removed = excluded_groups(doc, round1)
    changes = {
        "schema": "mechanics-extraction-delta/2",
        "patch_verified": False,
        "base": "mechanics-extractor/2",
        "excluded_facts": len(doc["excluded_facts"]),
        "removed_review_groups": len(removed),
        "removed_by_round1_decision": dict(Counter(r["round1_decision"] or "new" for r in removed)),
        "removed": removed,
        "note": (
            "Removed groups rest only on scepter/shard text whose Valve has-upgrade flag is "
            "false in the 2026-10-09 snapshot. Round-1 decisions judged the wording, not "
            "whether the upgrade is current."
        ),
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (
        ("facts-v3.json", doc),
        ("coverage.json", report),
        ("delta-vs-v2.json", changes),
    ):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n")
    with (output / "review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=v2script.FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    inputs = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
    for name in (v2script.V1_CASES, v2script.ROUND1):
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
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    report, changes = run(args.output)
    summary = {k: report[k] for k in ("subjects", "facts", "review", "review_groups")}
    summary["removed"] = changes["removed_by_round1_decision"]
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
