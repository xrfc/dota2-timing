"""Give every existing correction the feedback ids it resolves (U101). Run from repo root.

Old corrections name only a fact review_id. A correction resolves the wrong feedback on that
row; when a row has no wrong feedback, the correction stands alone and resolves nothing. Rows
whose wrongs cannot be matched are reported, not guessed.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from dota_items.data.mechanics_feedback import feedback_id  # noqa: E402

REVIEWS = ROOT / "knowledge/mechanics/reviews"
CORRECTION_FILES = ("v13-inputs-001.json", "v15-inputs-001.json")
FEEDBACK_FILES = (
    "u5-verdicts-2026-11-03.jsonl",
    "u5-spot-check-002/verdicts-2026-11-05.jsonl",
    "u5-spot-check-002/verdicts-2026-11-06.jsonl",
    "u5-spot-check-002/verdicts-2026-11-06b.jsonl",
)


def main():
    wrongs = {}
    for name in FEEDBACK_FILES:
        for line in (REVIEWS / name).read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry["verdict"] == "wrong":
                wrongs.setdefault(entry["review_id"], set()).add(feedback_id(entry))
    resolutions = []
    for name in CORRECTION_FILES:
        for correction in json.loads((REVIEWS / name).read_text(encoding="utf-8"))["corrections"]:
            resolutions.append(
                {
                    **correction,
                    "from": name,
                    "resolves": sorted(wrongs.get(correction["review_id"], set())),
                }
            )
    target = REVIEWS / "feedback-resolutions-001.json"
    target.write_text(
        json.dumps(
            {
                "schema": "mechanics-feedback-resolutions/1",
                "decision": "U101",
                "corrections": resolutions,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(len(resolutions), sum(1 for r in resolutions if not r["resolves"]), "standalone")


if __name__ == "__main__":
    main()
