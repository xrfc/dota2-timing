"""Migration accepts only registered producer metadata, never changed data."""

import copy

import pytest

from dota_items.data.producer_migration import ADDED, LEGACY_SHA256, ROOT, compare_replay
from dota_items.storage import file_hash, json_bytes


def pair():
    old = {
        "implementation_sha256": dict(LEGACY_SHA256),
        "samples": [{"labels": [1], "split": "train", "encoded_features": [0, 1]}],
        "task": {"window": [0, 1800]},
        "training_allowed": False,
    }
    new = copy.deepcopy(old)
    new["implementation_sha256"] = {
        name: file_hash(ROOT / name) for name in set(LEGACY_SHA256) | ADDED
    }
    return old, new


def test_registered_metadata_only_replay_is_nonmutating():
    old, new = pair()
    before = json_bytes(old)
    receipt = compare_replay(old, new)
    assert receipt["migration"] == "public-reader/1"
    assert receipt["training_allowed"] is False
    assert len(receipt["changes"]) == len(LEGACY_SHA256) + len(ADDED)
    assert json_bytes(old) == before
    assert compare_replay(new, new)["changes"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("labels", [0]),
        ("labels", [True]),
        ("split", "test"),
        ("encoded_features", [1, 0]),
    ],
)
def test_data_and_json_types_cannot_change(field, value):
    old, new = pair()
    new["samples"][0][field] = value
    with pytest.raises(ValueError, match="outside"):
        compare_replay(old, new)


@pytest.mark.parametrize("mutation", ["old_hash", "new_hash", "drop", "extra", "null_added"])
def test_unregistered_or_partial_producer_changes_rejected(mutation):
    old, new = pair()
    name = "data/feasibility.py"
    if mutation == "old_hash":
        old["implementation_sha256"][name] = "0" * 64
    elif mutation == "new_hash":
        new["implementation_sha256"][name] = "0" * 64
    elif mutation == "drop":
        del new["implementation_sha256"][name]
    elif mutation == "extra":
        new["implementation_sha256"]["../evil.py"] = "0" * 64
    else:
        old["implementation_sha256"]["data/source_io.py"] = None
    with pytest.raises(ValueError):
        compare_replay(old, new)


def test_nested_preflight_metadata_is_explicit_not_recursively_ignored():
    old, new = pair()
    old["audit"] = {"implementation_sha256": dict(old["implementation_sha256"])}
    new["audit"] = {"implementation_sha256": dict(new["implementation_sha256"])}
    with pytest.raises(ValueError, match="outside"):
        compare_replay(old, new)
    assert compare_replay(
        old, new, metadata_paths=(("implementation_sha256",), ("audit", "implementation_sha256"))
    )


def test_snapshot_strict_default_and_opt_in_returns_original(tmp_path, monkeypatch):
    from dota_items.data import purchase_snapshot

    old, new = pair()
    path = tmp_path / "snapshot.json"
    path.write_bytes(json_bytes(old))
    monkeypatch.setattr(purchase_snapshot, "build_snapshot", lambda *args, **kwargs: new)
    with pytest.raises(ValueError, match="reconstruction"):
        purchase_snapshot.verify_snapshot(path, tmp_path / "summary.json")
    assert (
        purchase_snapshot.verify_snapshot(
            path, tmp_path / "summary.json", allow_producer_migration=True
        )
        == old
    )
    assert path.read_bytes() == json_bytes(old)


def test_preflight_migration_is_not_reported_as_exact_reproduction(tmp_path, monkeypatch):
    from dota_items.data import lineup_preflight

    old, new = pair()
    for report in (old, new):
        report.update(schema_version="lineup-preflight/2", config={}, summary={})
        report["audit"] = {"implementation_sha256": dict(report["implementation_sha256"])}
    path = tmp_path / "preflight.json"
    path.write_bytes(json_bytes(old))
    monkeypatch.setattr(lineup_preflight, "build_preflight", lambda *args: new)
    with pytest.raises(ValueError, match="offline replay"):
        lineup_preflight.verify_preflight(path, None, None, None, None)
    receipt = lineup_preflight.verify_preflight(
        path, None, None, None, None, allow_producer_migration=True
    )
    assert receipt["status"] == "compatible_replay"
    assert receipt["producer_migration"]["changes"]
