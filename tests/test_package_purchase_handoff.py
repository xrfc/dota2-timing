import importlib.util
from pathlib import Path

import pytest

from dota_items.data.cohort_handoff import verify_bundle
from dota_items.storage import file_hash, json_bytes

spec = importlib.util.spec_from_file_location(
    "package_handoff", Path(__file__).parents[1] / "scripts/package_purchase_handoff.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs(tmp_path, monkeypatch):
    summary, snapshot, audit, interface = [
        tmp_path / n for n in ("summary.json", "snapshot.json", "audit.json", "interface.md")
    ]
    summary.write_bytes(json_bytes({"schema_version": "purchase-collection-summary/1"}))
    snapshot.write_bytes(json_bytes(module.synthetic_example()))
    interface.write_text("Synthetic test interface")
    audit.write_bytes(
        json_bytes(
            {
                "schema_version": "purchase-cohort-audit/1",
                "training_allowed": False,
                "new_split_assigned": False,
                "old_split_changed": False,
                "evidence_sha256": {str(p): file_hash(p) for p in (summary, snapshot)},
            }
        )
    )
    calls = []
    monkeypatch.setattr(module, "verify_snapshot", lambda *args: calls.append(args))
    return (summary, snapshot, audit, interface), calls


def test_package_copies_bytes_and_preserves_masks(tmp_path, monkeypatch):
    args, calls = inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle"
    manifest = module.package(*args, out)
    assert len(calls) == 1
    assert (out / "snapshot.json").read_bytes() == args[1].read_bytes()
    assert len(manifest["files"]) == 5
    snapshot = verify_bundle(out)
    row = snapshot["samples"][0]
    assert len(row["encoded_features"]) == len(snapshot["preprocessing"]["columns"]) == 22
    assert row["labels"][2] is None and row["label_mask"][2] is False
    assert not manifest["new_snapshot_created"]
    before = file_hash(out / "manifest.json")
    with pytest.raises(FileExistsError):
        module.package(*args, out)
    assert file_hash(out / "manifest.json") == before


def test_tampered_evidence_fails_before_output(tmp_path, monkeypatch):
    args, _ = inputs(tmp_path, monkeypatch)
    args[0].write_text('{"changed":true}')
    out = tmp_path / "bundle"
    with pytest.raises(ValueError, match="Hash mismatch"):
        module.package(*args, out)
    assert not out.exists()


def test_reconstruction_failure_fails_before_output(tmp_path, monkeypatch):
    args, _ = inputs(tmp_path, monkeypatch)

    def reject(*args):
        raise ValueError("reconstruction")

    monkeypatch.setattr(module, "verify_snapshot", reject)
    out = tmp_path / "bundle"
    with pytest.raises(ValueError, match="reconstruction"):
        module.package(*args, out)
    assert not out.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling_symlink"])
def test_refuses_any_existing_output_before_reconstruction(tmp_path, monkeypatch, kind):
    args, calls = inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle"
    if kind == "file":
        out.write_text("keep original")
    elif kind == "directory":
        out.mkdir()
        (out / "sentinel").write_text("keep original")
    else:
        target = tmp_path / "target"
        if kind == "symlink":
            target.mkdir()
        out.symlink_to(target, target_is_directory=True)
    with pytest.raises(FileExistsError):
        module.package(*args, out)
    assert calls == []
    if kind == "file":
        assert out.read_text() == "keep original"
    elif kind == "directory":
        assert (out / "sentinel").read_text() == "keep original"
    else:
        assert out.is_symlink()


@pytest.mark.parametrize("index", [0, 1])
def test_wrong_source_schema_fails_before_output(tmp_path, monkeypatch, index):
    args, _ = inputs(tmp_path, monkeypatch)
    args[index].write_bytes(json_bytes({"schema_version": "unsupported"}))
    report = module.load_handoff_json(args[2].read_bytes())
    report["evidence_sha256"][str(args[index])] = file_hash(args[index])
    args[2].write_bytes(json_bytes(report))
    out = tmp_path / "bundle"
    with pytest.raises(ValueError, match="Unsupported payload schema"):
        module.package(*args, out)
    assert not out.exists()


@pytest.mark.parametrize("value", [None, [], {}])
def test_missing_or_incomplete_audit_evidence_fails_before_output(tmp_path, monkeypatch, value):
    args, _ = inputs(tmp_path, monkeypatch)
    report = module.load_handoff_json(args[2].read_bytes())
    report["evidence_sha256"] = value
    args[2].write_bytes(json_bytes(report))
    out = tmp_path / "bundle"
    with pytest.raises(ValueError):
        module.package(*args, out)
    assert not out.exists()


def test_duplicate_audit_keys_fail_before_output(tmp_path, monkeypatch):
    args, _ = inputs(tmp_path, monkeypatch)
    raw = (
        args[2]
        .read_text()
        .replace('"evidence_sha256": {', '"evidence_sha256": {}, "evidence_sha256": {', 1)
    )
    args[2].write_text(raw)
    out = tmp_path / "bundle"
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        module.package(*args, out)
    assert not out.exists()


@pytest.mark.parametrize("index", [0, 1])
def test_source_change_during_reconstruction_is_not_packaged(tmp_path, monkeypatch, index):
    args, _ = inputs(tmp_path, monkeypatch)

    def reconstruct(*unused):
        args[index].write_text('{"changed":true}')

    monkeypatch.setattr(module, "verify_snapshot", reconstruct)
    out = tmp_path / "bundle"
    with pytest.raises(ValueError, match="Source changed during reconstruction"):
        module.package(*args, out)
    assert not out.exists()


def test_write_failure_leaves_no_completion_marker_and_refuses_retry(tmp_path, monkeypatch):
    args, _ = inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle"
    original_open = Path.open

    def fail_write(path, mode="r", *extra, **kwargs):
        if path == out / "summary.json" and mode == "xb":
            raise OSError("synthetic disk full")
        return original_open(path, mode, *extra, **kwargs)

    monkeypatch.setattr(Path, "open", fail_write)
    with pytest.raises(OSError, match="synthetic disk full"):
        module.package(*args, out)
    assert (out / "snapshot.json").exists()
    assert not (out / "manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        verify_bundle(out)
    with pytest.raises(FileExistsError):
        module.package(*args, out)


def test_corrupted_written_payload_is_not_published(tmp_path, monkeypatch):
    args, _ = inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle"
    original_read = Path.read_bytes

    def corrupt(path):
        if path == out / "snapshot.json":
            path.write_text('{"corrupted":true}')
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", corrupt)
    with pytest.raises(ValueError, match="Hash mismatch"):
        module.package(*args, out)
    assert not (out / "manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        verify_bundle(out)


def test_manifest_write_failure_is_not_a_complete_bundle(tmp_path, monkeypatch):
    args, _ = inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle"
    original_open = Path.open

    def fail_write(path, mode="r", *extra, **kwargs):
        if path == out / "manifest.json" and mode == "xb":
            raise OSError("synthetic manifest write failure")
        return original_open(path, mode, *extra, **kwargs)

    monkeypatch.setattr(Path, "open", fail_write)
    with pytest.raises(OSError, match="synthetic manifest write failure"):
        module.package(*args, out)
    assert len(list(out.iterdir())) == 5
    with pytest.raises(FileNotFoundError):
        verify_bundle(out)


def test_partial_manifest_write_cannot_be_read_as_complete(tmp_path, monkeypatch):
    args, _ = inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle"
    original_open = Path.open

    class InterruptedManifest:
        def __enter__(self):
            self.stream = original_open(out / "manifest.json", "xb")
            return self

        def write(self, contents):
            self.stream.write(contents[:20])
            raise OSError("synthetic interrupted manifest")

        def __exit__(self, *unused):
            self.stream.close()

    def partial_write(path, mode="r", *extra, **kwargs):
        if path == out / "manifest.json" and mode == "xb":
            return InterruptedManifest()
        return original_open(path, mode, *extra, **kwargs)

    monkeypatch.setattr(Path, "open", partial_write)
    with pytest.raises(OSError, match="synthetic interrupted manifest"):
        module.package(*args, out)
    assert (out / "manifest.json").stat().st_size == 20
    with pytest.raises(ValueError):
        verify_bundle(out)
    with pytest.raises(FileExistsError):
        module.package(*args, out)


def test_stale_producer_evidence_is_not_ignored(tmp_path, monkeypatch):
    args, calls = inputs(tmp_path, monkeypatch)
    producer = tmp_path / "producer.py"
    producer.write_text("historical producer")
    report = module.load_handoff_json(args[2].read_bytes())
    report["evidence_sha256"][str(producer)] = file_hash(producer)
    args[2].write_bytes(json_bytes(report))
    producer.write_text("updated producer")
    out = tmp_path / "bundle"
    with pytest.raises(ValueError, match="Hash mismatch"):
        module.package(*args, out)
    assert not out.exists()
    assert calls == []


@pytest.mark.parametrize("reject", [False, True])
def test_explicit_migration_reaches_reconstruction_and_is_declared(tmp_path, monkeypatch, reject):
    args, _ = inputs(tmp_path, monkeypatch)
    audit = module.load_handoff_json(args[2].read_bytes())
    audit["producer_migration"] = "public-reader/1"
    args[2].write_bytes(json_bytes(audit))
    calls = []

    def reconstruct(*args, **kwargs):
        calls.append(kwargs)
        if reject:
            raise ValueError("Unregistered migration")

    monkeypatch.setattr(module, "verify_snapshot", reconstruct)
    out = tmp_path / "bundle"
    if reject:
        with pytest.raises(ValueError, match="Unregistered"):
            module.package(*args, out, allow_producer_migration=True)
        assert not out.exists()
    else:
        manifest = module.package(*args, out, allow_producer_migration=True)
        assert manifest["producer_migration"] == "public-reader/1"
        verify_bundle(out)
    assert calls == [{"allow_producer_migration": True}]
