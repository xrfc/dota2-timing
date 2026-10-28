"""Rebuild frozen cohort evidence, then propose aggregate whole-group partitions; never train."""

import argparse
import copy
from pathlib import Path

from dota_items.data.cohort_handoff import build_audit
from dota_items.data.cohort_split_feasibility import analyze, support
from dota_items.data.producer_migration import ROOT, compare_replay
from dota_items.data.purchase_observation import observe_purchases
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash, json_bytes


def load(path):
    return parse_source_json(read_source_bytes(path))


def compare_audit(saved, rebuilt, *, allow=False):
    if json_bytes(saved) == json_bytes(rebuilt):
        return {"mode": "exact", "changes": []}
    if not allow:
        raise ValueError("Audit no longer exactly reproduces; explicit migration required")
    normalized = []
    for value in (saved, rebuilt):
        value = copy.deepcopy(value)
        evidence = value["evidence_sha256"]
        implementation = {}
        for name in list(evidence):
            path = Path(name).resolve()
            if path.is_relative_to(ROOT):
                implementation[path.relative_to(ROOT).as_posix()] = evidence.pop(name)
        value["implementation_sha256"] = implementation
        normalized.append(value)
    receipt = compare_replay(*normalized)
    return {"mode": "registered-producer-compatible", **receipt}


def build_report(old_root, new_root, summary, snapshot, audit, *, allow_audit_migration=False):
    input_hashes = {str(p): file_hash(p) for p in (summary, snapshot, audit)}
    saved = load(audit)
    rebuilt = build_audit(old_root, new_root, summary, snapshot, allow_producer_migration=True)
    reconstruction = compare_audit(saved, rebuilt, allow=allow_audit_migration)
    graph = rebuilt["graphs"]["including_new_excluded_inspectable"]
    if not graph["identity_coverage_complete"]:
        raise ValueError("Incomplete identity evidence; requires a separate protocol decision")
    old_snapshot = load(snapshot)
    old_samples = {r["match_id"]: r for r in old_snapshot["samples"]}
    items = old_snapshot["task"]["candidate_items"]
    rows, batch_samples = [], {}
    for name, root in (("old", old_root), ("new", new_root)):
        for source in load(root / "progress.json")["candidates"]:
            path = Path(source["path"])
            if file_hash(path) != source["sha256"]:
                raise ValueError("Candidate source hash changed")
            preflight = path.parent.parent / "preflight.json"
            if preflight not in batch_samples:
                batch_samples[preflight] = {r["match_id"]: r for r in load(preflight)["samples"]}
            sample = batch_samples[preflight][source["match_id"]]
            raw = load(path)
            target = next(p for p in raw["players"] if p["player_slot"] == sample["target_slot"])
            observed = observe_purchases(target, items)
            row = {
                "match_id": source["match_id"],
                "cohort": name,
                "labels": [v["log_presence"] for v in observed["items"]],
                "mask": [v["log_presence_mask"] for v in observed["items"]],
            }
            if name == "old":
                original = old_samples[row["match_id"]]
                if row["labels"] != original["labels"] or row["mask"] != original["label_mask"]:
                    raise ValueError("Old source-log semantics changed")
                row["old_split"] = original["split"]
            rows.append(row)
        subset = [r for r in rows if r["cohort"] == name]
        if (
            support(subset, items)
            != rebuilt["distributions"][name + "_retained"]["log_observation_support"]
        ):
            raise ValueError("Candidate support differs from frozen cohort audit")
    groups = [g["match_ids"] for g in graph["groups"]]
    public, private = analyze(groups, rows, items)
    public["collections"] = {
        name: {k: v for k, v in collection.items() if k != "exclusions"}
        for name, collection in rebuilt["collections"].items()
    }
    public["provenance"] = {
        "audit_sha256": input_hashes[str(audit)],
        "summary_sha256": input_hashes[str(summary)],
        "snapshot_sha256": input_hashes[str(snapshot)],
        "source_reconstruction_verified": True,
        "audit_reconstruction": reconstruction,
        "producer_migration": "public-reader/1",
        "implementation_sha256": {
            str(p): file_hash(p)
            for p in (
                Path(__file__),
                Path("src/dota_items/data/cohort_split_feasibility.py"),
                Path("src/dota_items/data/purchase_observation.py"),
            )
        },
    }
    for path, expected in (rebuilt["evidence_sha256"] | input_hashes).items():
        if file_hash(Path(path)) != expected:
            raise ValueError("Evidence changed during analysis")
    return public, {
        "analysis_id": public["analysis_id"],
        "formal_split_assigned": False,
        "training_executed": False,
        "proposals": private,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("old-root", "new-root", "summary", "snapshot", "audit", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--allow-audit-producer-migration", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Refusing to overwrite analysis directory")
    public, private = build_report(
        args.old_root,
        args.new_root,
        args.summary,
        args.snapshot,
        args.audit,
        **({"allow_audit_migration": True} if args.allow_audit_producer_migration else {}),
    )
    args.output.mkdir(parents=False, exist_ok=False)
    # Complete receipt written last; interrupted output is not a completed analysis.
    for name, value in (("aggregate.json", public), ("private-proposals.json", private)):
        with (args.output / name).open("xb") as stream:
            stream.write(json_bytes(value))
    with (args.output / "complete.json").open("xb") as stream:
        stream.write(
            json_bytes(
                {
                    "schema_version": "cohort-split-analysis-complete/1",
                    "sha256": {
                        name: file_hash(args.output / name)
                        for name in ("aggregate.json", "private-proposals.json")
                    },
                }
            )
        )
    print(
        {
            "output": str(args.output),
            "candidate_count": public["candidate_count"],
            "training_executed": False,
        }
    )


if __name__ == "__main__":
    main()
