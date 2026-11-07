"""Packet for sorting accepted unit-target rows: does the spell act on the unit? (U101)"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BATCH_SIZE = 25


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    rows = load("knowledge/mechanics/extractions/v15/facts-v15.json")["rows"]
    subjects = {
        r["subject"]
        for r in rows
        if r["mechanism"] == "unit_target_spell" and r["decision"] == "accept"
    }
    objects = [
        o
        for o in load("knowledge/mechanics/reviews/full-audit-001/objects.json")
        if o["subject"] in subjects
    ]
    for start in range(0, len(objects), BATCH_SIZE):
        name = f"batch-{start // BATCH_SIZE + 1:03d}.json"
        (OUT / "batches" / name).write_text(
            json.dumps(objects[start : start + BATCH_SIZE], ensure_ascii=False), encoding="utf-8"
        )
    print(len(objects), "objects")


if __name__ == "__main__":
    main()
