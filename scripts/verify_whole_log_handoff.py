"""Compatibility CLI for read-only whole-log handoff verification."""

import argparse
from pathlib import Path

from dota_items.experiments.whole_log.handoff import *  # noqa: F403
from dota_items.experiments.whole_log.handoff import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "cohort", "baseline", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    report = run(args.parent, args.cohort, args.baseline, args.output, expected=args.expected)
    print(f"Verified handoff: {report['identity_sha256']}; training_executed=false")


if __name__ == "__main__":
    main()
