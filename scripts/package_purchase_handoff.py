"""Package existing evidence without training, new splits, or overwriting files."""

import argparse
import hashlib
from pathlib import Path

from dota_items.data.cohort_handoff import checked
from dota_items.data.lineup_preflight import encode_lineup
from dota_items.data.purchase_snapshot import verify_snapshot
from dota_items.handoff.bundle import load_handoff_json, validate_bundle_payloads
from dota_items.storage import file_hash, json_bytes


def synthetic_example():
    vocabulary = [1, 2, 3, 4, 8, 6, 7, 9, 10, 11]
    features = {"ally_hero_ids": [1, 2, 3, 4, 8], "enemy_hero_ids": [6, 7, 9, 10, 11]}
    return {
        "schema_version": "purchase-log-modeling-snapshot/1",
        "synthetic": True,
        "modeling_ready": False,
        "training_executed": False,
        "legacy_training_allowed": False,
        "task": {
            "target": "source_purchase_log_key_presence",
            "window": [0, 1800],
            "candidate_items": ["bfury", "maelstrom", "manta", "black_king_bar", "skadi"],
            "negative_means": "absent_from_valid_source_log_only",
        },
        "preprocessing": {
            "fit_split": "train",
            "vocabulary": vocabulary,
            "columns": [
                c
                for side in ("ally", "enemy")
                for c in [*[f"{side}_hero_{h}" for h in vocabulary], f"{side}_unknown_count"]
            ],
        },
        "samples": [
            {
                "match_id": 1,
                "group_id": "synthetic-1",
                "split": "train",
                "features": features,
                "encoded_features": encode_lineup(features, vocabulary),
                "labels": [1, 0, None, 0, 0],
                "label_mask": [True, True, False, True, True],
                "role_hint": "unknown",
            }
        ],
        "splits": {"train": [1], "validation": [], "test": []},
        "limitations": ["Reader fixture only; not a reconstructed or trainable snapshot."],
    }


def package(summary, snapshot, audit, interface, output, *, allow_producer_migration=False):
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    sources = {
        "snapshot.json": snapshot,
        "summary.json": summary,
        "cohort-audit.json": audit,
        "INTERFACE.md": interface,
    }
    # Capture once so the bytes we publish cannot differ from those we validate.
    payloads = {name: path.read_bytes() for name, path in sources.items()}
    report = load_handoff_json(payloads["cohort-audit.json"])
    if not isinstance(report, dict) or report.get("schema_version") != "purchase-cohort-audit/1":
        raise ValueError("Unsupported audit")
    if any(
        report.get(k) is not False
        for k in ("training_allowed", "new_split_assigned", "old_split_changed")
    ):
        raise ValueError("Audit changed research boundaries")
    evidence = report.get("evidence_sha256")
    if not isinstance(evidence, dict):
        raise ValueError("Missing or invalid audit evidence")
    for name, path in (("summary.json", summary), ("snapshot.json", snapshot)):
        expected = evidence.get(str(path))
        if hashlib.sha256(payloads[name]).hexdigest() != expected:
            raise ValueError(f"Hash mismatch: {path}")
    for path, expected in evidence.items():
        checked(Path(path), expected)
    # Reuse the source reconstruction gate; never fit a model. Bind its inputs
    # before and after the call, rather than trusting a later reread for copying.
    options = {"allow_producer_migration": True} if allow_producer_migration else {}
    verify_snapshot(snapshot, summary, **options)
    for name, path in (("summary.json", summary), ("snapshot.json", snapshot)):
        if path.read_bytes() != payloads[name]:
            raise ValueError(f"Source changed during reconstruction: {path}")
    payloads["synthetic-reader-example.json"] = json_bytes(synthetic_example())
    manifest = {
        "schema_version": "purchase-data-handoff/1",
        "purpose": "Existing old snapshot interface; new cohort diagnostics only",
        **({"producer_migration": "public-reader/1"} if allow_producer_migration else {}),
        "training_authorized_by_package": False,
        "new_snapshot_created": False,
        "raw_sources_included": False,
        "source_paths": {name: str(path.resolve()) for name, path in sources.items()},
        "files": {
            name: hashlib.sha256(contents).hexdigest() for name, contents in payloads.items()
        },
        "producer_sha256": file_hash(Path(__file__)),
        "limitations": [
            "Hashes verify bytes, not authenticity or research authorization.",
            "Full source reconstruction requires original cached matches and receipts.",
            "A failed write may leave an incomplete directory; do not overwrite it.",
        ],
    }
    validate_bundle_payloads(manifest, payloads)
    output.mkdir(parents=True, exist_ok=False)
    for name, contents in payloads.items():
        with (output / name).open("xb") as stream:
            stream.write(contents)
    # Publication marker comes only after the bytes on disk also pass. Failures
    # retain the incomplete directory for inspection; retries need a fresh path.
    validate_bundle_payloads(manifest, {name: (output / name).read_bytes() for name in payloads})
    with (output / "manifest.json").open("xb") as stream:
        stream.write(json_bytes(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("summary", "snapshot", "audit", "interface", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument(
        "--allow-producer-migration",
        action="store_true",
        help="Explicit public-reader/1 compatibility replay; not ignore-hashes",
    )
    args = parser.parse_args()
    options = {"allow_producer_migration": True} if args.allow_producer_migration else {}
    result = package(
        args.summary, args.snapshot, args.audit, args.interface, args.output, **options
    )
    print({"files": len(result["files"]), "output": str(args.output)})


if __name__ == "__main__":
    main()
