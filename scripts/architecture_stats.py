"""Print or rewrite the track table in docs/architecture.md from the registry (U124 step 3).

PYTHONPATH=src python scripts/architecture_stats.py           # print
PYTHONPATH=src python scripts/architecture_stats.py --write   # update the doc
"""

import argparse
import re
from pathlib import Path

from dota_items.architecture import track_table

DOC = Path(__file__).resolve().parents[1] / "docs/architecture.md"
BLOCK = re.compile(r"(<!-- track-table:[^\n]*-->\n)(.*?)(\n<!-- /track-table -->)", re.S)


def updated(text):
    if not BLOCK.search(text):
        raise SystemExit("track-table markers missing in docs/architecture.md")
    return BLOCK.sub(lambda m: m.group(1) + track_table() + m.group(3), text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        DOC.write_text(updated(DOC.read_text(encoding="utf-8")), encoding="utf-8")
    print(track_table())


if __name__ == "__main__":
    main()
