"""Blind row-level recheck of old AI rows at high effort (U85). Run from repo root.

Each two_ai row from rounds 1-8 is re-judged from the object text. The packet omits the
existing decision, reviewer and quote. Rows read from game fields are checked by field_check.py.
"""

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
MECH = ROOT / "knowledge/mechanics"
BATCH_SIZE = 25
FIELD_ONLY = {"unit_target_spell", "channeled"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def condition_label(condition):
    if condition.get("context") == "item":
        return "item"
    if condition.get("requires_scepter"):
        return "scepter"
    if condition.get("requires_shard"):
        return "shard"
    return "base"


def main():
    rows = load(MECH / "extractions/v11/facts-v11.json")["rows"]
    objects = load(ROOT / "knowledge/mechanics/reviews/full-audit-001/objects.json")
    vocabulary = load(MECH / "vocabulary-v10.json")["mechanisms"]
    definitions = {
        m["id"]: {"id": m["id"], "zh": m["zh"], "definition": m.get("definition", "")}
        for m in vocabulary
    }
    judge = defaultdict(list)
    for row in rows:
        if row["basis"] != "two_ai" or row["origin"] not in {"v3_review", "audit_round4"}:
            continue
        if row["mechanism"] in FIELD_ONLY:
            continue
        judge[row["subject"]].append(
            {"mechanism": row["mechanism"], "condition": condition_label(row["condition"])}
        )
    picked = [
        {**o, "judge": sorted(judge[o["subject"]], key=str)}
        for o in objects
        if o["subject"] in judge
    ]
    (OUT / "batches").mkdir(exist_ok=True)
    for index in range(0, len(picked), BATCH_SIZE):
        chunk = picked[index : index + BATCH_SIZE]
        used = sorted({j["mechanism"] for o in chunk for j in o["judge"]})
        payload = {"vocabulary": [definitions[m] for m in used], "objects": chunk}
        name = f"batch-{index // BATCH_SIZE + 1:03d}.json"
        (OUT / "batches" / name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    print(len(picked), "objects", sum(len(o["judge"]) for o in picked), "rows")


if __name__ == "__main__":
    main()
