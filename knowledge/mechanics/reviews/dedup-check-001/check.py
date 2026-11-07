"""Which v4-era candidates did the (subject, mechanism) merge skip, and does v15 have them now?

Run from repo root. Writes report.json. Read-only: no facts are changed. A skipped candidate that
v15 still lacks is a candidate for review, not a confirmed missing fact.
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_mechanics_facts_v4 as v4script  # noqa: E402
import build_mechanics_facts_v6 as v6script  # noqa: E402
import build_mechanics_facts_v8 as v8script  # noqa: E402

from dota_items.data.mechanics_facts_v12 import condition_label  # noqa: E402

FACTS = "knowledge/mechanics/extractions/v15/facts-v15.json"


def identity(subject, mechanism, condition):
    """Fact identity with every condition field, not only the coarse context."""
    return subject, mechanism, json.dumps(condition, sort_keys=True)


def main():
    sources = v6script.load_sources(ROOT)
    sources["audit"].extend(v4script.read_jsonl(ROOT, v8script.ROUND8))
    v4 = json.loads((ROOT / "knowledge/mechanics/extractions/v4/facts-v4.json").read_text("utf-8"))
    current = json.loads((ROOT / FACTS).read_text(encoding="utf-8"))
    v4_full = {identity(r["subject"], r["mechanism"], r["condition"]) for r in v4["rows"]}
    v4_pairs = {(r["subject"], r["mechanism"]) for r in v4["rows"]}
    every = [*current["rows"], *current["retired_rows"], *current["deferred_rows"]]
    every += current["retired_term_rows"]
    now_full = {identity(r["subject"], r["mechanism"], r["condition"]) for r in every}
    now_label = {(r["subject"], r["mechanism"], condition_label(r["condition"])) for r in every}
    numeric = {
        (r["subject"], r["kind"], condition_label(r["condition"]))
        for r in current["numeric_upgrades"]
    }
    report, seen = [], set()
    for kind, candidates in (("audit", sources["audit"]), ("user_added", sources["user_added"])):
        for cand in candidates:
            key = identity(cand["subject"], cand["mechanism"], cand["condition"])
            if key in seen:
                continue
            seen.add(key)
            if key in v4_full or (cand["subject"], cand["mechanism"]) not in v4_pairs:
                continue
            label = (cand["subject"], cand["mechanism"], condition_label(cand["condition"]))
            if key in now_full:
                status = "present_now"
            elif label in now_label:
                status = "same_label_now"
            elif label in numeric:
                status = "numeric_upgrade_now"
            else:
                status = "missing_now"
            report.append(
                {
                    "source": kind,
                    "review_id": cand.get("review_id"),
                    "subject": cand["subject"],
                    "mechanism": cand["mechanism"],
                    "condition": cand["condition"],
                    "claude": cand.get("claude_decision"),
                    "codex": cand.get("decision"),
                    "status": status,
                }
            )
    summary = Counter(row["status"] for row in report)
    (OUT / "report.json").write_text(
        json.dumps(
            {"facts": FACTS, "summary": dict(summary), "rows": report}, ensure_ascii=False, indent=1
        )
        + "\n",
        encoding="utf-8",
    )
    print(dict(summary), len(report))


if __name__ == "__main__":
    main()
