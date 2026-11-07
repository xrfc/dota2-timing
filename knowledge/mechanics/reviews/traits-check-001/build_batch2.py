"""Pick a small second batch of trait items the user has not marked yet (2026-11-07).

Per trait: up to two heroes from the sample with a non-zero count, preferring items whose
abilities include unconfirmed facts; list-based traits (mana dependence, magic burst) get one.
Order is a fixed hash, so the batch is reproducible. Writes batch2.json.
"""

import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
LIST_BASED = {"mana_dependent", "magic_burst"}


def _order(item_id):
    return hashlib.sha256(f"traits-check-001-b2:{item_id}".encode()).hexdigest()


def main():
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))
    marked = {
        json.loads(line)["id"]
        for line in (OUT / "verdicts-2026-11-07.jsonl").read_text(encoding="utf-8").splitlines()
    }
    by_trait = {}
    for hero in sample["rows"]:
        for trait in hero["traits"]:
            if trait["up"] > 0 and trait["id"] not in marked:
                unconfirmed = any(not a["confirmed"] for a in trait["abilities"])
                by_trait.setdefault(trait["key"], []).append(
                    (not unconfirmed, _order(trait["id"]), trait["id"])
                )
    picked = []
    for key, items in sorted(by_trait.items()):
        take = 1 if key in LIST_BASED else 2
        picked += [item_id for _, _, item_id in sorted(items)[:take]]
    (OUT / "batch2.json").write_text(
        json.dumps({"schema": "traits-check-batch/1", "ids": picked}, ensure_ascii=False, indent=1)
        + "\n",
        encoding="utf-8",
    )
    print(len(picked), picked)


if __name__ == "__main__":
    main()
