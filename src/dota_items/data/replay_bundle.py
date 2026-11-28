"""Immutable, lossless compressed replay artifacts with explicit provenance.

A bundle is complete only when its manifest exists. Writers create a new root,
never replace existing files, and publish the manifest last. Packing is a storage
operation: original byte digests and producer identities remain visible. It does
not certify field semantics, authorize training, or remove historical artifacts.
"""

import gzip
import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dota_items.data.source_io import AuditInputError, parse_source_json, read_source_bytes
from dota_items.storage import file_hash, inside

SCHEMA = "replay-bundle/1"
MAX_ARTIFACT_BYTES = 2 * 1024**3
MAX_LINE_BYTES = 16 * 1024**2
MAX_MANIFEST_BYTES = 4 * 1024**2
BLOCK_BYTES = 1024**2
WRITE_BUFFER_BYTES = 64 * 1024
GZIP_LEVEL = 6
_ROLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DESCRIPTOR_KEYS = {
    "path",
    "codec",
    "format",
    "compressed_sha256",
    "uncompressed_sha256",
    "compressed_bytes",
    "uncompressed_bytes",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _json_value(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        _require(math.isfinite(value), "Non-finite JSON value")
        return
    if type(value) is list:
        for child in value:
            _json_value(child)
        return
    if type(value) is dict:
        _require(all(type(key) is str for key in value), "JSON object keys must be strings")
        for child in value.values():
            _json_value(child)
        return
    raise ValueError("Unsupported JSON value")


def _clone(value: Any) -> Any:
    _json_value(value)
    return parse_source_json(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())


def _object(value: Any, name: str) -> dict:
    _require(type(value) is dict, f"{name} must be an object")
    return _clone(value)


def _limit(value: int, name: str) -> int:
    _require(type(value) is int and value >= 0, f"{name} must be a nonnegative integer")
    return value


def _sha(value: Any) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _same_json(left: Any, right: Any) -> bool:
    _json_value(left)
    _json_value(right)
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False
    )


def _regular(path: Path) -> None:
    _require(not path.is_symlink() and path.is_file(), "Missing or non-regular source file")
    _require(all(not parent.is_symlink() for parent in path.parents), "Source symlinks unsupported")


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_bytes(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".bundle-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
        _sync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def _reference(reference: Any, *, verify: bool) -> None:
    _require(
        type(reference) is dict and set(reference) == {"path", "sha256", "size_bytes"},
        "Invalid source reference",
    )
    _require(type(reference["path"]) is str, "Invalid source reference path")
    path = Path(reference["path"])
    _require(path.is_absolute(), "Source reference paths must be absolute")
    _require(_sha(reference["sha256"]), "Invalid source reference digest")
    _limit(reference["size_bytes"], "source size_bytes")
    if verify:
        _regular(path)
        _require(path.stat().st_size == reference["size_bytes"], "Source reference size changed")
        _require(file_hash(path) == reference["sha256"], "Source reference digest changed")


def _references(identity: dict, artifacts: dict, *, verify: bool) -> None:
    references = identity.get("source_references", [])
    _require(type(references) is list, "source_references must be a list")
    for reference in references:
        _reference(reference, verify=verify)
    for descriptor in artifacts.values():
        if "source" in descriptor:
            _reference(descriptor["source"], verify=verify)
            _require(
                descriptor["source"]["sha256"] == descriptor["uncompressed_sha256"]
                and descriptor["source"]["size_bytes"] == descriptor["uncompressed_bytes"],
                "Packed source does not match its uncompressed artifact",
            )


def _descriptor(root: Path, role: Any, value: Any) -> Path:
    _require(type(role) is str and _ROLE.fullmatch(role) is not None, "Invalid artifact role")
    _require(type(value) is dict, "Artifact descriptor must be an object")
    _require(
        set(value) in (_DESCRIPTOR_KEYS, _DESCRIPTOR_KEYS | {"source"}),
        "Unexpected artifact descriptor fields",
    )
    _require(type(value["path"]) is str and value["path"].endswith(".gz"), "Invalid gzip path")
    _require(Path(value["path"]).as_posix() == value["path"], "Noncanonical artifact path")
    _require(value["path"] != "manifest.json", "Reserved artifact path")
    path = inside(root, value["path"])
    _require(value["codec"] == "gzip", "Unsupported artifact codec")
    _require(value["format"] in ("bytes", "json", "jsonl"), "Unsupported artifact format")
    for key in ("compressed_sha256", "uncompressed_sha256"):
        _require(_sha(value[key]), "Invalid artifact digest")
    for key in ("compressed_bytes", "uncompressed_bytes"):
        _limit(value[key], key)
    _require(value["uncompressed_bytes"] <= MAX_ARTIFACT_BYTES, "Artifact exceeds size limit")
    _require(
        value["compressed_bytes"] <= MAX_ARTIFACT_BYTES + 64 * 1024**2,
        "Compressed artifact exceeds size limit",
    )
    return path


def _inventory(root: Path, artifacts: dict, *, with_manifest: bool) -> None:
    expected = {descriptor["path"] for descriptor in artifacts.values()}
    _require(len(expected) == len(artifacts), "Artifact paths must be unique")
    if with_manifest:
        expected.add("manifest.json")
    allowed_dirs = set()
    for relative in expected:
        allowed_dirs.update(str(parent) for parent in Path(relative).parents if str(parent) != ".")
    observed = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        _require(not path.is_symlink(), "Bundle symlinks unsupported")
        if path.is_dir():
            _require(relative in allowed_dirs, "Unexpected bundle directory")
        else:
            _regular(path)
            observed.add(relative)
    _require(observed == expected, "Bundle file inventory differs from manifest")


def _verify_artifact(root: Path, role: str, descriptor: dict) -> None:
    path = _descriptor(root, role, descriptor)
    _regular(path)
    _require(path.stat().st_size == descriptor["compressed_bytes"], "Compressed size changed")
    _require(file_hash(path) == descriptor["compressed_sha256"], "Compressed digest changed")
    result = hashlib.sha256()
    size = 0
    try:
        with gzip.open(path, "rb") as stream:
            for block in iter(lambda: stream.read(BLOCK_BYTES), b""):
                size += len(block)
                _require(
                    size <= descriptor["uncompressed_bytes"], "Decompressed size exceeds manifest"
                )
                result.update(block)
    except (OSError, EOFError) as error:
        raise ValueError("Invalid or incomplete gzip artifact") from error
    _require(size == descriptor["uncompressed_bytes"], "Uncompressed size changed")
    _require(result.hexdigest() == descriptor["uncompressed_sha256"], "Uncompressed digest changed")
    _require(
        file_hash(path) == descriptor["compressed_sha256"], "Artifact changed during verification"
    )


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate manifest JSON key")
        result[key] = value
    return result


def _manifest(root: Path) -> dict:
    _require(not root.is_symlink() and root.is_dir(), "Missing or invalid bundle root")
    _require(all(not parent.is_symlink() for parent in root.parents), "Bundle symlinks unsupported")
    path = inside(root, "manifest.json")
    raw = read_source_bytes(path, max_bytes=MAX_MANIFEST_BYTES)
    value = parse_source_json(raw)
    json.loads(raw, object_pairs_hook=_unique_pairs)
    _object(value, "manifest")
    _require(
        set(value) == {"schema", "identity", "producer", "quality", "artifacts"},
        "Unexpected manifest fields",
    )
    _require(value["schema"] == SCHEMA, "Unsupported replay bundle schema")
    for key in ("identity", "producer", "quality", "artifacts"):
        _require(type(value[key]) is dict, f"{key} must be an object")
    _require(bool(value["artifacts"]), "Bundle has no artifacts")
    for role, descriptor in value["artifacts"].items():
        _descriptor(root, role, descriptor)
    _references(value["identity"], value["artifacts"], verify=False)
    _inventory(root, value["artifacts"], with_manifest=True)
    return value


class BundleWriter:
    """Write a new bundle without overwriting existing files or source bytes."""

    def __init__(self, root: Path, *, identity: dict, producer: dict):
        self.identity = _object(identity, "identity")
        self.producer = _object(producer, "producer")
        _references(self.identity, {}, verify=True)
        candidate = Path(root).absolute()
        _require(
            all(not parent.is_symlink() for parent in candidate.parents),
            "Bundle symlinks unsupported",
        )
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.mkdir(exist_ok=False)
        self.root = candidate
        self.artifacts = {}
        self._finished = False
        self._failed = False

    def _write(
        self, role: str, chunks: Iterable[bytes], *, filename: str | None, kind: str
    ) -> dict:
        _require(not self._finished and not self._failed, "Bundle writer is closed or failed")
        _require(type(role) is str and _ROLE.fullmatch(role) is not None, "Invalid artifact role")
        _require(role not in self.artifacts, "Artifact role already exists")
        suffix = ".jsonl.gz" if kind == "jsonl" else ".json.gz" if kind == "json" else ".gz"
        relative = filename if filename is not None else role + suffix
        _require(
            type(relative) is str and relative.endswith(".gz"), "Artifact filename must end in .gz"
        )
        _require(Path(relative).as_posix() == relative, "Noncanonical artifact path")
        _require(
            relative not in {d["path"] for d in self.artifacts.values()},
            "Artifact path already exists",
        )
        target = inside(self.root, relative)
        _require(not target.exists(), "Artifact already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".bundle-", dir=target.parent)
        temp = Path(temporary)
        size, digest = 0, hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as output:
                with gzip.GzipFile(
                    filename="", mode="wb", fileobj=output, compresslevel=GZIP_LEVEL, mtime=0
                ) as stream:
                    pending = bytearray()

                    def emit(block):
                        digest.update(block)
                        stream.write(block)

                    for chunk in chunks:
                        _require(type(chunk) is bytes, "Artifact chunks must be bytes")
                        size += len(chunk)
                        _require(size <= MAX_ARTIFACT_BYTES, "Artifact exceeds size limit")
                        if pending and len(pending) + len(chunk) > WRITE_BUFFER_BYTES:
                            emit(pending)
                            pending.clear()
                        if len(chunk) >= WRITE_BUFFER_BYTES:
                            emit(chunk)
                        else:
                            pending.extend(chunk)
                    if pending:
                        emit(pending)
                output.flush()
                os.fsync(output.fileno())
            descriptor = {
                "path": relative,
                "codec": "gzip",
                "format": kind,
                "compressed_sha256": file_hash(temp),
                "uncompressed_sha256": digest.hexdigest(),
                "compressed_bytes": temp.stat().st_size,
                "uncompressed_bytes": size,
            }
            os.link(temp, target)
            _sync_directory(target.parent)
            self.artifacts[role] = descriptor
            return _clone(descriptor)
        except Exception:
            self._failed = True
            raise
        finally:
            temp.unlink(missing_ok=True)

    def add_file(self, role: str, source: Path, *, filename: str | None = None) -> dict:
        source = Path(source).absolute()
        _regular(source)
        before = source.stat()
        _require(before.st_size <= MAX_ARTIFACT_BYTES, "Source exceeds size limit")

        def chunks():
            with source.open("rb") as stream:
                yield from iter(lambda: stream.read(BLOCK_BYTES), b"")

        descriptor = self._write(role, chunks(), filename=filename, kind="bytes")
        try:
            after = source.stat()
            _require(
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
                "Source changed during packing",
            )
            _require(
                file_hash(source) == descriptor["uncompressed_sha256"],
                "Source changed during packing",
            )
        except Exception:
            self._failed = True
            raise
        descriptor["source"] = {
            "path": str(source),
            "sha256": descriptor["uncompressed_sha256"],
            "size_bytes": descriptor["uncompressed_bytes"],
        }
        self.artifacts[role] = _clone(descriptor)
        return descriptor

    def add_json(self, role: str, value: Any, *, filename: str | None = None) -> dict:
        _json_value(value)
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False)
        return self._write(
            role,
            (piece.encode("utf-8") for piece in encoder.iterencode(value)),
            filename=filename,
            kind="json",
        )

    def add_channel(
        self, role: str, header: dict, rows: Iterable[dict], *, filename: str | None = None
    ) -> dict:
        header = _object(header, "channel header")
        _require(
            type(header.get("seconds")) is int and header["seconds"] >= 0,
            "Channel header needs an accurate seconds count",
        )
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False)

        def chunks():
            count = 0
            for value in (header,):
                for piece in encoder.iterencode(value):
                    yield piece.encode("utf-8")
                yield b"\n"
            for row in rows:
                _require(type(row) is dict, "Channel rows must be objects")
                _json_value(row)
                count += 1
                _require(count <= header["seconds"], "Channel has more rows than header seconds")
                for piece in encoder.iterencode(row):
                    yield piece.encode("utf-8")
                yield b"\n"
            _require(count == header["seconds"], "Channel has fewer rows than header seconds")

        return self._write(role, chunks(), filename=filename, kind="jsonl")

    def finish(self, quality: dict) -> dict:
        _require(not self._finished and not self._failed, "Bundle writer is closed or failed")
        quality = _object(quality, "quality")
        _require(bool(self.artifacts), "Bundle has no artifacts")
        for role, descriptor in self.artifacts.items():
            _verify_artifact(self.root, role, descriptor)
        _inventory(self.root, self.artifacts, with_manifest=False)
        _references(self.identity, self.artifacts, verify=True)
        manifest = {
            "schema": SCHEMA,
            "identity": _clone(self.identity),
            "producer": _clone(self.producer),
            "quality": quality,
            "artifacts": _clone(self.artifacts),
        }
        raw = (
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n"
        ).encode()
        _require(len(raw) <= MAX_MANIFEST_BYTES, "Manifest exceeds size limit")
        _atomic_bytes(self.root / "manifest.json", raw)
        self._finished = True
        return manifest


def verify_bundle(
    root: Path,
    *,
    expected_identity: dict | None = None,
    expected_producer: dict | None = None,
    verify_references: bool = True,
) -> dict:
    """Verify every stored byte and declared external source reference.

    This is integrity and identity checking, not an authenticity signature or a
    model-quality approval. An external receipt may additionally pin manifest SHA.
    """
    _require(type(verify_references) is bool, "verify_references must be boolean")
    root = Path(root).absolute()
    manifest = _manifest(root)
    if expected_identity is not None:
        _require(_same_json(manifest["identity"], expected_identity), "Bundle identity mismatch")
    if expected_producer is not None:
        _require(_same_json(manifest["producer"], expected_producer), "Bundle producer mismatch")
    for role, descriptor in manifest["artifacts"].items():
        _verify_artifact(root, role, descriptor)
    _references(manifest["identity"], manifest["artifacts"], verify=verify_references)
    return manifest


def _artifact(root: Path, role: str, *, max_bytes: int, label: str) -> tuple[Path, dict]:
    root = Path(root).absolute()
    manifest = _manifest(root)
    _require(type(role) is str and role in manifest["artifacts"], "Unknown artifact role")
    descriptor = manifest["artifacts"][role]
    _require(descriptor["uncompressed_bytes"] <= max_bytes, f"{label} exceeds read limit")
    _verify_artifact(root, role, descriptor)
    return inside(root, descriptor["path"]), descriptor


class _GzipSource:
    def __init__(self, path):
        self.path = path

    def open(self, mode):
        return gzip.open(self.path, mode)


def read_json_artifact(root: Path, role: str, max_bytes: int = MAX_ARTIFACT_BYTES) -> Any:
    """Read one bounded JSON artifact; source files need not remain available."""
    _limit(max_bytes, "max_bytes")
    path, descriptor = _artifact(root, role, max_bytes=max_bytes, label="JSON artifact")
    _require(descriptor["format"] in ("bytes", "json"), "Artifact is not a JSON document")
    _require(descriptor["uncompressed_bytes"] <= max_bytes, "JSON artifact exceeds read limit")
    try:
        raw = read_source_bytes(_GzipSource(path), max_bytes=max_bytes)
    except AuditInputError as error:
        raise ValueError("JSON artifact exceeds read limit") from error
    _require(
        hashlib.sha256(raw).hexdigest() == descriptor["uncompressed_sha256"],
        "Artifact changed during read",
    )
    value = parse_source_json(raw)
    _json_value(value)
    return value


def iter_channel(
    root: Path,
    role: str,
    max_line_bytes: int = MAX_LINE_BYTES,
    max_total_bytes: int = MAX_ARTIFACT_BYTES,
) -> Iterable[dict]:
    """Yield header then rows, with per-line/total bounds and byte verification."""
    _limit(max_line_bytes, "max_line_bytes")
    _limit(max_total_bytes, "max_total_bytes")
    path, descriptor = _artifact(root, role, max_bytes=max_total_bytes, label="Channel")
    _require(descriptor["format"] == "jsonl", "Artifact is not a JSONL channel")
    _require(descriptor["uncompressed_bytes"] <= max_total_bytes, "Channel exceeds read limit")
    size, digest, rows = 0, hashlib.sha256(), 0
    header = None
    with gzip.open(path, "rb") as stream:
        while line := stream.readline(max_line_bytes + 1):
            _require(len(line) <= max_line_bytes, "Channel line exceeds read limit")
            size += len(line)
            _require(size <= max_total_bytes, "Channel exceeds read limit")
            _require(line.endswith(b"\n"), "Incomplete JSONL line")
            digest.update(line)
            value = parse_source_json(line)
            _require(type(value) is dict, "Channel entries must be objects")
            _json_value(value)
            if header is None:
                header = value
                _require(
                    type(header.get("seconds")) is int and header["seconds"] >= 0,
                    "Invalid channel header seconds",
                )
            else:
                rows += 1
                _require(rows <= header["seconds"], "Channel row count exceeds header")
            yield value
    _require(
        header is not None and rows == header["seconds"], "Channel row count differs from header"
    )
    _require(size == descriptor["uncompressed_bytes"], "Channel size changed during read")
    _require(
        digest.hexdigest() == descriptor["uncompressed_sha256"],
        "Channel digest changed during read",
    )


def pack_files(
    output: Path,
    sources: dict[str, Path],
    identity: dict,
    producer: dict,
) -> dict:
    """Losslessly compress existing files into a new bundle without deleting them."""
    _require(type(sources) is dict and bool(sources), "sources must be a nonempty mapping")
    writer = BundleWriter(output, identity=identity, producer=producer)
    for role, source in sorted(sources.items()):
        writer.add_file(role, source)
    return writer.finish(
        {"status": "lossless_storage_verified", "semantic_quality": "not_evaluated"}
    )
