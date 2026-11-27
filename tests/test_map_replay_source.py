import gzip
import hashlib
import json

import pytest

from dota_items.data.map_replay_source import open_geometry_source
from dota_items.storage import file_hash


def source_fixture(tmp_path):
    def channel(name, filename):
        header = {
            "schema": "gem-state-capture/3" if name == "state" else "gem-extras-capture/1",
            "match_id": 123,
            "seconds": 2,
            "window": {"start": 0, "end_inclusive": 1},
            "coordinates": "cell space (cell*128+vec), map centre 16384",
            "omniscient": True,
        }
        raw = json.dumps(header).encode() + b'\n{"t": 0}\n{"t": 1}\n'
        path = tmp_path / filename
        path.write_bytes(gzip.compress(raw, mtime=0))
        return {
            "codec": "gzip",
            "format": "jsonl",
            "path": filename,
            "compressed_bytes": path.stat().st_size,
            "compressed_sha256": file_hash(path),
            "uncompressed_bytes": len(raw),
            "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        }

    meta = tmp_path / "123.json"
    meta.write_text(json.dumps({"match_id": 123, "duration": 1, "start_time": 100, "patch": 61}))
    doc = {
        "schema": "replay-bundle/1",
        "identity": {
            "match_id": 123,
            "training_allowed": False,
            "patch_window": {"patch": "7.42", "release_timestamp": 90, "upper_exclusive": 110},
            "expected_patch_code": 61,
            "discovery": {"match_id": 123, "start_time": 100},
            "source_references": [{"path": str(meta), "sha256": file_hash(meta)}],
        },
        "quality": {
            "status": "passed",
            "parser": {
                "match_id": 123,
                "game_build": 6993,
                "parse_error": None,
                "truncated_at_tick": None,
            },
            "base": {"observed_build": 6993, "metadata_duration": 1, "normalized_duration": 1},
        },
        "producer": {"original": "explicitly not certified"},
        "artifacts": {
            name: channel(name, filename)
            for name, filename in (("state", "state-v3.jsonl.gz"), ("extras", "extras-v1.jsonl.gz"))
        },
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(doc))
    return manifest, doc


def open_source(path, **kwargs):
    return open_geometry_source(
        path,
        expected_sha256=file_hash(path),
        exact_patch="7.42",
        match_allowed=lambda _: True,
        **kwargs,
    )


def test_consumed_geometry_has_a_narrow_receipt(tmp_path):
    path, _ = source_fixture(tmp_path)
    source = open_source(path)
    assert source.build == 6993
    assert list(source.rows("state")) == [{"t": 0}, {"t": 1}]
    list(source.rows("extras"))
    receipt = source.verify_again()
    assert receipt["full_bundle_quality_revalidated"] is False
    assert receipt["training_allowed"] is False
    assert set(receipt["channels"].values()) == {"complete"}


def test_holdout_rejected_before_metadata_or_channels(tmp_path):
    path, _ = source_fixture(tmp_path)
    (tmp_path / "123.json").unlink()
    with pytest.raises(ValueError, match="excluded"):
        open_geometry_source(
            path, expected_sha256=file_hash(path), exact_patch="7.42", match_allowed=lambda _: False
        )


def test_letter_patch_does_not_inherit(tmp_path):
    path, _ = source_fixture(tmp_path)
    with pytest.raises(ValueError, match="Exact replay patch"):
        open_geometry_source(
            path, expected_sha256=file_hash(path), exact_patch="7.42a", match_allowed=lambda _: True
        )


@pytest.mark.parametrize("state", ["unstarted", "partial", "closed"])
def test_stream_must_be_exhausted(tmp_path, state):
    path, _ = source_fixture(tmp_path)
    source = open_source(path)
    stream = source.rows("state")
    if state != "unstarted":
        next(stream)
    if state == "closed":
        stream.close()
    list(source.rows("extras"))
    with pytest.raises(ValueError, match="EOF"):
        source.verify_again()


def test_uncompressed_digest_checked_at_eof(tmp_path):
    path, doc = source_fixture(tmp_path)
    doc["artifacts"]["state"]["uncompressed_sha256"] = "0" * 64
    path.write_text(json.dumps(doc))
    source = open_source(path)
    with pytest.raises(ValueError, match="uncompressed bytes"):
        list(source.rows("state"))
    with pytest.raises(ValueError, match="EOF"):
        source.verify_again()


def test_crc_corruption_is_not_silently_accepted(tmp_path):
    path, doc = source_fixture(tmp_path)
    state = tmp_path / "state-v3.jsonl.gz"
    raw = bytearray(state.read_bytes())
    raw[-8] ^= 1
    state.write_bytes(raw)
    doc["artifacts"]["state"]["compressed_sha256"] = file_hash(state)
    path.write_text(json.dumps(doc))
    source = open_source(path)
    with pytest.raises(gzip.BadGzipFile):
        list(source.rows("state"))
    with pytest.raises(ValueError, match="EOF"):
        source.verify_again()


def test_source_drift_after_consumption(tmp_path):
    path, _ = source_fixture(tmp_path)
    source = open_source(path)
    list(source.rows("state"))
    list(source.rows("extras"))
    (tmp_path / "123.json").write_text("{}")
    with pytest.raises(ValueError, match="drift"):
        source.verify_again()


@pytest.mark.parametrize("mutation", ["build", "id", "duration", "path", "metadata_patch"])
def test_identity_and_path_mismatches_fail(tmp_path, mutation):
    path, doc = source_fixture(tmp_path)
    if mutation == "build":
        doc["quality"]["base"]["observed_build"] = 6989
    elif mutation == "id":
        doc["quality"]["parser"]["match_id"] = 124
    elif mutation == "duration":
        doc["quality"]["base"]["normalized_duration"] = 2
    elif mutation == "path":
        doc["artifacts"]["state"]["path"] = "../state-v3.jsonl.gz"
    elif mutation == "metadata_patch":
        meta = tmp_path / "123.json"
        obj = json.loads(meta.read_text())
        obj["patch"] = 60
        meta.write_text(json.dumps(obj))
        doc["identity"]["source_references"][0]["sha256"] = file_hash(meta)
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        open_source(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("match_id", 124),
        ("window", {"start": -1, "end_inclusive": 1}),
        ("schema", "gem-state-capture/2"),
        ("seconds", 3),
        ("coordinates", "world"),
        ("omniscient", False),
    ],
)
def test_header_identity_and_coordinate_contract(tmp_path, field, value):
    path, doc = source_fixture(tmp_path)
    target = tmp_path / "state-v3.jsonl.gz"
    lines = gzip.decompress(target.read_bytes()).splitlines(keepends=True)
    header = json.loads(lines[0])
    header[field] = value
    raw = json.dumps(header).encode() + b"\n" + b"".join(lines[1:])
    target.write_bytes(gzip.compress(raw, mtime=0))
    ref = doc["artifacts"]["state"]
    ref.update(
        compressed_bytes=target.stat().st_size,
        compressed_sha256=file_hash(target),
        uncompressed_bytes=len(raw),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
    )
    path.write_text(json.dumps(doc))
    source = open_source(path)
    with pytest.raises(ValueError, match="header"):
        list(source.rows("state"))


