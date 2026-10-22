"""Read-only recomputation of all four regularization comparison candidates."""

import argparse
from pathlib import Path

from dota_items.experiments.whole_log.regularization import report_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "cohort", "baseline", "handoff", "experiment", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report_run(**vars(args))
    print(f"Verified comparison: {args.output / 'complete.json'}")


if __name__ == "__main__":
    main()
