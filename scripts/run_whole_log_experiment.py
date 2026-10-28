"""One fixed whole-log frequency versus C=1 logistic development comparison."""

import argparse
from pathlib import Path

from dota_items.experiments.whole_log.baseline import run_experiment
from dota_items.storage import json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "cohort", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    result = run_experiment(args.parent, args.cohort, args.output, verify_only=args.verify_only)
    print(json_bytes(result).decode())


if __name__ == "__main__":
    main()
