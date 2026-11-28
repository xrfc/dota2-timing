"""Read pinned state channels for geometry diagnostics, not full bundle admission.

This narrow adapter consumes the published replay-bundle/1 format without depending
on the unmerged pipeline implementation. It checks bytes/identity and drains gzip;
it does not re-certify that producer, the raw parser, or full replay quality.
"""

import gzip
import hashlib
import re
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

SHA = re.compile(r"[a-f0-9]{64}")
LIMIT = 1024 * 1024 * 1024


def _digest(value):
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValueError("Expected SHA-256")
    return value


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid {name}")
    return value


def _read(path, expected):
    raw = read_source_bytes(Path(path))
    if hashlib.sha256(raw).hexdigest() != _digest(expected):
        raise ValueError("Source hash mismatch")
    return parse_source_json(raw)


def open_geometry_source(manifest_path, *, expected_sha256, exact_patch, match_allowed):
    """Check match exclusion before reading channels or metadata; pin all used bytes."""
    path = Path(manifest_path).resolve()
    doc = _read(path, expected_sha256)
    if doc.get("schema") != "replay-bundle/1":
        raise ValueError("Unsupported replay geometry source")
    identity, quality = doc["identity"], doc["quality"]
    mid = _integer(identity["match_id"], "match ID", 1)
    if not match_allowed(mid):
        raise ValueError("Match excluded by caller policy")
    if identity.get("training_allowed") is not False:
        raise ValueError("Expected diagnostic source")
    window = identity["patch_window"]
    if window["patch"] != exact_patch:
        raise ValueError("Exact replay patch mismatch")
    parser = quality["parser"]
    build = _integer(parser["game_build"], "replay build", 1)
    if (
        quality.get("status") != "passed"
        or parser["match_id"] != mid
        or quality["base"]["observed_build"] != build
        or parser.get("parse_error") is not None
        or parser.get("truncated_at_tick") is not None
    ):
        raise ValueError("Stored replay identity/end evidence is inconsistent")
    duration = _integer(quality["base"]["metadata_duration"], "duration")
    if quality["base"]["normalized_duration"] != duration:
        raise ValueError("Stored replay durations differ")
    if not isinstance(doc.get("producer"), dict):
        raise ValueError("Missing original producer identity")
    pins = {str(path): expected_sha256}
    metadata = None
    references = identity["source_references"]
    for ref in references:
        source = Path(ref["path"])
        if not source.is_absolute():
            raise ValueError("Source reference must be absolute")
        if source.name == f"{mid}.json":
            if metadata is not None:
                raise ValueError("Duplicate metadata")
            metadata = _read(source, ref["sha256"])
            pins[str(source)] = ref["sha256"]
    if metadata is None or metadata.get("match_id") != mid or metadata.get("duration") != duration:
        raise ValueError("Metadata identity or duration mismatch")
    start = _integer(metadata["start_time"], "start time")
    if identity["discovery"]["match_id"] != mid or identity["discovery"]["start_time"] != start:
        raise ValueError("Discovery identity mismatch")
    lower = _integer(window["release_timestamp"], "patch lower boundary")
    upper = _integer(window["upper_exclusive"], "patch upper boundary", 1)
    if not lower <= start < upper or metadata.get("patch") != identity["expected_patch_code"]:
        raise ValueError("Metadata outside frozen patch identity")
    channels = {}
    for name, filename in (("state", "state-v3.jsonl.gz"), ("extras", "extras-v1.jsonl.gz")):
        item = doc["artifacts"][name]
        if item["path"] != filename or item["format"] != "jsonl" or item["codec"] != "gzip":
            raise ValueError("Unsupported geometry channel")
        channel = path.parent / filename
        if channel.resolve().parent != path.parent:
            raise ValueError("Channel escapes bundle")
        for key in ("compressed_bytes", "uncompressed_bytes"):
            if not 0 < _integer(item[key], key) <= LIMIT:
                raise ValueError("Geometry channel exceeds diagnostic limit")
        for key in ("compressed_sha256", "uncompressed_sha256"):
            _digest(item[key])
        if (
            channel.stat().st_size != item["compressed_bytes"]
            or file_hash(channel) != item["compressed_sha256"]
        ):
            raise ValueError("Geometry channel compressed bytes mismatch")
        pins[str(channel)] = item["compressed_sha256"]
        channels[name] = (channel, dict(item))
    return _GeometrySource(path, doc, mid, exact_patch, build, duration, channels, pins)


