"""Packet for sorting accepted cooldown reduction rows by whose cooldown they cut (U97)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    rows = load("knowledge/mechanics/extractions/v13/facts-v13.json")["rows"]
    subjects = {
        r["subject"]
        for r in rows
        if r["mechanism"] == "cooldown_reduction" and r["decision"] == "accept"
    }
    objects = [
        o
        for o in load("knowledge/mechanics/reviews/full-audit-001/objects.json")
        if o["subject"] in subjects
    ]
    (OUT / "batches/batch-001.json").write_text(
        json.dumps(objects, ensure_ascii=False), encoding="utf-8"
    )
    print(len(objects), "objects")


if __name__ == "__main__":
    main()
