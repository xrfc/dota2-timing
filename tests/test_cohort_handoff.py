import copy

import pytest

from dota_items.data.cohort_handoff import checked, component_impact, numeric, verify_bundle
from dota_items.storage import file_hash, json_bytes


def test_bridge_preserves_old_split_and_detects_transitive_connections():
    old = [
        {"match_id": 1, "split": "train", "group_id": "a"},
        {"match_id": 2, "split": "test", "group_id": "b"},
    ]
    original = copy.deepcopy(old)
    result = component_impact([[1, 2, 3, 4], [5]], old, {3, 4, 5})
    assert result["bridging_group_count"] == 1
    assert result["new_in_bridging_groups"] == 2
    assert result["new_without_observed_old_connection"] == 1
    assert old == original


def test_no_bridge_with_only_one_old_split():
    result = component_impact(
        [[1, 3], [2]], [{"match_id": 1, "split": "train", "group_id": "a"}], {2, 3}
    )
    assert result["bridging_group_count"] == 0
    assert result["mixed_old_new_groups"] == 1


def test_numeric_missing_is_not_zero():
    assert numeric([None, True, 10, 20]) == {
        "observed": 2,
        "missing": 2,
        "min": 10,
        "median": 15,
        "max": 20,
    }


def bundle(tmp_path):
    payloads = {
        "snapshot.json": {"schema_version": "purchase-log-modeling-snapshot/1"},
        "summary.json": {"schema_version": "purchase-collection-summary/1"},
        "cohort-audit.json": {
            "schema_version": "purchase-cohort-audit/1",
            "training_allowed": False,
            "new_split_assigned": False,
            "old_split_changed": False,
        },
        "synthetic-reader-example.json": {
            "schema_version": "purchase-log-modeling-snapshot/1",
            "synthetic": True,
            "modeling_ready": False,
            "training_executed": False,
            "legacy_training_allowed": False,
        },
    }
    for name, value in payloads.items():
        (tmp_path / name).write_bytes(json_bytes(value))
    (tmp_path / "INTERFACE.md").write_text("Synthetic interface only")
    names = [*payloads, "INTERFACE.md"]
    manifest = {
        "schema_version": "purchase-data-handoff/1",
        "training_authorized_by_package": False,
        "new_snapshot_created": False,
        "raw_sources_included": False,
        "producer_sha256": "a" * 64,
        "source_paths": {
            name: f"/unavailable/original/{name}"
            for name in names
            if name != "synthetic-reader-example.json"
        },
        "files": {name: file_hash(tmp_path / name) for name in names},
    }
    save_manifest(tmp_path, manifest)
    return manifest


def save_manifest(directory, manifest):
    (directory / "manifest.json").write_bytes(json_bytes(manifest))


def test_bundle_integrity_and_tampering(tmp_path):
    bundle(tmp_path)
    assert verify_bundle(tmp_path)["schema_version"] == "purchase-log-modeling-snapshot/1"
    (tmp_path / "snapshot.json").write_text("{}")
    with pytest.raises(ValueError, match="Hash mismatch"):
        verify_bundle(tmp_path)


def test_bundle_missing_file(tmp_path):
    bundle(tmp_path)
    (tmp_path / "summary.json").unlink()
    with pytest.raises(FileNotFoundError):
        verify_bundle(tmp_path)


def test_bundle_path_escape(tmp_path):
    manifest = bundle(tmp_path)
    manifest["files"]["../outside.json"] = "0" * 64
    (tmp_path / "manifest.json").write_bytes(json_bytes(manifest))
    with pytest.raises(ValueError, match="Unsafe"):
        verify_bundle(tmp_path)


def test_checked_rejects_altered_evidence(tmp_path):
    p = tmp_path / "input.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="Hash mismatch"):
        checked(p, "0" * 64)


