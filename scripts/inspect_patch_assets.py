"""Inspect pinned map/mechanics candidates and existing non-holdout replay geometry."""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.map_replay_geometry import audit_replay_geometry, compare_landmark_positions
from dota_items.data.map_replay_source import open_geometry_source, read_landmark_capture
from dota_items.data.map_snapshot import compare_map_snapshots
from dota_items.data.patch_assets import verify_patch_assets
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "worlddata.json",
    "elevationdata.json",
    "gridnavdata.json",
    "mapdata.json",
    "lanedata.json",
)
PRODUCER_FILES = (
    "scripts/inspect_patch_assets.py",
    "src/dota_items/data/atomic_directory.py",
    "src/dota_items/data/patch_assets.py",
    "src/dota_items/data/map_snapshot.py",
    "src/dota_items/data/mechanics_candidate.py",
    "src/dota_items/data/map_replay_geometry.py",
    "src/dota_items/data/map_replay_source.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/data/awareness_split.py",
    "src/dota_items/storage.py",
)


def _read(path):
    return parse_source_json(read_source_bytes(Path(path)))


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _pinned_json(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Expected path/SHA-256 reference")
    path = Path(ref["path"])
    if not path.is_absolute():
        raise ValueError("Reference path must be absolute")
    raw = read_source_bytes(path)
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Pinned JSON changed")
    return parse_source_json(raw)


def run(spec_path, output, *, repository_root=ROOT):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    spec_path, repository_root = Path(spec_path).resolve(), Path(repository_root).resolve()
    code_before = {name: file_hash(repository_root / name) for name in PRODUCER_FILES}
    spec_bytes = read_source_bytes(spec_path)
    spec = parse_source_json(spec_bytes)
    if (
        not isinstance(spec, dict)
        or set(spec) != {"schema", "exact_patch", "binding", "replays", "older_map", "landmarks"}
        or spec["schema"] != "patch-assets-inspection/1"
    ):
        raise ValueError("Invalid patch inspection specification")
    binding_doc = _pinned_json(spec["binding"])
    binding = verify_patch_assets(
        binding_doc, exact_patch=spec["exact_patch"], repository_root=repository_root
    )
    # Inspect all manifests before opening their large channels, including U133 exclusion.
    if not isinstance(spec["replays"], list) or not spec["replays"]:
        raise ValueError("At least one replay reference is required")
    sources = [
        open_geometry_source(
            ref["path"],
            expected_sha256=ref["sha256"],
            exact_patch=spec["exact_patch"],
            match_allowed=lambda mid: not is_holdout(mid),
        )
        for ref in spec["replays"]
    ]
    if len({source.match_id for source in sources}) != len(sources):
        raise ValueError("Duplicate replay match")
    docs = {name: binding.map.read(name) for name in FILES}
    comparison = None
    if spec["older_map"] is not None:
        older = spec["older_map"]
        if set(older) != {"root", "files"}:
            raise ValueError("Invalid older map reference")
        comparison = compare_map_snapshots(
            binding.map, Path(older["root"]), expected_file_sha256=older["files"]
        )
    reports = [
        audit_replay_geometry(
            docs,
            source.rows("state"),
            match_id=source.match_id,
            patch=source.patch,
            replay_build=source.build,
            duration=source.duration,
            extras_rows=source.rows("extras"),
        )
        for source in sources
    ]
    landmark_reports = []
    if not isinstance(spec["landmarks"], list):
        raise ValueError("Landmarks must be explicit references")
    for ref in spec["landmarks"]:
        if not isinstance(ref, dict) or set(ref) != {"capture", "receipt"}:
            raise ValueError("Landmark output and receipt must both be pinned")
        header = _pinned_json(ref["capture"])
        source = next((s for s in sources if s.match_id == header.get("match_id")), None)
        if source is None:
            raise ValueError("Landmark capture does not match selected replays")
        capture = read_landmark_capture(ref["capture"], ref["receipt"], replay_source=source)
        landmark_reports.append(
            {
                "source": ref,
                "match_id": source.match_id,
                "comparison": compare_landmark_positions(docs, capture["observations"]),
                "capture_limits": {
                    "missing_coordinates": len(capture["missing_coordinates"]),
                    "unmapped": len(capture["unmapped"]),
                    "changes": len(capture["changes"]),
                },
            }
        )
    result = {
        "schema": "patch-assets-inspection-report/1",
        "binding": binding.binding,
        "assets": binding.summary(),
        "old_map_comparison": comparison,
        "replay_geometry": reports,
        "landmark_geometry": landmark_reports,
        "replay_builds": sorted({source.build for source in sources}),
        "map_client_version": binding.binding["map"]["client_version"],
        "compatibility_approved": False,
        "training_allowed": False,
        "action_review_allowed": False,
        "limits": (
            "Coordinate diagnostics do not validate camp semantics, routing, "
            "visibility or action ranking."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=".patch-inspection-", dir=output.parent))
    try:
        _write(scratch / "report.json", result)
        binding.verify_again()
        receipts = [source.verify_again() for source in sources]
        if read_source_bytes(spec_path) != spec_bytes:
            raise ValueError("Inspection specification changed")
        _pinned_json(spec["binding"])
        for ref in spec["landmarks"]:
            capture = _pinned_json(ref["capture"])
            source = next(s for s in sources if s.match_id == capture["match_id"])
            read_landmark_capture(ref["capture"], ref["receipt"], replay_source=source)
        if spec["older_map"] is not None:
            for name, digest in spec["older_map"]["files"].items():
                if file_hash(Path(spec["older_map"]["root"]) / name) != digest:
                    raise ValueError("Older map changed")
        if code_before != {name: file_hash(repository_root / name) for name in PRODUCER_FILES}:
            raise ValueError("Consumer code changed")
        _write(
            scratch / "receipt.json",
            {
                "schema": "patch-assets-inspection-receipt/1",
                "spec": {"path": str(spec_path), "sha256": hashlib.sha256(spec_bytes).hexdigest()},
                "consumer_sources": code_before,
                "inputs": receipts,
                "outputs": {"report.json": file_hash(scratch / "report.json")},
                "training_allowed": False,
            },
        )
        if output.exists():
            raise ValueError("Output appeared before publication")
        publish_directory(scratch, output)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "matches": len(result["replay_geometry"]),
                "action_review_allowed": result["action_review_allowed"],
            }
        )
    )


if __name__ == "__main__":
    main()
