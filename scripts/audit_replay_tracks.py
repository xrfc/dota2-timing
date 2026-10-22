"""CLI for provenance-bound replay trajectory and visibility exports."""

import argparse
import json
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.workflow.replay_audit import audit

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--match-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        args.workspace,
        args.match_id,
        parse_source_json(read_source_bytes(args.metadata)),
        args.output,
    )
    print(
        json.dumps({k: result[k] for k in ("match_id", "channel_rows", "semantic_review_required")})
    )
