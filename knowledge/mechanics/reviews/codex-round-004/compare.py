"""Check round-4 coverage; write JSONL and compare with Claude's screen. Run from repo root."""

import collections
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def read_lines(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main():
    claude = {row["review_id"]: row for row in read_lines(OUT / "claude-screen.jsonl")}
    rows, problems = [], []
    for batch_path in sorted((OUT / "batches").glob("*.json")):
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        result_path = OUT / "results" / batch_path.name
        if not result_path.exists():
            problems.append(f"missing {result_path.name}")
            continue
        reviews = json.loads(result_path.read_text(encoding="utf-8"))["reviews"]
        by_id = {review["review_id"]: review for review in reviews}
        if len(by_id) != len(reviews) or set(by_id) != {group["review_id"] for group in batch}:
            problems.append(f"id mismatch {result_path.name}")
        for group in batch:
            review = by_id.get(group["review_id"])
            if review:
                screen = claude[group["review_id"]]
                rows.append(
                    {
                        "review_id": group["review_id"],
                        "subject": group["subject"],
                        "subject_zh": group["subject_zh"],
                        "mechanism": group["mechanism"],
                        "mechanism_zh": group["mechanism_zh"],
                        "lead": group["lead"],
                        "reviewer": "Codex",
                        "decision": review["decision"],
                        "condition_zh": review["condition_zh"],
                        "reason_zh": review["reason_zh"],
                        "claude_decision": screen["decision"],
                        "claude_reason_zh": screen["reason_zh"],
                    }
                )
    with (OUT / "codex-review.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    pairs = collections.Counter((row["claude_decision"], row["decision"]) for row in rows)
    print("groups", len(rows), "problems", problems)
    print("pairs", {f"{a}->{b}": n for (a, b), n in sorted(pairs.items())})


if __name__ == "__main__":
    main()