def landmark_fixture(tmp_path):
    path, _ = source_fixture(tmp_path)
    source = open_source(path)
    capture = {
        "schema": "map-landmark-capture/1",
        "coordinate_space": "world",
        "training_allowed": False,
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "post_game_tick": 100,
        "parse_error": None,
        "truncated_at_tick": None,
    }
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(capture))
    ref = {"path": str(capture_path), "sha256": file_hash(capture_path)}
    receipt = {
        "schema": "map-landmark-capture-receipt/1",
        "training_allowed": False,
        "manifest": source.receipt()["manifest"],
        "output_sha256": {"capture.json": ref["sha256"]},
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "used_files": source.receipt()["used_files"],
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    receipt_ref = {"path": str(receipt_path), "sha256": file_hash(receipt_path)}
    return source, ref, receipt_ref


def test_landmarks_bind_to_replay_and_output_receipt(tmp_path):
    from dota_items.data.map_replay_source import read_landmark_capture

    source, capture, receipt = landmark_fixture(tmp_path)
    assert read_landmark_capture(capture, receipt, replay_source=source)["game_build"] == 6993


@pytest.mark.parametrize(
    "mutation",
    ["different_manifest", "different_output", "different_build", "no_inventory", "drift"],
)
def test_landmarks_cannot_substitute_another_capture(tmp_path, mutation):
    from pathlib import Path

    from dota_items.data.map_replay_source import read_landmark_capture

    source, capture, receipt = landmark_fixture(tmp_path)
    path = Path(receipt["path"])
    doc = json.loads(path.read_text())
    if mutation == "different_manifest":
        doc["manifest"]["sha256"] = "0" * 64
    elif mutation == "different_output":
        doc["output_sha256"]["capture.json"] = "0" * 64
    elif mutation == "different_build":
        doc["game_build"] = 6989
    elif mutation == "no_inventory":
        doc["used_files"] = {}
    elif mutation == "drift":
        (tmp_path / "123.json").write_text("{}")
    path.write_text(json.dumps(doc))
    receipt["sha256"] = file_hash(path)
    with pytest.raises(ValueError):
        read_landmark_capture(capture, receipt, replay_source=source)
