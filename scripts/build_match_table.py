"""M1 match table commands. ``inventory`` only counts coverage; it never filters or trains."""

import argparse
import json
from pathlib import Path

from dota_items.data.match_table import DEFAULT_ROOTS, inventory, load_match, match_files
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run_inventory(output, roots=DEFAULT_ROOTS, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output exists")
    files = list(match_files([repo / r for r in roots]))
    result = inventory(load_match(path, manifest) for path, manifest in files)
    result["roots"] = list(roots)
    result["implementation"] = {
        name: file_hash(repo / name)
        for name in ("scripts/build_match_table.py", "src/dota_items/data/match_table.py")
    }
    output.mkdir(parents=True)
    write(output / "inventory.json", result)
    return {k: result[k] for k in ("matches", "unique_matches", "players", "distinct_heroes")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "inventory":
        print(json.dumps(run_inventory(args.output)))


if __name__ == "__main__":
    main()
