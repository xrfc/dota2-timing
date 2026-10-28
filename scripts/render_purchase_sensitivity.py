"""Render existing comparison JSON without training or reading match data."""

import argparse
import hashlib
import json
from pathlib import Path

from dota_items.modeling.sensitivity_report import render_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    report = render_report(json.loads(raw), source_sha256=hashlib.sha256(raw).hexdigest())
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(report)
    print(args.output)


if __name__ == "__main__":
    main()
