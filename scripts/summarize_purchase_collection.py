"""Re-audit retained collection files globally, including cross-batch player overlap."""

import argparse
from pathlib import Path

from dota_items.data.feasibility import AuditConfig, audit_paths
from dota_items.data.lineup_preflight import (
    PreflightConfig,
    split_matches,
    summarize_purchase_support,
)
from dota_items.data.patch_time import load_patch_window
from dota_items.data.player_overlap import audit_player_overlap
from dota_items.storage import file_hash, json_bytes, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    progress = read_json(args.root / "progress.json")
    rules = read_json(args.root / "collection.json")
    receipt = Path("knowledge/evidence/feasibility-2026-10-13/receipt.json")
    if file_hash(receipt) != rules["patch_receipt_sha256"]:
        raise ValueError("Patch evidence changed")
    candidates = progress["candidates"]
    ids = [row["match_id"] for row in candidates]
    if len(ids) != len(set(ids)) or len(ids) != progress["retained_candidates"]:
        raise ValueError("Duplicate candidate or inconsistent progress count")
    paths = {}
    for row in candidates:
        path = Path(row["path"])
        path.resolve().relative_to(args.root.resolve())
        if file_hash(path) != row["sha256"]:
            raise ValueError("Retained source changed")
        paths[row["match_id"]] = path
    config = AuditConfig.model_validate(rules["audit_config"])
    audit = audit_paths(
        list(paths.values()),
        config,
        patch_window=load_patch_window(receipt, config.requested_patch),
        expected_ids={path: mid for mid, path in paths.items()},
    )
    for row in audit["results"]:
        if (
            row["status"] != "inspectable"
            or row.get("patch_time_check") != "time_consistent"
            or not row["window_complete_in_duration"]
            or row["purchase_log_status"] != "present"
            or row["invalid_purchase_rows"]
            or row["synthetic_marker_present"]
        ):
            raise ValueError("Retained candidate no longer passes preflight conditions")
    splits = split_matches(ids, PreflightConfig())
    report = {
        "schema_version": "purchase-collection-summary/1",
        "training_allowed": False,
        "attempted": progress["attempted"],
        "retained_candidates": len(ids),
        "target_candidates": progress["target"],
        "target_reached": len(ids) >= progress["target"],
        "training_admitted_matches": 0,
        "retained_raw_bytes": sum(p.stat().st_size for p in paths.values()),
        "collection_config_sha256": file_hash(args.root / "collection.json"),
        "implementation_sha256": {
            **audit["implementation_sha256"],
            "summary_script": file_hash(Path(__file__)),
            "data/lineup_preflight.py": file_hash(Path("src/dota_items/data/lineup_preflight.py")),
            "data/player_overlap.py": file_hash(Path("src/dota_items/data/player_overlap.py")),
        },
        "splits": splits,
        "player_overlap": audit_player_overlap(audit["results"], paths, splits),
        "purchase_support": summarize_purchase_support(
            audit["results"], audit["results"], splits, config.candidate_items
        ),
        "sources": candidates,
        "audit": audit,
        "limitations": rules["limitations"]
        + [
            "Global splits are diagnostic only, not an independent final evaluation.",
            "Deleted rejected raw files cannot be reproduced from hashes alone.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(json_bytes(report))
    print(
        {
            k: report[k]
            for k in (
                "attempted",
                "retained_candidates",
                "target_reached",
                "training_admitted_matches",
                "retained_raw_bytes",
            )
        }
    )


if __name__ == "__main__":
    main()
