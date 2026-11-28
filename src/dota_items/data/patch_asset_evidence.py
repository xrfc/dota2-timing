"""Pinned evidence for candidate patch assets; no gameplay or training admission."""

import copy
import hashlib
import json
import math
import re
from importlib.metadata import version
from pathlib import Path

from dota_items.data.map_replay_source import read_landmark_capture
from dota_items.data.source_io import read_source_bytes
from dota_items.storage import file_hash

CAPTURE_COMMON_FILES = (
    "src/dota_items/__init__.py",
    "src/dota_items/sources/__init__.py",
    "src/dota_items/data/__init__.py",
    "src/dota_items/contracts/__init__.py",
    "scripts/capture_map_runtime.py",
    "src/dota_items/sources/map_landmark_capture.py",
    "src/dota_items/sources/replay_identity.py",
    "src/dota_items/sources/gem_replay.py",
    "src/dota_items/sources/gem_observations.py",
    "src/dota_items/data/patch_asset_evidence.py",
    "src/dota_items/data/map_replay_source.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/data/awareness_split.py",
    "src/dota_items/data/atomic_directory.py",
    "src/dota_items/storage.py",
    "src/dota_items/normalize.py",
    "src/dota_items/domain.py",
    "src/dota_items/contracts/replay_context.py",
    "src/dota_items/contracts/numeric.py",
)


def capture_producer_files(kind):
    if kind not in {"runtime", "visibility"}:
        raise ValueError("Unknown map capture kind")
    return CAPTURE_COMMON_FILES + (f"src/dota_items/sources/map_{kind}_capture.py",)


RUNTIME_PRODUCER_FILES = capture_producer_files("runtime")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate evidence JSON key")
        result[key] = value
    return result


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite evidence value")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def decode_json(raw):
    value = json.loads(raw, object_pairs_hook=_pairs)
    _finite(value)
    return value


