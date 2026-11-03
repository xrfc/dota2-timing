"""Build MK-T3 reviewed facts v4 from v3 evidence and recorded decisions (U54).

Writes to a new directory only; earlier packages are untouched.

    PYTHONPATH=src python scripts/build_mechanics_facts_v4.py \
        --output knowledge/mechanics/extractions/v4
"""

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

from dota_items.data.mechanics_facts_v4 import build_reviewed

ROOT = Path(__file__).resolve().parents[1]
MECH = "knowledge/mechanics"
REVIEWS = f"{MECH}/reviews"
INPUTS = (
    f"{MECH}/extractions/v3/review.csv",
    f"{MECH}/extractions/v3/facts-v3.json",
    f"{MECH}/vocabulary-v4.json",
    f"{MECH}/retired-items-v1.json",
    f"{REVIEWS}/claude-round-001/claude-review.jsonl",
    f"{REVIEWS}/claude-round-002/new-in-v2.jsonl",
    f"{REVIEWS}/codex-round-002/codex-review.jsonl",
    f"{REVIEWS}/codex-round-003/codex-review.jsonl",
    f"{REVIEWS}/codex-round-004/codex-review.jsonl",
    f"{REVIEWS}/user-rulings-001.jsonl",
    f"{REVIEWS}/u5-verdicts-2026-11-03.jsonl",
    f"{REVIEWS}/break-check-001/break-conditions.jsonl",
    f"{REVIEWS}/break-check-001/confirmed-missing-groups.jsonl",
    "knowledge/game-files/snapshots/2026-11-02/manifest.json",
)
IMPLEMENTATION = (
    "src/dota_items/data/mechanics_facts_v4.py",
    "scripts/build_mechanics_facts_v4.py",
    "scripts/check_break_against_game_files.py",
)
BASE = {"context": "base", "requires_scepter": False, "requires_shard": False}
ITEM = {"context": "item", "requires_scepter": False, "requires_shard": False}


def read_jsonl(repo, name):
    text = (repo / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def load_break_tags(repo):
    path = repo / "scripts/check_break_against_game_files.py"
    spec = importlib.util.spec_from_file_location("check_break", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_tags(repo / "knowledge/game-files/snapshots/2026-11-02")


def ability_condition(ability):
    return {
        "context": "base",
        "requires_scepter": bool(ability.get("granted_by_scepter")),
        "requires_shard": bool(ability.get("granted_by_shard")),
    }


def load_sources(repo):
    registry = json.loads(
        (repo / "knowledge/hero-capabilities/hero-registry.json").read_text(encoding="utf-8")
    )
    abilities = {a["name"]: a for h in registry["heroes"] for a in h["abilities"]}

    def condition_of(subject):
        return ability_condition(abilities[subject]) if subject in abilities else ITEM

    with (repo / INPUTS[0]).open(encoding="utf-8-sig") as stream:
        review_rows = [
            {**row, "condition": json.loads(row["condition"]), "quotes": row["quotes"].split(" | ")}
            for row in csv.DictReader(stream)
        ]
    claude = {}
    for name in INPUTS[4:6]:
        claude.update({row["review_id"]: row for row in read_jsonl(repo, name)})
    codex = {}
    for name in INPUTS[6:8]:
        codex.update({row["review_id"]: row["decision"] for row in read_jsonl(repo, name)})
    rulings = {row["review_id"]: row for row in read_jsonl(repo, INPUTS[9])}
    conditions_rows = read_jsonl(repo, INPUTS[11])
    conditions = {r["review_id"]: r["condition_en"] for r in conditions_rows if r["review_id"]}
    subject_conditions = {
        r["subject"]: r["condition_en"] for r in conditions_rows if not r["review_id"]
    }
    audit = [
        {**row, "condition": condition_of(row["subject"])} for row in read_jsonl(repo, INPUTS[8])
    ]
    user_added = []
    for row in read_jsonl(repo, INPUTS[12]):
        digest = hashlib.sha256(f"{row['subject']}|break_sensitive|u47".encode()).hexdigest()[:20]
        user_added.append(
            {
                **row,
                "review_id": digest,
                "condition": condition_of(row["subject"]),
                "condition_en": subject_conditions.get(row["subject"], []),
            }
        )
    audit_ids = {row["review_id"] for row in audit}
    review_ids = {row["review_id"] for row in review_rows}
    for rid, row in rulings.items():
        if rid not in audit_ids and rid not in review_ids:
            user_added.append({**row, "condition": condition_of(row["subject"])})
    facts = json.loads((repo / INPUTS[1]).read_text(encoding="utf-8"))["facts"]
    return {
        "review_rows": review_rows,
        "claude": claude,
        "codex": codex,
        "rulings": rulings,
        "verdicts": {row["review_id"]: row["verdict"] for row in read_jsonl(repo, INPUTS[10])},
        "break_conditions": conditions,
        "break_tags": load_break_tags(repo),
        "audit": audit,
        "user_added": user_added,
        "item_status": json.loads((repo / INPUTS[3]).read_text(encoding="utf-8"))["status"],
        "field_observations": [
            {
                "subject": fact["subject"],
                "mechanism": fact["mechanism"],
                "evidence_kind": fact["evidence_kind"],
                "value": fact["value"],
                "fact_id": fact["fact_id"],
            }
            for fact in facts
            if fact["review"] == "auto"
        ],
    }


def delta_of(doc):
    changed = [
        {
            key: row[key]
            for key in ("review_id", "subject_zh", "mechanism", "claude", "decision", "basis")
        }
        for row in doc["rows"]
        if row["origin"] == "v3_review" and row["claude"] != row["decision"]
    ]
    added = [
        {key: row[key] for key in ("subject_zh", "mechanism", "origin", "decision", "basis")}
        for row in doc["rows"]
        if row["origin"] != "v3_review"
    ]
    return {
        "schema": "mechanics-reviewed-delta/1",
        "changed_from_claude": changed,
        "added": added,
        "retired_rows": [
            {key: row[key] for key in ("subject_zh", "mechanism", "origin", "item_status")}
            for row in doc["retired_rows"]
        ],
        "deferred_rows": [
            {key: row[key] for key in ("subject_zh", "mechanism", "origin", "decision", "basis")}
            for row in doc["deferred_rows"]
        ],
    }


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    doc = build_reviewed(load_sources(repo))
    output.mkdir(parents=True)
    for name, value in (("facts-v4.json", doc), ("delta-vs-v3.json", delta_of(doc))):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": doc["extractor_version"],
        "patch_verified": False,
        "input_sha256": {name: digest(repo / name) for name in INPUTS},
        "implementation_sha256": {name: digest(repo / name) for name in IMPLEMENTATION},
        "output_sha256": {path.name: digest(path) for path in sorted(output.iterdir())},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    print(json.dumps(run(args.output)["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
