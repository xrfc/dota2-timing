"""Packet for the new "haste" mechanism (U120): which candidates raise self/ally move speed.

Candidates (candidates.json) are abilities and items whose official text or value names
mention raising movement speed; many only slow enemies. Texts come from full-audit-001.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BATCH_SIZE = 25


def main():
    candidates = json.loads((OUT / "candidates.json").read_text(encoding="utf-8"))
    objects = {
        o["subject"]: o
        for o in json.loads(
            (ROOT / "knowledge/mechanics/reviews/full-audit-001/objects.json").read_text("utf-8")
        )
    }
    picked = [objects[c["subject"]] for c in candidates if c["subject"] in objects]
    missing = [c["subject"] for c in candidates if c["subject"] not in objects]
    for start in range(0, len(picked), BATCH_SIZE):
        name = f"batch-{start // BATCH_SIZE + 1:03d}.json"
        (OUT / "batches" / name).write_text(
            json.dumps(picked[start : start + BATCH_SIZE], ensure_ascii=False), encoding="utf-8"
        )
    print(len(picked), "objects;", "missing:", missing)


if __name__ == "__main__":
    main()
