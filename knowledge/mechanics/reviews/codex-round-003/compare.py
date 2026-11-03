"""Check round-3 coverage; write JSONL and label comparison. Run from repo root."""

import collections
import glob
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
R = OUT.parent


def read_lines(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main():
    claude = {}
    for path in (
        R / "claude-round-001/claude-review.jsonl",
        R / "claude-round-002/new-in-v2.jsonl",
    ):
        claude.update({r["review_id"]: r for r in read_lines(path)})
    rows, problems = [], []
    for batch_path in sorted(glob.glob(str(OUT / "batches/*.json"))):
        batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
        result_path = OUT / "results" / Path(batch_path).name
        if not result_path.exists():
            problems.append(f"missing {result_path.name}")
            continue
        reviews = json.loads(result_path.read_text(encoding="utf-8"))["reviews"]
        by_id = {r["review_id"]: r for r in reviews}
        if len(by_id) != len(reviews) or set(by_id) != {g["review_id"] for g in batch}:
            problems.append(f"id mismatch {result_path.name}")
        for group in batch:
            review = by_id.get(group["review_id"])
            if review:
                rows.append(
                    {
                        "review_id": group["review_id"],
                        "subject": group["subject"],
                        "subject_zh": group["subject_zh"],
                        "mechanism": group["mechanism"],
                        "mechanism_zh": group["mechanism_zh"],
                        "reviewer": "Codex",
                        "decision": review["decision"],
                        "condition_zh": review["condition_zh"],
                        "reason_zh": review["reason_zh"],
                        "claude_decision": claude[group["review_id"]]["decision"],
                    }
                )
    with (OUT / "codex-review.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    pairs = collections.Counter((r["claude_decision"], r["decision"]) for r in rows)
    print("groups", len(rows), "problems", problems)
    print("pairs", {f"{a}->{b}": n for (a, b), n in sorted(pairs.items())})
    return rows


if __name__ == "__main__":
    main()
