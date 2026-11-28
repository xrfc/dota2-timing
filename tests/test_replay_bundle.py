"""Storage integrity is independent from semantic quality and training approval."""

import gzip
import hashlib
import json

import pytest

from dota_items.data import replay_bundle as bundle

IDENTITY = {"match_id": 9000000000, "patch": "7.42", "training_allowed": False}
PRODUCER = {"schema": "synthetic-producer/1", "sha256": "a" * 64}


def writer(root, **kwargs):
    return bundle.BundleWriter(root, identity=kwargs.get("identity", IDENTITY), producer=PRODUCER)


def saved(root):
    return json.loads((root / "manifest.json").read_text())


def replace_manifest(root, manifest):
    (root / "manifest.json").write_text(json.dumps(manifest))


def test_json_bytes_match_legacy_dump_and_gzip_is_reproducible(tmp_path):
    value = {"中文": [True, None, 1.25], "id": 9000000000}
    expected = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    descriptors = []
    packed = []
    for name in ("a", "b"):
        root = tmp_path / name
        out = writer(root)
        descriptor = out.add_json("raw", value)
        assert not (root / "manifest.json").exists()
        result = out.finish({"status": "synthetic_only"})
        assert result["identity"] == IDENTITY
        assert set(p.name for p in root.iterdir()) == {"raw.json.gz", "manifest.json"}
        assert gzip.decompress((root / descriptor["path"]).read_bytes()) == expected
        assert descriptor["uncompressed_sha256"] == hashlib.sha256(expected).hexdigest()
        assert bundle.read_json_artifact(root, "raw") == value
        assert (
            bundle.verify_bundle(root, expected_identity=IDENTITY, expected_producer=PRODUCER)
            == result
        )
        descriptors.append(descriptor)
        packed.append((root / descriptor["path"]).read_bytes())
    assert descriptors[0] == descriptors[1]
    assert packed[0] == packed[1]


def test_immutable_root_roles_files_and_finished_writer(tmp_path):
    root = tmp_path / "bundle"
    out = writer(root)
    with pytest.raises(FileExistsError):
        writer(root)
    descriptor = out.add_json("raw", {"x": 1}, filename="data/raw.json.gz")
    before = (root / descriptor["path"]).read_bytes()
    with pytest.raises(ValueError, match="role already"):
        out.add_json("raw", {"x": 2})
    with pytest.raises(ValueError, match="path already"):
        out.add_json("other", {}, filename="data/raw.json.gz")
    result = out.finish({})
    with pytest.raises(ValueError, match="closed"):
        out.add_json("more", {})
    with pytest.raises(ValueError, match="closed"):
        out.finish({})
    assert (root / descriptor["path"]).read_bytes() == before
    assert bundle.verify_bundle(root) == result


@pytest.mark.parametrize(
    "path",
    [
        "../outside.gz",
        "/tmp/out.gz",
        "x/../raw.gz",
        "x\\raw.gz",
        "./raw.gz",
        "x//raw.gz",
        "raw.json",
    ],
)
def test_artifact_paths_do_not_escape_or_alias(tmp_path, path):
    out = writer(tmp_path / "bundle")
    with pytest.raises(ValueError):
        out.add_json("raw", {}, filename=path)
    assert not (out.root / "manifest.json").exists()


@pytest.mark.parametrize("role", ["", ".", "..", "a/b", True, 3])
def test_roles_are_explicit_portable_identifiers(tmp_path, role):
    out = writer(tmp_path / "bundle")
    with pytest.raises(ValueError, match="role"):
        out.add_json(role, {})


