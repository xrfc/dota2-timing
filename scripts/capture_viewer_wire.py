"""Capture raw viewer vector writes from one registered engineering replay."""

import argparse
import json
from pathlib import Path

from dota_items.experiments.awareness.viewer_capture import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.spec, args.output)))


if __name__ == "__main__":
    main()