@pytest.mark.parametrize("values", [[], [None, False, True, "3"]])
def test_numeric_empty_or_all_missing_retains_denominator(values):
    assert numeric(values) == {
        "observed": 0,
        "missing": len(values),
        "min": None,
        "median": None,
        "max": None,
    }


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_numeric_nonfinite_rejected_not_silently_removed(bad):
    values = [None, False, 0, bad, 10]
    with pytest.raises(ValueError, match="Nonfinite numeric observation"):
        numeric(values)
    assert len(values) == 5


def test_numeric_rejects_overflowed_median():
    with pytest.raises(ValueError, match="Nonfinite numeric median"):
        numeric([1e308, 1e308])


@pytest.mark.parametrize(
    "name",
    [
        "snapshot.json",
        "summary.json",
        "cohort-audit.json",
        "synthetic-reader-example.json",
        "INTERFACE.md",
    ],
)
def test_bundle_requires_every_declared_payload(tmp_path, name):
    manifest = bundle(tmp_path)
    del manifest["files"][name]
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="Missing or unexpected bundle payload"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize("files", [None, [], "snapshot.json", {}])
def test_bundle_rejects_missing_or_invalid_file_manifest(tmp_path, files):
    manifest = bundle(tmp_path)
    if files is None:
        del manifest["files"]
    else:
        manifest["files"] = files
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError):
        verify_bundle(tmp_path)


@pytest.mark.parametrize("digest", [None, False, 123, "0" * 63, "A" * 64, "g" * 64])
def test_bundle_rejects_malformed_sha256(tmp_path, digest):
    manifest = bundle(tmp_path)
    manifest["files"]["snapshot.json"] = digest
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="Invalid SHA-256"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize(
    "name",
    ["/outside.json", "../outside.json", "./snapshot.json", "sub/x", "sub\\x", "C:x", "..", ""],
)
def test_bundle_rejects_path_aliases_before_read(tmp_path, name):
    manifest = bundle(tmp_path)
    manifest["files"][name] = "0" * 64
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="Unsafe bundle path"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize("name", ["manifest.json", "snapshot.json", "summary.json"])
@pytest.mark.parametrize("external", [False, True])
def test_bundle_rejects_symlinks_even_inside_root(tmp_path, name, external):
    root = tmp_path / "bundle"
    root.mkdir()
    bundle(root)
    path = root / name
    target = (tmp_path if external else root) / "target.json"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(ValueError, match="Unsafe bundle path"):
        verify_bundle(root)


def test_bundle_rejects_symlink_root(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    bundle(root)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe or missing bundle directory"):
        verify_bundle(alias)


@pytest.mark.parametrize("name", ["manifest.json", "snapshot.json"])
def test_bundle_rejects_duplicate_json_keys_even_when_hashed(tmp_path, name):
    manifest = bundle(tmp_path)
    if name == "manifest.json":
        raw = (tmp_path / name).read_text().replace('"files": {', '"files": {}, "files": {', 1)
    else:
        raw = '{"schema_version":"wrong","schema_version":"purchase-log-modeling-snapshot/1"}'
    (tmp_path / name).write_text(raw)
    if name != "manifest.json":
        manifest["files"][name] = file_hash(tmp_path / name)
        save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize(
    "name", ["snapshot.json", "summary.json", "cohort-audit.json", "synthetic-reader-example.json"]
)
@pytest.mark.parametrize("value", [{}, [], {"schema_version": "wrong"}])
def test_bundle_checks_all_json_payload_schemas(tmp_path, name, value):
    manifest = bundle(tmp_path)
    (tmp_path / name).write_bytes(json_bytes(value))
    manifest["files"][name] = file_hash(tmp_path / name)
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="Unsupported payload schema"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_bundle_rejects_nonfinite_json_even_with_matching_hash(tmp_path, constant):
    manifest = bundle(tmp_path)
    (tmp_path / "snapshot.json").write_text(
        '{"schema_version":"purchase-log-modeling-snapshot/1","value":' + constant + "}"
    )
    manifest["files"]["snapshot.json"] = file_hash(tmp_path / "snapshot.json")
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="Nonfinite JSON number"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize(
    "field", ["training_authorized_by_package", "new_snapshot_created", "raw_sources_included"]
)
@pytest.mark.parametrize("bad", [None, 0, True])
def test_bundle_boundary_declarations_must_be_explicit_false(tmp_path, field, bad):
    manifest = bundle(tmp_path)
    manifest[field] = bad
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="Invalid handoff research boundaries"):
        verify_bundle(tmp_path)


