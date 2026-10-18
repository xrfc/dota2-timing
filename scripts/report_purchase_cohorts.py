"""Read existing cohort audit JSON and exclusively publish a Markdown quality report."""

import argparse
from pathlib import Path

from dota_items.data.cohort_report import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        digest = write_report(args.input, args.output)
    except (OSError, ValueError):
        parser.exit(1, "Report failed: invalid audit or unavailable/existing output.\n")
    print(f"Report written; input SHA-256: {digest}")


if __name__ == "__main__":
    main()
