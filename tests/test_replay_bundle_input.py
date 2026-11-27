"""Downstream input admission must keep version, byte and read-session boundaries."""

import copy
import hashlib
import json
import os

import pytest
from test_replay_bundle_quality import MID, PRODUCER, make_bundle, save_manifest

from dota_items.data import replay_bundle_input as inputs
from dota_items.data.replay_bundle import pack_files


def pinned(root, *, patch="7.41f", mid=MID):
    return {
        "schema": inputs.REFERENCE_SCHEMA,
        "match_id": mid,
        "patch": patch,
        "bundle": str(root.absolute()),
        "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "training_allowed": False,
    }


def fixture(tmp_path, **kwargs):
    root, manifest = make_bundle(tmp_path, **kwargs)
    manifest["identity"]["patch_window"] = {"patch": "7.41f"}
    save_manifest(root, manifest)
    return root, manifest, pinned(root)


def open_input(reference, **kwargs):
    options = {
        "match_id": MID,
        "allowed_patches": ("7.41f",),
        "expected_producer": PRODUCER,
        "match_allowed": lambda _: True,
    }
    return inputs.open_bundle_input(reference, **(options | kwargs))


def no_reads(*args, **kwargs):
    pytest.fail("Rejected input must not open bundle files")


def file_inventory(root):
    return {
        str(path.relative_to(root)): (
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def test_complete_input_reads_existing_gzip_without_writing_copies(tmp_path):
    root, manifest, expected = fixture(tmp_path)
    before = file_inventory(tmp_path)
    actual = inputs.create_reference(
        root, match_id=MID, expected_producer=PRODUCER, match_allowed=lambda _: True
    )
    assert actual == expected
    source = open_input(actual)
    assert source.normalized()["match_id"] == MID
    assert source.metadata()["match_id"] == MID
    assert [row["t"] for row in source.rows("state")] == [0, 1, 2]
    assert [row["t"] for row in source.rows("extras")] == [0, 1, 2]
    receipt = source.verify()
    assert receipt == source.receipt()
    assert receipt["reference"] == expected
    assert receipt["producer"] == manifest["producer"]
    assert receipt["patch_window"] == {"patch": "7.41f"}
    assert receipt["game_build"] == 6993 and receipt["duration"] == 2
    assert receipt["training_allowed"] is False and receipt["omniscient"] is True
    assert file_inventory(tmp_path) == before


@pytest.mark.parametrize("allowed", [False, 1, None])
def test_reserved_policy_rejects_before_reference_or_bundle_access(tmp_path, monkeypatch, allowed):
    monkeypatch.setattr(inputs, "read_source_bytes", no_reads)
    with pytest.raises(ValueError, match="Reserved"):
        open_input(None, match_allowed=lambda _: allowed)
    with pytest.raises(ValueError, match="Reserved"):
        inputs.create_reference(
            tmp_path / "absent",
            match_id=MID,
            expected_producer=PRODUCER,
            match_allowed=lambda _: allowed,
        )


@pytest.mark.parametrize("mid", [True, 0, -1, str(MID)])
def test_invalid_requested_id_does_not_open_a_bundle(tmp_path, monkeypatch, mid):
    monkeypatch.setattr(inputs, "read_source_bytes", no_reads)
    with pytest.raises(ValueError, match="positive integer"):
        open_input(None, match_id=mid)


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"match_id": MID + 1}, "Requested match"),
        ({"allowed_patches": ("7.42",)}, "unsupported"),
        ({"allowed_patches": "7.41f"}, "explicit supported"),
        ({"allowed_patches": ()}, "explicit supported"),
        ({"expected_producer": None}, "Expected producer"),
    ],
)
def test_request_policy_rejects_before_any_bundle_read(tmp_path, monkeypatch, overrides, reason):
    _, _, reference = fixture(tmp_path)
    monkeypatch.setattr(inputs, "read_source_bytes", no_reads)
    with pytest.raises(ValueError, match=reason):
        open_input(reference, **overrides)


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "replay-bundle-reference/unknown"},
        {"match_id": True},
        {"patch": "latest"},
        {"bundle": "relative/path"},
        {"manifest_sha256": "not-a-digest"},
        {"training_allowed": True},
        {"extra": "unrecognized"},
    ],
)
def test_reference_shape_is_explicit_and_cannot_grant_training(tmp_path, change):
    _, _, reference = fixture(tmp_path)
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference | change), encoding="utf-8")
    with pytest.raises(ValueError):
        inputs.load_reference(path)


def test_reference_roundtrip_and_receipts_do_not_alias_caller_state(tmp_path):
    _, _, reference = fixture(tmp_path)
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference), encoding="utf-8")
    loaded = inputs.load_reference(path)
    producer = copy.deepcopy(PRODUCER)
    source = open_input(loaded, expected_producer=producer)
    loaded["manifest_sha256"] = "0" * 64
    producer["schema"] = "changed"
    receipt = source.receipt()
    receipt["reference"]["match_id"] = 1
    receipt["producer"]["schema"] = "changed"
    assert source.verify()["reference"] == reference
    assert source.receipt()["producer"] == PRODUCER


def test_reference_pins_exact_manifest_bytes_even_when_json_is_equivalent(tmp_path):
    root, _, reference = fixture(tmp_path)
    path = root / "manifest.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Pinned manifest changed"):
        open_input(reference)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("match_id", MID + 1, "match identity"),
        ("match_id", True, "match identity"),
        ("patch_window", {"patch": "7.42"}, "patch identity"),
    ],
)
def test_repinned_manifest_cannot_override_reference_identity(tmp_path, field, value, reason):
    root, manifest, _ = fixture(tmp_path)
    manifest["identity"][field] = value
    save_manifest(root, manifest)
    with pytest.raises(ValueError, match=reason):
        open_input(pinned(root))


