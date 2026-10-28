"""Strict /1 package integrity and schema checks; not research admission."""

import hashlib
import json
import math
import re
from pathlib import Path

_BUNDLE_SCHEMAS = {
    "snapshot.json": "purchase-log-modeling-snapshot/1",
    "summary.json": "purchase-collection-summary/1",
    "cohort-audit.json": "purchase-cohort-audit/1",
    "synthetic-reader-example.json": "purchase-log-modeling-snapshot/1",
    "INTERFACE.md": None,
}
_BUNDLE_SOURCES = set(_BUNDLE_SCHEMAS) - {"synthetic-reader-example.json"}


def load_handoff_json(contents):
    """Strict JSON decoding for the handoff boundary, not a semantic adapter."""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def finite(value):
        raise ValueError(f"Nonfinite JSON number: {value}")

    def floating(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            finite(value)
        return parsed

    return json.loads(
        contents, object_pairs_hook=unique, parse_constant=finite, parse_float=floating
    )


def _sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _bundle_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != (
        "purchase-data-handoff/1"
    ):
        raise ValueError("Unsupported handoff")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Missing or invalid bundle file manifest")
    for name, expected in files.items():
        # The existing /1 protocol has exactly five flat payload names, no aliases.
        if not name or name in (".", "..") or any(c in name for c in ("/", "\\", ":")):
            raise ValueError("Unsafe bundle path")
        if not _sha256(expected):
            raise ValueError(f"Invalid SHA-256: {name}")
    if set(files) != set(_BUNDLE_SCHEMAS):
        raise ValueError("Missing or unexpected bundle payload")
    if any(
        manifest.get(key) is not False
        for key in (
            "training_authorized_by_package",
            "new_snapshot_created",
            "raw_sources_included",
        )
    ):
        raise ValueError("Invalid handoff research boundaries")
    if not _sha256(manifest.get("producer_sha256")):
        raise ValueError("Invalid producer SHA-256")
    sources = manifest.get("source_paths")
    if (
        not isinstance(sources, dict)
        or set(sources) != _BUNDLE_SOURCES
        or any(not isinstance(path, str) or not path for path in sources.values())
    ):
        raise ValueError("Invalid source paths")
    # Source paths are descriptive provenance only; a reader never opens them.
    return files


def validate_bundle_payloads(manifest, payloads):
    """Validate /1 byte integrity and schema, NOT semantics, origin or permission."""
    files = _bundle_manifest(manifest)
    if set(payloads) != set(files):
        raise ValueError("Missing or unexpected bundle payload")
    decoded = {}
    for name, schema in _BUNDLE_SCHEMAS.items():
        contents = payloads[name]
        if hashlib.sha256(contents).hexdigest() != files[name]:
            raise ValueError(f"Hash mismatch: {name}")
        if schema is None:
            continue
        value = load_handoff_json(contents)
        if not isinstance(value, dict) or value.get("schema_version") != schema:
            raise ValueError(f"Unsupported payload schema: {name}")
        decoded[name] = value
    audit = decoded["cohort-audit.json"]
    for declaration in (manifest, audit):
        if (
            "producer_migration" in declaration
            and declaration["producer_migration"] != "public-reader/1"
        ):
            raise ValueError("Unsupported producer migration declaration")
    if manifest.get("producer_migration") != audit.get("producer_migration"):
        raise ValueError("Producer migration declarations differ")
    if any(
        audit.get(key) is not False
        for key in ("training_allowed", "new_split_assigned", "old_split_changed")
    ):
        raise ValueError("Audit changed research boundaries")
    example = decoded["synthetic-reader-example.json"]
    if example.get("synthetic") is not True or any(
        example.get(key) is not False
        for key in ("modeling_ready", "training_executed", "legacy_training_allowed")
    ):
        raise ValueError("Invalid synthetic reader example boundaries")
    return decoded["snapshot.json"]


def verify_bundle(directory):
    """Read a complete flat bundle without following bundle symlinks.

    No source paths are opened and no model is fitted. A matching hash is not
    authenticity, full snapshot semantic validation, or research authorization.
    """
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Unsafe or missing bundle directory")

    def contents(name):
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory.resolve():
            raise ValueError("Unsafe bundle path")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path.read_bytes()

    manifest = load_handoff_json(contents("manifest.json"))
    files = _bundle_manifest(manifest)
    payloads = {name: contents(name) for name in files}
    return validate_bundle_payloads(manifest, payloads)