def validate_ref(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Expected an explicit path/SHA-256 reference")
    if not isinstance(ref["path"], str) or not Path(ref["path"]).is_absolute():
        raise ValueError("Evidence path must be absolute")
    if not isinstance(ref["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]):
        raise ValueError("Invalid evidence SHA-256")
    path = Path(ref["path"])
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError("Evidence must be a regular canonical file without symbolic links")
    return path


class EvidencePins:
    """Snapshot used bytes before work; recheck all files immediately before publication."""

    def __init__(self):
        self._pins = {}

    @property
    def inventory(self):
        return copy.deepcopy(self._pins)

    def read(self, ref):
        path = validate_ref(ref)
        raw = read_source_bytes(path)
        if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("Evidence digest mismatch")
        self.add(ref)
        return decode_json(raw)

    def add(self, ref):
        path = validate_ref(ref)
        old = self._pins.get(str(path))
        if old is not None and old != ref["sha256"]:
            raise ValueError("Conflicting evidence references")
        if file_hash(path) != ref["sha256"]:
            raise ValueError("Evidence digest mismatch")
        self._pins[str(path)] = ref["sha256"]

    def track(self, path):
        path = Path(path).absolute()
        ref = {"path": str(path), "sha256": file_hash(path)}
        self.add(ref)
        return ref

    def verify(self):
        for name, digest in self._pins.items():
            path = validate_ref({"path": name, "sha256": digest})
            if file_hash(path) != digest:
                raise ValueError("Evidence or producer changed before publication")


def read_fresh_capture(capture_ref, receipt_ref, *, source, pins, kind, repository_root):
    """Read a fresh runtime capture tied to this exact original replay manifest."""
    if kind not in {"runtime", "visibility"}:
        raise ValueError("Unknown map capture kind")
    doc, receipt = pins.read(capture_ref), pins.read(receipt_ref)
    expected = {"match_id": source.match_id, "patch": source.patch, "game_build": source.build}
    if (
        doc.get("schema") != f"map-{kind}-capture/1"
        or receipt.get("schema") != f"map-{kind}-capture-receipt/1"
        or any(row.get(key) != value for row in (doc, receipt) for key, value in expected.items())
        or doc.get("coordinate_space") != "world"
        or doc.get("omniscient") is not True
        or doc.get("training_allowed") is not False
        or receipt.get("training_allowed") is not False
        or receipt.get("manifest") != source.receipt()["manifest"]
        or receipt.get("output_sha256") != {"capture.json": capture_ref["sha256"]}
        or type(doc.get("post_game_tick")) is not int
        or doc["post_game_tick"] < 0
        or doc.get("parse_error") is not None
        or doc.get("truncated_at_tick") is not None
    ):
        raise ValueError("Runtime capture identity, completion or receipt mismatch")
    used = receipt.get("used_files")
    if not isinstance(used, dict) or not used:
        raise ValueError("Runtime evidence inventory missing")
    for name, digest in used.items():
        pins.add({"path": name, "sha256": digest})
    manifest_ref = source.receipt()["manifest"]
    manifest = pins.read(manifest_ref)
    old = receipt.get("landmarks")
    if not isinstance(old, dict) or set(old) != {"capture", "receipt"}:
        raise ValueError("Original landmark capture references missing")
    landmark = read_landmark_capture(old["capture"], old["receipt"], replay_source=source)
    old_receipt = pins.read(old["receipt"])
    pins.read(old["capture"])
    if (
        doc["post_game_tick"] != landmark["post_game_tick"]
        or doc["post_game_tick"] != manifest["quality"]["parser"].get("post_game_tick")
        or receipt.get("demo_sha256") != old_receipt.get("demo_sha256")
        or not isinstance(receipt.get("demo_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", receipt["demo_sha256"])
    ):
        raise ValueError("Capture end marker or decompressed archive differs from original")
    spec_ref = receipt.get("spec")
    spec = pins.read(spec_ref)
    if (
        spec.get("schema") != "map-runtime-capture-spec/1"
        or spec.get("capture_kind") != kind
        or spec.get("exact_patch") != source.patch
        or spec.get("replay") != manifest_ref
        or spec.get("landmarks") != old
    ):
        raise ValueError("Capture specification/source mismatch")
    required = dict(old_receipt["used_files"])
    for ref in (manifest_ref, old["capture"], old["receipt"], spec_ref):
        if ref["path"] in required and required[ref["path"]] != ref["sha256"]:
            raise ValueError("Conflicting original capture references")
        required[ref["path"]] = ref["sha256"]
    for name in capture_producer_files(kind):
        ref = pins.track(Path(repository_root) / name)
        required[ref["path"]] = ref["sha256"]
    for name, digest in required.items():
        if used.get(name) != digest:
            raise ValueError("Incomplete or changed capture producer/source inventory")
    dependencies = manifest["producer"].get("dependencies")
    if (
        not isinstance(dependencies, dict)
        or not dependencies
        or receipt.get("dependencies") != dependencies
        or old_receipt.get("dependencies") != dependencies
        or any(version(name) != value for name, value in dependencies.items())
    ):
        raise ValueError("Incomplete or changed capture dependencies")
    for ref in manifest["identity"]["source_references"]:
        if used.get(ref["path"]) != ref["sha256"]:
            raise ValueError("Original manifest source missing from capture")
        pins.add({"path": ref["path"], "sha256": ref["sha256"]})
    compat = Path(spec["compat"])
    actual = {str(p) for p in (compat / "gem").rglob("*") if p.suffix in {".py", ".json"}}
    declared = {
        name for name in old_receipt["used_files"] if Path(name).is_relative_to(compat / "gem")
    }
    if not actual or actual != declared:
        raise ValueError("Compatibility source/resource inventory changed")
    return doc


def read_runtime_capture(capture_ref, receipt_ref, *, source, pins, repository_root=None):
    return read_fresh_capture(
        capture_ref,
        receipt_ref,
        source=source,
        pins=pins,
        kind="runtime",
        repository_root=repository_root or Path(__file__).resolve().parents[3],
    )