def test_pack_files_is_lossless_keeps_original_and_records_references(tmp_path):
    source = tmp_path / "legacy.json"
    raw = b'{ "x": 1, "id": 9000000000 }\n'
    source.write_bytes(raw)
    reference = {
        "path": str(source),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }
    identity = {**IDENTITY, "source_references": [reference]}
    root = tmp_path / "bundle"
    result = bundle.pack_files(root, {"legacy": source}, identity, PRODUCER)
    assert source.read_bytes() == raw
    assert result["artifacts"]["legacy"]["source"] == reference
    assert bundle.read_json_artifact(root, "legacy") == {"x": 1, "id": 9000000000}
    assert result["quality"]["semantic_quality"] == "not_evaluated"
    source.write_bytes(b"bad")
    with pytest.raises(ValueError, match="reference size changed"):
        bundle.verify_bundle(root)
    assert bundle.verify_bundle(root, verify_references=False) == result
    assert bundle.read_json_artifact(root, "legacy")["x"] == 1


def test_identity_and_producer_require_exact_json_types_and_fields(tmp_path):
    root = tmp_path / "bundle"
    out = writer(root)
    out.add_json("x", {})
    out.finish({})
    with pytest.raises(ValueError, match="identity mismatch"):
        bundle.verify_bundle(root, expected_identity={**IDENTITY, "training_allowed": 0})
    with pytest.raises(ValueError, match="identity mismatch"):
        bundle.verify_bundle(root, expected_identity={"match_id": IDENTITY["match_id"]})
    with pytest.raises(ValueError, match="producer mismatch"):
        bundle.verify_bundle(root, expected_producer={**PRODUCER, "sha256": "b" * 64})


def test_streaming_channel_counts_and_bounded_reads(tmp_path):
    root = tmp_path / "bundle"
    out = writer(root)
    rows = ({"t": t, "heroes": [{"player_id": p} for p in range(10)]} for t in range(3))
    header = {"schema": "synthetic-channel/1", "seconds": 3, "match_id": 9000000000}
    descriptor = out.add_channel("state", header, rows)
    out.finish({"status": "not_semantically_evaluated"})
    values = list(bundle.iter_channel(root, "state"))
    assert values[0] == header
    assert [r["t"] for r in values[1:]] == [0, 1, 2]
    assert (
        list(bundle.iter_channel(root, "state", max_total_bytes=descriptor["uncompressed_bytes"]))
        == values
    )
    with pytest.raises(ValueError, match="Channel exceeds"):
        list(
            bundle.iter_channel(root, "state", max_total_bytes=descriptor["uncompressed_bytes"] - 1)
        )
    with pytest.raises(ValueError, match="line exceeds"):
        list(bundle.iter_channel(root, "state", max_line_bytes=5))
    with pytest.raises(ValueError, match="not a JSON document"):
        bundle.read_json_artifact(root, "state")


@pytest.mark.parametrize("count", [0, 2])
def test_channel_failure_never_publishes_manifest_or_partial_artifact(tmp_path, count):
    root = tmp_path / "bundle"
    out = writer(root)
    with pytest.raises(ValueError, match="rows"):
        out.add_channel("state", {"seconds": 1}, ({"t": n} for n in range(count)))
    assert not (root / "manifest.json").exists()
    assert not (root / "state.jsonl.gz").exists()
    with pytest.raises(ValueError, match="failed"):
        out.finish({})
    with pytest.raises((ValueError, FileNotFoundError)):
        bundle.verify_bundle(root)


def test_broken_generator_preserves_previous_artifact_but_prevents_completion(tmp_path):
    root = tmp_path / "bundle"
    out = writer(root)
    first = out.add_json("raw", {"a": 1})
    before = (root / first["path"]).read_bytes()

    def broken():
        yield {"t": 0}
        raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        out.add_channel("state", {"seconds": 2}, broken())
    assert (root / first["path"]).read_bytes() == before
    assert not (root / "manifest.json").exists()
    assert not list(root.glob(".bundle-*"))
    with pytest.raises(ValueError, match="failed"):
        out.finish({})


@pytest.mark.parametrize(
    "value", [{"x": float("nan")}, {"x": float("inf")}, {1: "coercion"}, {"x": (1, 2)}]
)
def test_json_does_not_coerce_keys_or_nonfinite_values(tmp_path, value):
    out = writer(tmp_path / "bundle")
    with pytest.raises(ValueError):
        out.add_json("raw", value)
    assert not list(out.root.iterdir())


