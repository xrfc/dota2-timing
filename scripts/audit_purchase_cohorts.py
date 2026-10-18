"""Offline audit only. Does not fit models or assign additional matches to splits."""

import argparse
from pathlib import Path

from dota_items.data.cohort_handoff import build_audit
from dota_items.storage import json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-root", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-producer-migration",
        action="store_true",
        help="Explicit public-reader/1 compatibility replay; not ignore-hashes",
    )
    args = parser.parse_args()
    options = {"allow_producer_migration": True} if args.allow_producer_migration else {}
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build_audit(args.old_root, args.new_root, args.summary, args.snapshot, **options)
    with args.output.open("xb") as stream:
        stream.write(json_bytes(report))
    print({k: {n: v for n, v in g.items() if n != "groups"} for k, g in report["graphs"].items()})


if __name__ == "__main__":
    main()
