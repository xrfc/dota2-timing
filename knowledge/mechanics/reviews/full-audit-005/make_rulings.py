"""Turn the slow split (U93) into operations for facts v13. Run from repo root.

Rows that only lower attack speed move to attack_slow; rows that lower both keep slow and gain
attack_slow. Unspecified slows stay where they are.
"""

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from dota_items.data.mechanics_facts_v12 import condition_label  # noqa: E402

TARGET = ROOT / "knowledge/mechanics/reviews/slow-rulings-001.jsonl"


def main():
    facts = json.loads(
        (ROOT / "knowledge/mechanics/extractions/v12/facts-v12.json").read_text(encoding="utf-8")
    )
    accepted = {
        (row["subject"], condition_label(row["condition"]))
        for row in facts["rows"]
        if row["mechanism"] == "slow" and row["decision"] == "accept"
    }
    found = {}
    for path in sorted(glob.glob(str(OUT / "results/batch-*.json"))):
        for obj in json.loads(Path(path).read_text(encoding="utf-8"))["objects"]:
            for item in obj["mechanisms"]:
                found.setdefault((obj["subject"], item["condition"]), {})[item["mechanism"]] = item
    ops = []
    for (subject, condition), items in sorted(found.items()):
        if (subject, condition) not in accepted or "attack_slow" not in items:
            continue
        if "slow" in items:
            ops.append(
                {
                    "op": "set",
                    "subject": subject,
                    "mechanism": "attack_slow",
                    "decision": "accept",
                    "basis": "two_ai",
                    "note_zh": "Codex按新定义读出，Claude看过依据后认同，不是盲审（U93）",
                    "condition": condition,
                    "quote": items["attack_slow"]["quote"],
                }
            )
        else:
            ops.append(
                {
                    "op": "move",
                    "subject": subject,
                    "mechanism": "slow",
                    "new": "attack_slow",
                    "condition": condition,
                }
            )
    TARGET.write_text(
        "".join(json.dumps(op, ensure_ascii=False) + "\n" for op in ops), encoding="utf-8"
    )
    print(len(ops), sum(op["op"] == "move" for op in ops))


if __name__ == "__main__":
    main()