def test_bundle_rejects_unmarked_partial_output(tmp_path):
    bundle(tmp_path)
    (tmp_path / "manifest.json").unlink()
    with pytest.raises(FileNotFoundError):
        verify_bundle(tmp_path)


def test_bundle_read_does_not_claim_semantics_origin_or_authorization(tmp_path):
    # Correct schemas and hashes need not imply a usable sample or real origin.
    # The descriptive source_paths intentionally do not exist on this machine.
    bundle(tmp_path)
    assert verify_bundle(tmp_path) == {"schema_version": "purchase-log-modeling-snapshot/1"}


@pytest.mark.parametrize("value", [None, [], {}, {"schema_version": "wrong"}])
def test_invalid_manifest_root_is_rejected(tmp_path, value):
    bundle(tmp_path)
    save_manifest(tmp_path, value)
    with pytest.raises(ValueError, match="Unsupported handoff"):
        verify_bundle(tmp_path)


@pytest.mark.parametrize("field", ["producer_sha256", "source_paths"])
def test_manifest_requires_producer_and_descriptive_source_metadata(tmp_path, field):
    manifest = bundle(tmp_path)
    del manifest[field]
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError):
        verify_bundle(tmp_path)


@pytest.mark.parametrize(
    "name,field,bad",
    [
        ("cohort-audit.json", "training_allowed", True),
        ("cohort-audit.json", "new_split_assigned", 0),
        ("cohort-audit.json", "old_split_changed", None),
        ("synthetic-reader-example.json", "synthetic", False),
        ("synthetic-reader-example.json", "modeling_ready", True),
        ("synthetic-reader-example.json", "training_executed", 0),
        ("synthetic-reader-example.json", "legacy_training_allowed", None),
    ],
)
def test_payload_boundary_declarations_are_not_inferred(tmp_path, name, field, bad):
    import json

    manifest = bundle(tmp_path)
    path = tmp_path / name
    value = json.loads(path.read_text())
    value[field] = bad
    path.write_bytes(json_bytes(value))
    manifest["files"][name] = file_hash(path)
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="boundaries"):
        verify_bundle(tmp_path)


def test_bundle_rejects_dangling_payload_symlink(tmp_path):
    bundle(tmp_path)
    path = tmp_path / "snapshot.json"
    path.unlink()
    path.symlink_to(tmp_path / "absent")
    with pytest.raises(ValueError, match="Unsafe bundle path"):
        verify_bundle(tmp_path)


def test_bundle_requires_regular_payload_files(tmp_path):
    bundle(tmp_path)
    path = tmp_path / "snapshot.json"
    path.unlink()
    path.mkdir()
    with pytest.raises(FileNotFoundError):
        verify_bundle(tmp_path)


@pytest.mark.parametrize(
    "manifest_value,audit_value,valid",
    [
        ("public-reader/1", "public-reader/1", True),
        ("unknown", "unknown", False),
        (None, None, False),
        ("public-reader/1", "absent", False),
        ("absent", "public-reader/1", False),
    ],
)
def test_migration_declarations_are_explicit_and_consistent(
    tmp_path, manifest_value, audit_value, valid
):
    import json

    manifest = bundle(tmp_path)
    if manifest_value != "absent":
        manifest["producer_migration"] = manifest_value
    path = tmp_path / "cohort-audit.json"
    audit = json.loads(path.read_text())
    if audit_value != "absent":
        audit["producer_migration"] = audit_value
    path.write_bytes(json_bytes(audit))
    manifest["files"]["cohort-audit.json"] = file_hash(path)
    save_manifest(tmp_path, manifest)
    if valid:
        verify_bundle(tmp_path)
    else:
        with pytest.raises(ValueError, match="migration"):
            verify_bundle(tmp_path)
