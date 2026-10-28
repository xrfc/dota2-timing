"""Compatibility CLI for read-only whole-log diagnostics."""

import argparse
import shlex
import sys
from pathlib import Path

from dota_items.experiments.whole_log.diagnostics import *  # noqa: F403
from dota_items.experiments.whole_log.diagnostics import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "snapshot", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(
        args.experiment, args.snapshot, args.output, command=shlex.join([sys.executable, *sys.argv])
    )
    print(f"Verified frozen diagnostics: {args.output / 'complete.json'}")


if __name__ == "__main__":
    main()