def test_old_producer_is_rejected_even_with_valid_reference_and_bytes(tmp_path):
    root, _, reference = fixture(tmp_path)
    wrong = {"schema": "old-producer/1"}
    with pytest.raises(ValueError, match="producer mismatch"):
        open_input(reference, expected_producer=wrong)
    with pytest.raises(ValueError, match="producer mismatch"):
        inputs.create_reference(
            root, match_id=MID, expected_producer=wrong, match_allowed=lambda _: True
        )


def test_review_required_cannot_become_a_consumer_input(tmp_path):
    root, _, reference = fixture(
        tmp_path, state_change=lambda rows: rows[1]["heroes"][0].update(hp=None)
    )
    with pytest.raises(ValueError, match="quality is not passed"):
        open_input(reference)
    with pytest.raises(ValueError, match="quality is not passed"):
        inputs.create_reference(
            root, match_id=MID, expected_producer=PRODUCER, match_allowed=lambda _: True
        )


def test_lossless_archive_is_not_a_quality_approved_replay(tmp_path):
    raw = tmp_path / "source.json"
    raw.write_text('{"match_id": 9103408009}', encoding="utf-8")
    root = tmp_path / "archive"
    pack_files(
        root,
        {"raw": raw},
        {"match_id": MID, "patch_window": {"patch": "7.41f"}, "training_allowed": False},
        PRODUCER,
    )
    with pytest.raises(ValueError, match="exactly raw/normalized/state/extras"):
        open_input(pinned(root))


@pytest.mark.parametrize("role", ["raw", "normalized", "state", "extras"])
def test_corrupted_artifact_cannot_be_opened_as_a_verified_input(tmp_path, role):
    root, manifest, reference = fixture(tmp_path)
    path = root / manifest["artifacts"][role]["path"]
    value = bytearray(path.read_bytes())
    value[-1] ^= 1
    path.write_bytes(value)
    with pytest.raises(ValueError, match="Compressed digest"):
        open_input(reference)


@pytest.mark.parametrize("stop", ["not_started", "first_row", "last_row"])
def test_partial_iterator_must_not_authorize_report_publication(tmp_path, stop):
    _, _, reference = fixture(tmp_path)
    source = open_input(reference)
    rows = source.rows("state")
    if stop == "first_row":
        assert next(rows)["t"] == 0
    elif stop == "last_row":
        assert [next(rows)["t"] for _ in range(3)] == [0, 1, 2]
    with pytest.raises(ValueError, match="not fully consumed"):
        source.verify()
    rows.close()
    with pytest.raises(ValueError, match="not fully consumed"):
        source.verify()


def test_every_opened_channel_must_be_exhausted(tmp_path):
    _, _, reference = fixture(tmp_path)
    source = open_input(reference)
    state, extras = source.rows("state"), source.rows("extras")
    assert len(list(state)) == 3
    with pytest.raises(ValueError, match="not fully consumed"):
        source.verify()
    assert len(list(extras)) == 3
    assert source.verify()["duration"] == 2


def test_manifest_change_during_normalized_read_is_detected(tmp_path, monkeypatch):
    root, _, reference = fixture(tmp_path)
    source = open_input(reference)
    original = inputs.read_json_artifact

    def change_after_read(*args, **kwargs):
        value = original(*args, **kwargs)
        path = root / "manifest.json"
        path.write_bytes(path.read_bytes() + b"\n")
        return value

    monkeypatch.setattr(inputs, "read_json_artifact", change_after_read)
    with pytest.raises(ValueError, match="Pinned manifest changed"):
        source.normalized()


def test_manifest_change_during_channel_iteration_is_detected(tmp_path):
    root, _, reference = fixture(tmp_path)
    source = open_input(reference)
    rows = source.rows("state")
    assert next(rows)["t"] == 0
    path = root / "manifest.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Pinned manifest changed"):
        list(rows)
    with pytest.raises(ValueError):
        source.verify()


def test_source_change_with_same_size_and_mtime_still_blocks_publication(tmp_path):
    _, _, reference = fixture(tmp_path)
    source = open_input(reference)
    assert len(list(source.rows("state"))) == 3
    path = tmp_path / "m.dem"
    stat = path.stat()
    raw = path.read_bytes()
    path.write_bytes(b"X" + raw[1:])
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert path.stat().st_size == stat.st_size and path.stat().st_mtime_ns == stat.st_mtime_ns
    with pytest.raises(ValueError, match="reference"):
        source.verify()


def test_metadata_change_is_rejected_when_consumer_reads_it(tmp_path):
    _, _, reference = fixture(tmp_path)
    source = open_input(reference)
    path = tmp_path / "meta.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Metadata changed"):
        source.metadata()


def test_post_read_artifact_change_is_rejected_by_final_verification(tmp_path):
    root, manifest, reference = fixture(tmp_path)
    source = open_input(reference)
    assert len(list(source.rows("extras"))) == 3
    path = root / manifest["artifacts"]["extras"]["path"]
    path.write_bytes(path.read_bytes() + b"extra")
    with pytest.raises(ValueError, match="Compressed size"):
        source.verify()


@pytest.mark.parametrize(
    "manifest",
    [
        None,
        [],
        {"identity": None},
        {"identity": []},
        {"identity": {"patch_window": None}},
        {"identity": {"patch_window": []}},
    ],
)
def test_reference_creation_rejects_malformed_manifest_shape_before_quality(
    tmp_path, monkeypatch, manifest
):
    root = tmp_path / "malformed"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(inputs, "verify_quality_bundle", no_reads)
    with pytest.raises(ValueError):
        inputs.create_reference(
            root, match_id=MID, expected_producer=PRODUCER, match_allowed=lambda _: True
        )