def test_source_modified_during_compression_cannot_be_accepted(tmp_path, monkeypatch):
    source = tmp_path / "input.json"
    source.write_bytes(b'{"x":1}')
    out = writer(tmp_path / "bundle")
    original = out._write

    def mutate_after_write(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_bytes(b'{"x":2}')
        return result

    monkeypatch.setattr(out, "_write", mutate_after_write)
    with pytest.raises(ValueError, match="Source changed"):
        out.add_file("raw", source)
    with pytest.raises(ValueError, match="failed"):
        out.finish({})
    assert not (out.root / "manifest.json").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "payload",
        "compressed_hash",
        "uncompressed_hash",
        "size",
        "unknown",
        "missing",
        "extra",
        "duplicate_json_key",
    ],
)
def test_tampered_or_incomplete_bundle_is_never_reused(tmp_path, damage):
    root = tmp_path / "bundle"
    out = writer(root)
    descriptor = out.add_json("raw", {"a": [1, 2]})
    out.finish({})
    manifest = saved(root)
    path = root / descriptor["path"]
    if damage == "payload":
        path.write_bytes(path.read_bytes()[:-5])
    elif damage == "compressed_hash":
        manifest["artifacts"]["raw"]["compressed_sha256"] = "0" * 64
    elif damage == "uncompressed_hash":
        manifest["artifacts"]["raw"]["uncompressed_sha256"] = "0" * 64
    elif damage == "size":
        manifest["artifacts"]["raw"]["uncompressed_bytes"] = 1
    elif damage == "unknown":
        manifest["unexpected"] = True
    elif damage == "missing":
        path.unlink()
    elif damage == "extra":
        (root / "stray.txt").write_text("unlisted")
    if damage == "duplicate_json_key":
        (root / "manifest.json").write_text(
            json.dumps(manifest)[:-1] + ', "schema": "replay-bundle/1"}'
        )
    else:
        replace_manifest(root, manifest)
    with pytest.raises((ValueError, FileNotFoundError)):
        bundle.verify_bundle(root)


def test_symlink_artifacts_and_reference_sources_are_rejected(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("{}")
    linked = tmp_path / "link.json"
    linked.symlink_to(source)
    out = writer(tmp_path / "bundle")
    with pytest.raises(ValueError, match="non-regular"):
        out.add_file("raw", linked)
    descriptor = out.add_json("raw", {})
    out.finish({})
    artifact = out.root / descriptor["path"]
    copy = tmp_path / "copy.gz"
    artifact.rename(copy)
    artifact.symlink_to(copy)
    with pytest.raises(ValueError, match="symlinks"):
        bundle.verify_bundle(out.root)


def test_json_read_limit_and_unknown_role(tmp_path):
    out = writer(tmp_path / "bundle")
    descriptor = out.add_json("raw", {"x": "longer text"})
    out.finish({})
    assert (
        bundle.read_json_artifact(out.root, "raw", descriptor["uncompressed_bytes"])["x"]
        == "longer text"
    )
    with pytest.raises(ValueError, match="read limit"):
        bundle.read_json_artifact(out.root, "raw", descriptor["uncompressed_bytes"] - 1)
    with pytest.raises(ValueError, match="Unknown artifact"):
        bundle.read_json_artifact(out.root, "missing")
    with pytest.raises(ValueError, match="nonnegative"):
        bundle.read_json_artifact(out.root, "raw", True)


def test_streamed_write_enforces_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "MAX_ARTIFACT_BYTES", 8)
    out = writer(tmp_path / "bundle")
    with pytest.raises(ValueError, match="size limit"):
        out.add_json("raw", {"x": "too many bytes"})
    assert not (out.root / "raw.json.gz").exists()
    assert not (out.root / "manifest.json").exists()


