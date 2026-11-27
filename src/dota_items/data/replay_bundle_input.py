"""Explicit, hash-pinned replay inputs for downstream consumers.

The caller supplies the current expected producer and its match/patch policy.
This module does not import workflow, decide a product's split, or migrate old
producers. A reference is an integrity anchor, not a signature of authenticity.
"""

import hashlib
import json
import re
from pathlib import Path

from dota_items.data.replay_bundle import iter_channel, read_json_artifact
from dota_items.data.replay_bundle_quality import verify_quality_bundle
from dota_items.data.source_io import parse_source_json, read_source_bytes

REFERENCE_SCHEMA = "replay-bundle-reference/1"
_FIELDS = {"schema", "match_id", "patch", "bundle", "manifest_sha256", "training_allowed"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _allowed(mid, match_allowed):
    _require(type(mid) is int and mid > 0, "Expected a positive integer match ID")
    _require(callable(match_allowed), "An explicit match policy is required")
    _require(match_allowed(mid) is True, "Reserved match rejected before bundle access")


def validate_reference(value):
    _require(type(value) is dict and set(value) == _FIELDS, "Invalid bundle reference fields")
    _require(value["schema"] == REFERENCE_SCHEMA, "Unsupported bundle reference")
    _require(type(value["match_id"]) is int and value["match_id"] > 0, "Invalid reference match")
    _require(
        type(value["patch"]) is str and re.fullmatch(r"\d+\.\d+[a-z]?", value["patch"]),
        "Reference needs an exact patch",
    )
    _require(
        type(value["bundle"]) is str and Path(value["bundle"]).is_absolute(),
        "Reference bundle path must be absolute",
    )
    _require(
        type(value["manifest_sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", value["manifest_sha256"]),
        "Reference needs a manifest SHA-256",
    )
    _require(value["training_allowed"] is False, "Reference does not authorize training")
    return _copy(value)


def load_reference(path):
    return validate_reference(parse_source_json(read_source_bytes(Path(path), max_bytes=64 * 1024)))


def _manifest(root):
    path = Path(root) / "manifest.json"
    _require(not path.is_symlink(), "Manifest symlinks unsupported")
    raw = read_source_bytes(path, max_bytes=1024**2)
    return parse_source_json(raw), hashlib.sha256(raw).hexdigest()


class _BundleInput:
    """A verified read session; exhaust channel iterators and verify before publication."""

    def __init__(self, reference, expected_producer):
        self._reference = validate_reference(reference)
        _require(
            type(expected_producer) is dict and expected_producer, "Expected producer required"
        )
        self._producer = _copy(expected_producer)
        self._root = Path(self._reference["bundle"])
        self._pending = 0
        self._manifest = self._anchor()

    def _anchor(self):
        manifest, digest = _manifest(self._root)
        _require(digest == self._reference["manifest_sha256"], "Pinned manifest changed")
        _require(type(manifest) is dict, "Invalid bundle manifest")
        identity = manifest.get("identity", {})
        _require(type(identity) is dict, "Invalid bundle identity")
        _require(
            type(identity.get("match_id")) is int
            and identity["match_id"] == self._reference["match_id"],
            "Reference match identity mismatch",
        )
        window = identity.get("patch_window")
        _require(
            type(window) is dict and window.get("patch") == self._reference["patch"],
            "Reference patch identity mismatch",
        )
        return manifest

    def verify(self):
        _require(self._pending == 0, "Channel iterator not fully consumed")
        self._anchor()
        manifest = verify_quality_bundle(
            self._root,
            expected_identity=self._manifest["identity"],
            expected_producer=self._producer,
        )
        _require(manifest["quality"]["status"] == "passed", "Replay quality is not passed")
        self._anchor()
        return self.receipt()

    def normalized(self):
        self._anchor()
        value = read_json_artifact(self._root, "normalized")
        self._anchor()
        return value

    def metadata(self):
        self._anchor()
        reference = self._manifest["identity"]["source_references"][1]
        raw = read_source_bytes(Path(reference["path"]))
        _require(hashlib.sha256(raw).hexdigest() == reference["sha256"], "Metadata changed")
        self._anchor()
        return parse_source_json(raw)

    def rows(self, role):
        _require(role in ("state", "extras"), "Expected state or extras channel")
        self._anchor()
        self._pending += 1

        def consume():
            values = iter(iter_channel(self._root, role))
            try:
                header = next(values)
                _require(
                    type(header.get("match_id")) is int
                    and header["match_id"] == self._reference["match_id"],
                    "Channel match identity mismatch",
                )
                yield from values
                self._anchor()
                self._pending -= 1
            finally:
                values.close()

        return consume()

    def receipt(self):
        return {
            "schema": "replay-consumer-input/1",
            "reference": _copy(self._reference),
            "producer": _copy(self._producer),
            "patch_window": _copy(self._manifest["identity"]["patch_window"]),
            "game_build": self._manifest["quality"]["parser"]["game_build"],
            "duration": self._manifest["quality"]["base"]["metadata_duration"],
            "use": "engineering_review_only",
            "omniscient": True,
            "training_allowed": False,
        }


def open_bundle_input(reference, *, match_id, allowed_patches, expected_producer, match_allowed):
    """Reject split/patch/ID mismatches before opening a bundle's payloads."""
    _allowed(match_id, match_allowed)
    reference = validate_reference(reference)
    _require(reference["match_id"] == match_id, "Requested match differs from reference")
    _require(
        type(allowed_patches) in (tuple, list, set, frozenset) and bool(allowed_patches),
        "An explicit supported patch set is required",
    )
    _require(reference["patch"] in allowed_patches, "Patch unsupported by this consumer")
    source = _BundleInput(reference, expected_producer)
    source.verify()
    return source


def create_reference(root, *, match_id, expected_producer, match_allowed):
    """Verify a current producer output and return a small immutable-input reference."""
    _allowed(match_id, match_allowed)
    root = Path(root).absolute()
    manifest, digest = _manifest(root)
    _require(type(manifest) is dict, "Invalid bundle manifest")
    identity = manifest.get("identity")
    _require(type(identity) is dict, "Invalid bundle identity")
    window = identity.get("patch_window")
    _require(type(window) is dict, "Invalid patch window")
    patch = window.get("patch")
    reference = validate_reference(
        {
            "schema": REFERENCE_SCHEMA,
            "match_id": match_id,
            "patch": patch,
            "bundle": str(root),
            "manifest_sha256": digest,
            "training_allowed": False,
        }
    )
    open_bundle_input(
        reference,
        match_id=match_id,
        allowed_patches=(patch,),
        expected_producer=expected_producer,
        match_allowed=match_allowed,
    )
    return reference