class _GeometrySource:
    def __init__(self, path, doc, mid, patch, build, duration, channels, pins):
        self.match_id, self.patch, self.build, self.duration = mid, patch, build, duration
        self._path, self._doc, self._channels, self._pins = path, doc, channels, pins
        self._states = dict.fromkeys(channels, "pending")

    def rows(self, name):
        """Every selected stream must reach EOF before the report can be published."""
        if name not in self._states or self._states[name] != "pending":
            raise ValueError("Channel is unavailable or already opened")
        self._states[name] = "reading"
        path, ref = self._channels[name]
        return self._iterate(name, path, ref)

    def _iterate(self, name, path, ref):
        count, digest = 0, hashlib.sha256()
        first = True
        try:
            with gzip.open(path, "rb") as stream:
                while line := stream.readline(1024 * 1024 + 1):
                    count += len(line)
                    if len(line) > 1024 * 1024 or count > ref["uncompressed_bytes"]:
                        raise ValueError("Geometry channel exceeds declared size")
                    if not line.endswith(b"\n") or not line.strip():
                        raise ValueError("Invalid JSONL record")
                    digest.update(line)
                    row = parse_source_json(line)
                    if not isinstance(row, dict):
                        raise ValueError("Geometry state must be an object")
                    if first:
                        first = False
                        schema = (
                            "gem-state-capture/3" if name == "state" else "gem-extras-capture/1"
                        )
                        if (
                            row.get("schema") != schema
                            or row.get("match_id") != self.match_id
                            or row.get("seconds") != self.duration + 1
                            or row.get("window") != {"start": 0, "end_inclusive": self.duration}
                            or row.get("coordinates")
                            != "cell space (cell*128+vec), map centre 16384"
                            or row.get("omniscient") is not True
                        ):
                            raise ValueError("Invalid geometry channel header")
                        continue
                    yield row
            if first:
                raise ValueError("Missing geometry channel header")
            if (
                count != ref["uncompressed_bytes"]
                or digest.hexdigest() != ref["uncompressed_sha256"]
            ):
                raise ValueError("Geometry channel uncompressed bytes mismatch")
            self._states[name] = "complete"
        except BaseException:
            self._states[name] = "failed"
            raise

    def verify_again(self):
        if any(state != "complete" for state in self._states.values()):
            raise ValueError("Geometry channels must be consumed to EOF")
        if any(file_hash(Path(path)) != digest for path, digest in self._pins.items()):
            raise ValueError("Replay geometry source drift")
        return self.receipt()

    def receipt(self):
        return {
            "schema": "replay-geometry-source/1",
            "manifest": {"path": str(self._path), "sha256": self._pins[str(self._path)]},
            "match_id": self.match_id,
            "exact_patch": self.patch,
            "replay_build": self.build,
            "duration": self.duration,
            "used_files": dict(self._pins),
            "original_producer": self._doc["producer"],
            "channels": dict(self._states),
            "full_bundle_quality_revalidated": False,
            "training_allowed": False,
            "limits": (
                "Only pinned metadata/state/extras are checked; "
                "original producer is recorded, not re-certified."
            ),
        }


def read_landmark_capture(capture_ref, receipt_ref, *, replay_source):
    """Bind fresh landmark output to its receipt and the selected replay manifest."""
    for ref in (capture_ref, receipt_ref):
        if (
            not isinstance(ref, dict)
            or set(ref) != {"path", "sha256"}
            or not isinstance(ref["path"], str)
            or not Path(ref["path"]).is_absolute()
        ):
            raise ValueError("Invalid landmark reference")
    capture = _read(capture_ref["path"], capture_ref["sha256"])
    receipt = _read(receipt_ref["path"], receipt_ref["sha256"])
    if (
        capture.get("schema") != "map-landmark-capture/1"
        or receipt.get("schema") != "map-landmark-capture-receipt/1"
        or capture.get("coordinate_space") != "world"
        or capture.get("training_allowed") is not False
        or receipt.get("training_allowed") is not False
        or receipt.get("manifest") != replay_source.receipt()["manifest"]
        or receipt.get("output_sha256") != {"capture.json": capture_ref["sha256"]}
    ):
        raise ValueError("Landmark capture receipt/source mismatch")
    expected = {
        "match_id": replay_source.match_id,
        "patch": replay_source.patch,
        "game_build": replay_source.build,
    }
    if any(doc.get(key) != value for doc in (capture, receipt) for key, value in expected.items()):
        raise ValueError("Landmark capture identity mismatch")
    _integer(capture.get("post_game_tick"), "landmark post-game marker")
    if capture.get("parse_error") is not None or capture.get("truncated_at_tick") is not None:
        raise ValueError("Incomplete landmark capture")
    pins = receipt.get("used_files")
    if not isinstance(pins, dict) or not pins:
        raise ValueError("Landmark source inventory missing")
    for name, digest in pins.items():
        if not isinstance(name, str) or not Path(name).is_absolute():
            raise ValueError("Invalid landmark source path")
        if file_hash(Path(name)) != _digest(digest):
            raise ValueError("Landmark source/code drift")
    return capture