def test_atomic_publish_race_does_not_replace_a_winner(tmp_path, monkeypatch):
    out = writer(tmp_path / "bundle")
    link = bundle.os.link

    def occupied(temporary, target):
        target.write_bytes(b"another writer won")
        link(temporary, target)

    monkeypatch.setattr(bundle.os, "link", occupied)
    with pytest.raises(FileExistsError):
        out.add_json("raw", {"x": 1})
    assert (out.root / "raw.json.gz").read_bytes() == b"another writer won"
    assert not (out.root / "manifest.json").exists()
    assert not list(out.root.glob(".bundle-*"))


def test_truncated_gzip_rejected_even_when_compressed_descriptor_was_updated(tmp_path):
    out = writer(tmp_path / "bundle")
    descriptor = out.add_json("raw", {"x": list(range(10))})
    out.finish({})
    path = out.root / descriptor["path"]
    truncated = path.read_bytes()[:-5]
    path.write_bytes(truncated)
    manifest = saved(out.root)
    manifest["artifacts"]["raw"].update(
        compressed_bytes=len(truncated), compressed_sha256=hashlib.sha256(truncated).hexdigest()
    )
    replace_manifest(out.root, manifest)
    with pytest.raises(ValueError, match="incomplete gzip"):
        bundle.verify_bundle(out.root)


def test_requested_read_bound_is_checked_before_decompression(tmp_path, monkeypatch):
    out = writer(tmp_path / "bundle")
    descriptor = out.add_json("raw", {"x": "longer text"})
    out.finish({})

    def no_gzip(*args, **kwargs):
        raise AssertionError("must reject before decompression")

    monkeypatch.setattr(bundle.gzip, "open", no_gzip)
    with pytest.raises(ValueError, match="read limit"):
        bundle.read_json_artifact(out.root, "raw", descriptor["uncompressed_bytes"] - 1)


def test_tiny_tokens_and_large_chunks_produce_identical_gzip_bytes(tmp_path, monkeypatch):
    payload = b'{"value":"' + b"abc123" * 40000 + b'"}'
    original = bundle.gzip.GzipFile.write
    writes = []

    def observed(stream, value):
        writes.append(len(value))
        return original(stream, value)

    tiny = writer(tmp_path / "tiny")
    with monkeypatch.context() as context:
        context.setattr(bundle.gzip.GzipFile, "write", observed)
        tiny_descriptor = tiny._write(
            "raw",
            (payload[index : index + 1] for index in range(len(payload))),
            filename=None,
            kind="json",
        )
    tiny.finish({})
    large = writer(tmp_path / "large")
    large_descriptor = large._write("raw", iter([payload]), filename=None, kind="json")
    large.finish({})
    assert tiny_descriptor == large_descriptor
    assert (tiny.root / tiny_descriptor["path"]).read_bytes() == (
        large.root / large_descriptor["path"]
    ).read_bytes()
    assert tiny_descriptor["uncompressed_sha256"] == hashlib.sha256(payload).hexdigest()
    assert max(writes) <= bundle.WRITE_BUFFER_BYTES
    assert len(writes) < 10


def test_large_chunk_bypasses_bounded_pending_buffer_without_changing_bytes(tmp_path, monkeypatch):
    chunks = [b"prefix", b"x" * (bundle.WRITE_BUFFER_BYTES * 3), b"suffix"]
    expected = b"".join(chunks)
    writes = []
    original = bundle.gzip.GzipFile.write

    def observed(stream, value):
        writes.append(len(value))
        return original(stream, value)

    out = writer(tmp_path / "bundle")
    with monkeypatch.context() as context:
        context.setattr(bundle.gzip.GzipFile, "write", observed)
        descriptor = out._write("raw", iter(chunks), filename=None, kind="bytes")
    out.finish({})
    assert max(writes) == len(chunks[1])
    assert descriptor["uncompressed_sha256"] == hashlib.sha256(expected).hexdigest()
    assert gzip.decompress((out.root / descriptor["path"]).read_bytes()) == expected
