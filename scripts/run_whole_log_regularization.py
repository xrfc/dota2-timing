"""Default: verify only. --execute is reserved for separately authorized real training."""

import argparse
from pathlib import Path

from dota_items.experiments.whole_log.regularization import run
from dota_items.storage import json_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "cohort", "baseline", "handoff", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json_bytes(run(**vars(args))).decode())


if __name__ == "__main__":
    main()
