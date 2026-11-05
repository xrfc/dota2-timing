"""Compare the recheck with existing rows. Run from repo root. Writes comparison.json."""

import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
from build_packet import FIELD_ONLY, condition_label  # noqa: E402


def main():
    rows = json.loads(
        (ROOT / "knowledge/mechanics/extractions/v11/facts-v11.json").read_text(encoding="utf-8")
    )["rows"]
    want = {}
    for row in rows:
        if (
            row["basis"] == "two_ai"
            and row["origin"] in {"v3_review", "audit_round4"}
            and row["mechanism"] not in FIELD_ONLY
        ):
            want[(row["subject"], row["mechanism"], condition_label(row["condition"]))] = row
    got = {}
    for path in sorted(glob.glob(str(OUT / "results/batch-*.json"))):
        for obj in json.loads(Path(path).read_text(encoding="utf-8"))["objects"]:
            for j in obj["judgments"]:
                got[(obj["subject"], j["mechanism"], j["condition"])] = j
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    tally = Counter()
    diffs = []
    for key, row in want.items():
        j = got.get(key)
        if j is None:
            continue
        tally[(row["decision"], j["decision"])] += 1
        cond_bad = j["decision"] == "accept" and not j["condition_correct"]
        if j["decision"] != row["decision"] or cond_bad:
            diffs.append(
                {
                    "subject": key[0],
                    "subject_zh": row["subject_zh"],
                    "mechanism": key[1],
                    "condition": key[2],
                    "origin": row["origin"],
                    "old": row["decision"],
                    "new": j["decision"],
                    "condition_correct": j["condition_correct"],
                    "correct_condition": j["correct_condition"],
                    "quote": j["quote"],
                    "reason_zh": j["reason_zh"],
                    "old_quotes": row.get("quotes", []),
                }
            )
    summary = {
        "wanted": len(want),
        "judged": len(want) - len(missing),
        "missing": [list(k) for k in missing],
        "extra": [list(k) for k in extra],
        "tally": {f"{a}->{b}": n for (a, b), n in sorted(tally.items())},
        "differences": len(diffs),
        "condition_only": sum(1 for d in diffs if d["new"] == d["old"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    (OUT / "comparison.json").write_text(
        json.dumps({"summary": summary, "differences": diffs}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
