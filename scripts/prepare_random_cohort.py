"""Offline, source-replayed random v2 snapshot. No collection or model training."""

import argparse
from pathlib import Path

from analyze_cohort_splits import compare_audit

from dota_items.contracts.tasks import task_contract
from dota_items.data.cohort_handoff import build_audit
from dota_items.data.lineup_preflight import lineup_features
from dota_items.data.player_overlap import audit_player_overlap
from dota_items.data.purchase_observation import observe_purchases
from dota_items.data.random_cohort_snapshot import assemble_snapshot
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.modeling.batch import adapt_snapshot
from dota_items.storage import digest, file_hash, json_bytes


def load(path):
    return parse_source_json(read_source_bytes(path))


def inventory():
    return {
        str(p): file_hash(p)
        for root in (Path("data"), Path("reports"))
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def unchanged(hashes):
    for name, expected in hashes.items():
        if file_hash(Path(name)) != expected:
            raise ValueError(f"Protected input changed: {name}")


def build(args):
    rebuilt = build_audit(
        args.old_root, args.new_root, args.summary, args.snapshot, allow_producer_migration=True
    )
    replay = compare_audit(load(args.audit), rebuilt, allow=True)
    contract = task_contract()
    expected = {
        "hero_id": contract["target_hero_id"],
        "requested_role": 1,
        "requested_patch": "7.41f",
        "window_start": 0,
        "window_end": 1800,
        "candidate_items": contract["labels"]["candidate_items"],
    }
    old = {r["match_id"]: r for r in load(args.snapshot)["samples"]}
    old_audit = {r["match_id"]: r for r in load(args.summary)["audit"]["results"]}
    graph = rebuilt["graphs"]["including_new_excluded_inspectable"]
    groups = {mid: g["component"] for g in graph["groups"] for mid in g["match_ids"]}
    samples, audit_rows, paths, sources = [], [], {}, []
    batches = {}
    for cohort, root in (("old", args.old_root), ("new", args.new_root)):
        config = load(root / "collection.json")["audit_config"]
        if json_bytes({k: config.get(k) for k in expected}) != json_bytes(expected):
            raise ValueError("Collection scope differs from task")
        for source in load(root / "progress.json")["candidates"]:
            mid, path = source["match_id"], Path(source["path"])
            if mid in paths:
                raise ValueError("Duplicate candidate")
            if file_hash(path) != source["sha256"]:
                raise ValueError("Candidate source changed")
            if cohort == "old":
                row = old_audit[mid]
            else:
                preflight = path.parent.parent / "preflight.json"
                if preflight not in batches:
                    batches[preflight] = {
                        r["match_id"]: r for r in load(preflight)["audit"]["results"]
                    }
                row = batches[preflight][mid]
            if row["patch_time_check"] != "time_consistent":
                raise ValueError("Patch time evidence inconsistent")
            raw = load(path)
            if raw["match_id"] != mid:
                raise ValueError("Payload identity mismatch")
            target = next(p for p in raw["players"] if p["player_slot"] == row["target_slot"])
            if target["hero_id"] != 8:
                raise ValueError("Wrong target hero")
            observed = observe_purchases(target, expected["candidate_items"], start=0, end=1800)
            if observed["log_status"] != "present":
                raise ValueError("Missing or invalid candidate log")
            labels = [v["log_presence"] for v in observed["items"]]
            masks = [v["log_presence_mask"] for v in observed["items"]]
            if cohort == "old" and (
                labels != old[mid]["labels"] or masks != old[mid]["label_mask"]
            ):
                raise ValueError("Old source-label parity failed")
            samples.append(
                {
                    "match_id": mid,
                    "source_sha256": source["sha256"],
                    "cohort": cohort,
                    "group_id": groups[mid],
                    "features": lineup_features(row),
                    "labels": labels,
                    "label_mask": masks,
                    "role_hint": row["semantic_review"]["role_evidence"]["status"],
                }
            )
            sources.append({**source, "cohort": cohort})
            paths[mid] = path
            audit_rows.append(row)
    snapshot = assemble_snapshot(samples, seed=42)
    for cohort in ("old", "new"):
        subset = [r for r in samples if r["cohort"] == cohort]
        for i, key in enumerate(expected["candidate_items"]):
            values = [r["labels"][i] for r in subset if r["label_mask"][i]]
            observed = {
                "positive": values.count(1),
                "negative": values.count(0),
                "unknown": len(subset) - len(values),
            }
            frozen = rebuilt["distributions"][cohort + "_retained"]["log_observation_support"][key]
            if observed != {k: frozen[k] for k in observed}:
                raise ValueError("Support differs from source-replayed audit")
    snapshot["player_overlap"] = audit_player_overlap(audit_rows, paths, snapshot["splits"])
    snapshot["group_id_scope"] = "expanded graph including inspectable rejected new matches"
    package = Path("src/dota_items")
    snapshot["task_implementation_sha256"] = {
        name: file_hash(package / name)
        for name in ("contracts/tasks.py", "data/random_cohort_snapshot.py")
    }
    implementation = {
        str(p): file_hash(p)
        for p in [
            Path(__file__),
            Path("scripts/analyze_cohort_splits.py"),
            *sorted(package.rglob("*.py")),
        ]
    }
    snapshot["provenance"] = {
        "audit_reconstruction": replay,
        "source_manifest_sha256": digest(sources),
        "implementation_sha256": implementation,
        "frozen_audit_sha256": file_hash(args.audit),
    }
    shapes = {}
    for split in ("train", "validation"):
        batch = adapt_snapshot(snapshot, split)
        shapes[split] = {
            "X": list(batch.x.shape),
            "y": list(batch.y.shape),
            "mask": list(batch.mask.shape),
        }
    report = {
        "candidate_count": len(samples),
        "source_unique_count": len(paths),
        "seed": 42,
        "membership_sha256": snapshot["membership_sha256"],
        "split_counts": {k: len(v) for k, v in snapshot["splits"].items()},
        "support": snapshot["support"],
        "consumer_shapes": shapes,
        "train_model_items": snapshot["train_model_items"],
        "validation_both_class_items": [
            k for k, v in snapshot["support"]["validation"].items() if v["both_classes_present"]
        ],
        "player_overlap_summary": snapshot["player_overlap"]["summary"],
        "player_overlap_pairs": snapshot["player_overlap"]["split_pairs"],
        "audit_reconstruction": replay,
        "training_executed": False,
    }
    unchanged(rebuilt["evidence_sha256"])
    unchanged(implementation)
    return {
        "snapshot.json": snapshot,
        "report.json": report,
        "sources.json": sources,
        "source-audit.json": rebuilt,
        "split.json": {
            "policy": snapshot["split_policy"],
            "members": snapshot["splits"],
            "sha256": snapshot["membership_sha256"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("old-root", "new-root", "summary", "snapshot", "audit", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify and (args.output.exists() or args.output.is_symlink()):
        parser.error("Refusing to overwrite output")
    before = inventory()
    payloads = build(args)
    unchanged(before)
    if args.verify:
        receipt = load(args.output / "complete.json")
        for name, value in payloads.items():
            if json_bytes(value) != read_source_bytes(args.output / name):
                raise ValueError(f"Replay differs: {name}")
        unchanged({str(args.output / name): sha for name, sha in receipt["sha256"].items()})
        print("Source replay and all bundle hashes verified; no training")
        return
    args.output.mkdir(parents=False, exist_ok=False)
    payloads["protection.json"] = {"files": before, "count": len(before), "unchanged": True}
    for name, value in payloads.items():
        with (args.output / name).open("xb") as stream:
            stream.write(json_bytes(value))
    unchanged(before)
    with (args.output / "complete.json").open("xb") as stream:
        stream.write(
            json_bytes(
                {
                    "schema_version": "random-cohort-complete/1",
                    "sha256": {name: file_hash(args.output / name) for name in payloads},
                    "training_executed": False,
                }
            )
        )
    print(json_bytes(payloads["report.json"]).decode())


if __name__ == "__main__":
    main()
