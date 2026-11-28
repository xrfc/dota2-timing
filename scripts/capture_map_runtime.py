"""Fresh runtime map evidence from an already pinned, non-holdout landmark capture."""

import argparse
import json
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.map_replay_source import open_geometry_source, read_landmark_capture
from dota_items.data.patch_asset_evidence import (
    CAPTURE_COMMON_FILES,
    EvidencePins,
    capture_producer_files,
)
from dota_items.sources.gem_replay import prepared_demo
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_FILES = CAPTURE_COMMON_FILES


def prepare(spec_path, pins):
    spec_ref = pins.track(spec_path)
    spec = pins.read(spec_ref)
    if (
        not isinstance(spec, dict)
        or set(spec) != {"schema", "capture_kind", "exact_patch", "replay", "landmarks", "compat"}
        or spec["schema"] != "map-runtime-capture-spec/1"
    ):
        raise ValueError("Invalid runtime capture specification")
    if spec["capture_kind"] not in {"runtime", "visibility"}:
        raise ValueError("Unknown map capture kind")
    ref = spec["replay"]
    source = open_geometry_source(
        ref["path"],
        expected_sha256=ref["sha256"],
        exact_patch=spec["exact_patch"],
        match_allowed=lambda mid: not is_holdout(mid),
    )
    old = spec["landmarks"]
    if not isinstance(old, dict) or set(old) != {"capture", "receipt"}:
        raise ValueError("Both original landmark output and receipt are required")
    landmark = read_landmark_capture(old["capture"], old["receipt"], replay_source=source)
    pins.read(old["capture"])
    receipt = pins.read(old["receipt"])
    for inventory in (source.receipt()["used_files"], receipt["used_files"]):
        for name, digest in inventory.items():
            pins.add({"path": name, "sha256": digest})
    manifest = pins.read(ref)
    demos = [
        Path(item["path"])
        for item in manifest["identity"]["source_references"]
        if Path(item["path"]).name
        in {
            f"{source.match_id}.dem",
            f"{source.match_id}.dem.bz2",
            f"{source.match_id}.dem.zst",
            f"{source.match_id}.dem.zip",
        }
    ]
    if len(demos) != 1 or str(demos[0]) not in pins.inventory:
        raise ValueError("Original pinned replay archive is missing or ambiguous")
    archive_ref = next(
        item for item in manifest["identity"]["source_references"] if item["path"] == str(demos[0])
    )
    pins.add({"path": archive_ref["path"], "sha256": archive_ref["sha256"]})
    if (
        type(archive_ref.get("size_bytes")) is not int
        or archive_ref["size_bytes"] <= 0
        or demos[0].stat().st_size != archive_ref["size_bytes"]
    ):
        raise ValueError("Original replay archive size mismatch")
    compat = Path(spec["compat"])
    if not compat.is_absolute() or compat.resolve() != compat or compat.is_symlink():
        raise ValueError("Compatibility directory must be canonical and absolute")
    cm_path = compat / "manifest.json"
    cm_digest = manifest["producer"]["parser"]["manifest_sha256"]
    cm = pins.read({"path": str(cm_path), "sha256": cm_digest})
    if cm.get("schema") != "gem-isolated-backport/1" or cm.get("base_version") != "0.10.0":
        raise ValueError("Unsupported compatibility source")
    # Inventory is inherited from the previous fresh capture, including JSON resources.
    expected = {
        Path(name).relative_to(compat / "gem").as_posix(): digest
        for name, digest in receipt["used_files"].items()
        if Path(name).is_relative_to(compat / "gem")
    }
    actual = {
        p.relative_to(compat / "gem").as_posix()
        for p in (compat / "gem").rglob("*")
        if p.suffix in {".py", ".json"}
    }
    if (
        actual != set(expected)
        or not expected
        or {k: v for k, v in expected.items() if k.endswith(".py")} != cm.get("patched")
    ):
        raise ValueError("Compatibility source/resource inventory changed")
    dependencies = receipt.get("dependencies")
    if (
        not isinstance(dependencies, dict)
        or not dependencies
        or dependencies != manifest["producer"].get("dependencies")
        or any(version(name) != value for name, value in dependencies.items())
    ):
        raise ValueError("Runtime dependencies differ from pinned capture")
    return spec, source, landmark, demos[0], compat, expected, dependencies


def run(spec_path, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    if any(name == "gem" or name.startswith("gem.") for name in sys.modules):
        raise ValueError("Fresh process required")
    pins = EvidencePins()
    for name in PRODUCER_FILES:
        pins.track(ROOT / name)
    prepared = prepare(Path(spec_path).absolute(), pins)
    spec, source, landmark, archive, compat, files, dependencies = prepared
    for name in capture_producer_files(spec["capture_kind"]):
        pins.track(ROOT / name)
    if spec["capture_kind"] == "runtime":
        from dota_items.sources.map_runtime_capture import capture
    else:
        from dota_items.sources.map_visibility_capture import capture
    initial_pins = pins.inventory
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".map-runtime-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        private, staging = temporary / "private", temporary / "result"
        staging.mkdir()
        for name, digest in files.items():
            target = private / "gem" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(compat / "gem" / name, target)
            if file_hash(target) != digest:
                raise ValueError("Compatibility copy changed")
        sys.path.insert(0, str(private))
        import gem

        if Path(gem.__file__).resolve() != private / "gem/__init__.py":
            raise ValueError("Unexpected parser import location")
        with prepared_demo(archive, temporary / "scratch") as demo:
            digest = file_hash(demo)
            result = capture(demo)
            if file_hash(demo) != digest:
                raise ValueError("Decompressed replay changed")
        if any(result.get(k) != landmark[k] for k in ("match_id", "game_build", "post_game_tick")):
            raise ValueError(
                "Fresh parse identity or completion differs from pinned landmark parse"
            )
        result.update(patch=source.patch, training_allowed=False, omniscient=True)
        (staging / "capture.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        prepare(Path(spec_path).absolute(), pins)
        if pins.inventory != initial_pins:
            raise ValueError("Capture input inventory changed")
        pins.verify()
        for name, expected in files.items():
            if file_hash(private / "gem" / name) != expected:
                raise ValueError("Private parser source/resource changed")
        receipt = {
            "schema": f"map-{spec['capture_kind']}-capture-receipt/1",
            "spec": {
                "path": str(Path(spec_path).absolute()),
                "sha256": initial_pins[str(Path(spec_path).absolute())],
            },
            "match_id": source.match_id,
            "patch": source.patch,
            "game_build": source.build,
            "manifest": spec["replay"],
            "landmarks": spec["landmarks"],
            "used_files": pins.inventory,
            "dependencies": dependencies,
            "demo_sha256": digest,
            "output_sha256": {"capture.json": file_hash(staging / "capture.json")},
            "training_allowed": False,
            "action_review_allowed": False,
            "limits": (
                "Fresh omniscient entity observations; no spawn rules or visibility certification."
            ),
        }
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        publish_directory(staging, output)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = run(args.spec, args.output)
    print(json.dumps({key: receipt[key] for key in ("match_id", "patch", "game_build")}))


if __name__ == "__main__":
    main()
