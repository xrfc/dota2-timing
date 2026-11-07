"""Turn saved page verdicts into a tracked file: export_verdicts.py <JSON dir> <output>.

The JSON dir is an ArtifactData read of the page's `verdicts` collection saved with out_dir.
"""

import glob
import json
import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    source, target = sys.argv[1], Path(sys.argv[2])
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))["rows"]
    known = {t["id"] for h in sample for t in h["traits"]} | {h["rel_id"] for h in sample}
    known |= {a["id"] for h in sample for a in h["abilities"]}
    rows = []
    for path in sorted(glob.glob(os.path.join(source, "*.json"))):
        item = os.path.basename(path).removesuffix(".json")
        if item not in known:
            raise SystemExit(f"Unknown item {item}")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows.append(
            {"id": item, "verdict": data["verdict"], "note": data.get("note", ""), "at": data["at"]}
        )
    rows.sort(key=lambda row: row["at"])
    target.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    print(len(rows))


if __name__ == "__main__":
    main()
