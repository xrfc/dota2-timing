"""Capture static landmarks from a pinned replay archive without changing frozen bundles."""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path, PurePosixPath

from dota_items.data.atomic_directory import publish_directory as _publish
from dota_items.data.awareness_split import is_holdout
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.gem_replay import prepared_demo
from dota_items.sources.map_landmark_capture import capture
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
CODE_PATHS = (
    "scripts/capture_map_landmarks.py",
    "src/dota_items/sources/map_landmark_capture.py",
    "src/dota_items/sources/replay_identity.py",
    "src/dota_items/sources/gem_replay.py",
    "src/dota_items/sources/gem_observations.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/data/awareness_split.py",
    "src/dota_items/data/atomic_directory.py",
    "src/dota_items/storage.py",
    "src/dota_items/normalize.py",
    "src/dota_items/domain.py",
    "src/dota_items/contracts/replay_context.py",
    "src/dota_items/contracts/numeric.py",
)


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("Expected SHA-256")
    return value


def _int(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid {name}")
    return value


def _read(path, digest):
    raw = read_source_bytes(path)
    if hashlib.sha256(raw).hexdigest() != _sha(digest):
        raise ValueError("Pinned manifest/metadata hash mismatch")
    return parse_source_json(raw)


def _relative(root, name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or PurePosixPath(name).is_absolute()
        or str(PurePosixPath(name)) != name
        or ".." in PurePosixPath(name).parts
    ):
        raise ValueError("Invalid compatibility relative path")
    path = root
    for part in PurePosixPath(name).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Compatibility symlink is not allowed")
    return path


def _verify_pins(pins):
    if any(file_hash(Path(name)) != digest for name, digest in pins.items()):
        raise ValueError("Source/code/compatibility drift")


def prepare_inputs(replay_manifest, manifest_sha256, patch, compat):
    """Identity and U133 exclusion run before any archive or compatibility reads."""
    code_pins = {str(ROOT / name): file_hash(ROOT / name) for name in CODE_PATHS}
    if not isinstance(patch, str) or re.fullmatch(r"[0-9]+\.[0-9]+[a-z]?", patch) is None:
        raise ValueError("Expected exact patch")
    path, compat = Path(replay_manifest).resolve(), Path(compat).resolve()
    doc = _read(path, manifest_sha256)
    if doc.get("schema") != "replay-bundle/1":
        raise ValueError("Expected replay-bundle/1")
    identity = doc["identity"]
    mid = _int(identity["match_id"], "match ID", 1)
    if is_holdout(mid):
        raise ValueError("U133 holdout match cannot be inspected")
    window = identity["patch_window"]
    if window["patch"] != patch or identity.get("training_allowed") is not False:
        raise ValueError("Replay patch or diagnostic-use identity mismatch")
    quality, parser = doc["quality"], doc["quality"]["parser"]
    build = _int(parser["game_build"], "game build", 1)
    _int(parser["post_game_tick"], "post-game end marker")
    if (
        quality.get("status") != "passed"
        or parser["match_id"] != mid
        or parser.get("parse_error") is not None
        or parser.get("truncated_at_tick") is not None
        or quality["base"]["observed_build"] != build
    ):
        raise ValueError("Stored replay parse identity/end evidence mismatch")
    pins = {**code_pins, str(path): manifest_sha256}
    references = identity["source_references"]
    if not isinstance(references, list) or not references:
        raise ValueError("Replay has no source references")
    demo, metadata = None, None
    for ref in references:
        source = Path(ref["path"])
        if not source.is_absolute() or str(source) in pins or source.is_symlink():
            raise ValueError("Invalid/duplicate source reference")
        _sha(ref["sha256"])
        if source.stat().st_size != _int(ref["size_bytes"], "source size", 1):
            raise ValueError("Source size mismatch")
        if file_hash(source) != ref["sha256"]:
            raise ValueError("Source hash mismatch")
        pins[str(source)] = ref["sha256"]
        if source.name in {f"{mid}.dem", f"{mid}.dem.bz2", f"{mid}.dem.zst", f"{mid}.dem.zip"}:
            if demo is not None:
                raise ValueError("Duplicate replay source")
            demo = source
        elif source.name == f"{mid}.json":
            if metadata is not None:
                raise ValueError("Duplicate metadata source")
            metadata = _read(source, ref["sha256"])
    if demo is None or metadata is None:
        raise ValueError("Replay archive/metadata reference is missing")
    start = _int(metadata["start_time"], "match start")
    if (
        metadata["match_id"] != mid
        or identity["discovery"]["match_id"] != mid
        or identity["discovery"]["start_time"] != start
        or metadata["patch"] != identity["expected_patch_code"]
        or not _int(window["release_timestamp"], "patch start")
        <= start
        < _int(window["upper_exclusive"], "patch end", 1)
    ):
        raise ValueError("Metadata falls outside pinned patch identity")
    original_parser = doc["producer"]["parser"]
    cm_path = compat / "manifest.json"
    cm_digest = _sha(original_parser["manifest_sha256"])
    cm = _read(cm_path, cm_digest)
    if (
        cm.get("schema") != "gem-isolated-backport/1"
        or cm.get("base_version") != "0.10.0"
        or original_parser.get("verified_python_files") != 190
        or version("gem-dota") != original_parser.get("distribution_version")
    ):
        raise ValueError("Unsupported pinned compatibility identity")
    pins[str(cm_path)] = cm_digest
    actual = {p.relative_to(compat / "gem").as_posix() for p in (compat / "gem").rglob("*.py")}
    if (
        not isinstance(cm.get("patched"), dict)
        or len(cm["patched"]) != 190
        or actual != set(cm["patched"])
    ):
        raise ValueError("Compatibility Python inventory mismatch")
    for name, digest in cm["patched"].items():
        source = _relative(compat / "gem", name)
        if file_hash(source) != _sha(digest):
            raise ValueError("Compatibility source hash mismatch")
        pins[str(source)] = digest
    resources = sorted((compat / "gem").rglob("*.json"))
    for source in resources:
        _relative(compat / "gem", source.relative_to(compat / "gem").as_posix())
        pins[str(source)] = file_hash(source)
    dependencies = {name: version(name) for name in doc["producer"]["dependencies"]}
    if dependencies != doc["producer"]["dependencies"]:
        raise ValueError("Replay runtime dependencies changed")
    _verify_pins(pins)
    return {
        "match_id": mid,
        "patch": patch,
        "game_build": build,
        "demo": demo,
        "compat": compat,
        "manifest": {"path": str(path), "sha256": manifest_sha256},
        "pins": pins,
        "compatibility": {
            "manifest_sha256": cm_digest,
            "python_files": cm["patched"],
            "resources": [p.relative_to(compat / "gem").as_posix() for p in resources],
        },
        "dependencies": dependencies,
        "original_producer": doc["producer"],
    }


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run(replay_manifest, manifest_sha256, patch, compat, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    if any(name == "gem" or name.startswith("gem.") for name in sys.modules):
        raise ValueError("Fresh process required: Gem has already been imported")
    prepared = prepare_inputs(replay_manifest, manifest_sha256, patch, compat)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".landmarks-") as temporary:
        temporary = Path(temporary)
        private, staging = temporary / "compat", temporary / "result"
        staging.mkdir()
        for name in [
            *prepared["compatibility"]["python_files"],
            *prepared["compatibility"]["resources"],
        ]:
            source = prepared["compat"] / "gem" / name
            target = private / "gem" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if file_hash(target) != prepared["pins"][str(source)]:
                raise ValueError("Compatibility copy changed")
        sys.path.insert(0, str(private))
        import gem

        if Path(gem.__file__).resolve() != private / "gem/__init__.py":
            raise ValueError("Unexpected Gem import location")
        with prepared_demo(prepared["demo"], temporary / "scratch") as demo:
            demo_digest = file_hash(demo)
            result = capture(demo)
            if file_hash(demo) != demo_digest:
                raise ValueError("Decompressed demo changed during parsing")
        if (
            result["match_id"] != prepared["match_id"]
            or result["game_build"] != prepared["game_build"]
        ):
            raise ValueError("Fresh parse match/build differs from pinned replay identity")
        result.update(patch=patch, training_allowed=False)
        _write(staging / "capture.json", result)
        _verify_pins(prepared["pins"])
        again = prepare_inputs(replay_manifest, manifest_sha256, patch, compat)
        if again["pins"] != prepared["pins"]:
            raise ValueError("Source or compatibility inventory drift")
        for name in [
            *prepared["compatibility"]["python_files"],
            *prepared["compatibility"]["resources"],
        ]:
            if (
                file_hash(private / "gem" / name)
                != prepared["pins"][str(prepared["compat"] / "gem" / name)]
            ):
                raise ValueError("Private compatibility source drift")
        receipt = {
            "schema": "map-landmark-capture-receipt/1",
            "match_id": result["match_id"],
            "patch": patch,
            "game_build": result["game_build"],
            "manifest": prepared["manifest"],
            "demo_sha256": demo_digest,
            "used_files": prepared["pins"],
            "dependencies": prepared["dependencies"],
            "original_producer": prepared["original_producer"],
            "output_sha256": {"capture.json": file_hash(staging / "capture.json")},
            "counts": {
                key: len(result[key])
                for key in ("observations", "missing_coordinates", "unmapped", "changes")
            },
            "training_allowed": False,
            "map_geometry_verified": False,
            "limits": (
                "Fresh static-entity parse; does not certify "
                "the original bundle producer or terrain."
            ),
        }
        _write(staging / "receipt.json", receipt)
        _publish(staging, output)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--compat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    result = run(**vars(parser.parse_args()))
    print(json.dumps({key: result[key] for key in ("match_id", "patch", "game_build", "counts")}))


if __name__ == "__main__":
    main()
