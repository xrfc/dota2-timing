"""Turn saved page verdicts into a tracked file: export_verdicts.py <JSON dir> <output>."""

import glob
import json
import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    source, target = sys.argv[1], Path(sys.argv[2])
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))["rows"]
    review_ids = {row["id"]: row["review_id"] for row in sample}
    rows = []
    for path in sorted(glob.glob(os.path.join(source, "*.json"))):
        page_id = os.path.basename(path).removesuffix(".json")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows.append(
            {
                "review_id": review_ids[page_id],
                "verdict": data["verdict"],
                "note": data.get("note", ""),
                "at": data["at"],
            }
        )
    rows.sort(key=lambda row: row["at"])
    target.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    print(len(rows))


if __name__ == "__main__":
    main()
