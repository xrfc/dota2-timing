"""Build the spot check page from the sample and the current facts. Run from repo root.

The sample only fixes which rows are looked at. What each row claims and how each mechanism is
defined come from the current facts and vocabulary, so the page cannot lag behind a decision.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
# Current versions come from the single entry point (MK-T6a), not hard-coded paths.
_CURRENT = json.loads((ROOT / "knowledge/mechanics/current.json").read_text(encoding="utf-8"))
FACTS = _CURRENT["entries"]["facts"]["path"]
VOCABULARY = _CURRENT["entries"]["vocabulary"]["path"]
KEYS = ("id", "n", "m", "mz", "c", "d", "why", "t", "b")


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def current_rows(sample, facts, terms):
    """Rows as they stand now; ones the user has already ruled on need no second look."""
    by_id = {row["review_id"]: row for row in facts["rows"]}
    rows = []
    for row in sample:
        fact = by_id.get(row["review_id"])
        if fact is None or fact["basis"].startswith("user:"):
            continue
        mechanism = fact["mechanism"]
        rows.append(
            {
                **row,
                "m": mechanism,
                "mz": terms[mechanism]["zh"],
                "d": "有" if fact["decision"] == "accept" else "没有",
            }
        )
    return rows


def main():
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))["rows"]
    terms = {term["id"]: term for term in load(VOCABULARY)["mechanisms"]}
    rows = current_rows(sample, load(FACTS), terms)
    defs = {row["m"]: terms[row["m"]]["definition"] for row in rows}
    payload = json.dumps(
        {"defs": defs, "rows": [{key: row[key] for key in KEYS} for row in rows]},
        ensure_ascii=False,
    )
    template = (OUT / "page.template.html").read_text(encoding="utf-8")
    html = template.replace("/*DATA*/", payload.replace("</", "<\\/"))
    (OUT / "page.html").write_text(html, encoding="utf-8")
    print(len(rows), "rows", len(defs), "definitions")


if __name__ == "__main__":
    main()
