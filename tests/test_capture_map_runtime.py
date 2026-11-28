import json
from importlib.metadata import version
from pathlib import Path

import pytest
from test_map_replay_source import source_fixture

from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.storage import file_hash
from scripts import capture_map_runtime as cli


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {"path": str(path), "sha256": file_hash(path)}


def runtime_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "is_holdout", lambda mid: False)
    path, manifest = source_fixture(tmp_path)
    archive = tmp_path / "123.dem"
    archive.write_bytes(b"pinned original archive")
    compat = tmp_path / "compat"
    module = compat / "gem/__init__.py"
    module.parent.mkdir(parents=True)
    module.write_text("# parser fixture\n")
    cm = write(
        compat / "manifest.json",
        {
            "schema": "gem-isolated-backport/1",
            "base_version": "0.10.0",
            "patched": {"__init__.py": file_hash(module)},
        },
    )
    manifest["identity"]["source_references"].append(
        {"path": str(archive), "sha256": file_hash(archive), "size_bytes": archive.stat().st_size}
    )
    manifest["producer"]["parser"] = {"manifest_sha256": cm["sha256"]}
    manifest["producer"]["dependencies"] = {"pytest": version("pytest")}
    manifest["quality"]["parser"]["post_game_tick"] = 300
    mref = write(path, manifest)
    capture = {
        "schema": "map-landmark-capture/1",
        "coordinate_space": "world",
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "post_game_tick": 300,
        "training_allowed": False,
    }
    cref = write(tmp_path / "landmarks/capture.json", capture)
    receipt = {
        "schema": "map-landmark-capture-receipt/1",
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "manifest": mref,
        "training_allowed": False,
        "output_sha256": {"capture.json": cref["sha256"]},
        "used_files": {str(p): file_hash(p) for p in (archive, module, compat / "manifest.json")},
        "dependencies": {"pytest": version("pytest")},
        "demo_sha256": "d" * 64,
    }
    rref = write(tmp_path / "landmarks/receipt.json", receipt)
    spec = {
        "schema": "map-runtime-capture-spec/1",
        "capture_kind": "runtime",
        "exact_patch": "7.42",
        "replay": mref,
        "landmarks": {"capture": cref, "receipt": rref},
        "compat": str(compat),
    }
    spec_path = tmp_path / "runtime-spec.json"
    write(spec_path, spec)
    return spec_path, spec, compat


def test_prepare_keeps_pinned_source_identity_and_detects_added_runtime_resource(
    tmp_path, monkeypatch
):
    path, spec, compat = runtime_fixture(tmp_path, monkeypatch)
    prepared = cli.prepare(path, EvidencePins())
    assert prepared[1].match_id == 123
    assert prepared[3].name == "123.dem"
    assert prepared[5] == {"__init__.py": file_hash(compat / "gem/__init__.py")}
    write(compat / "gem/new-resource.json", {})
    with pytest.raises(ValueError, match="inventory changed"):
        cli.prepare(path, EvidencePins())


def test_holdout_exclusion_precedes_landmark_or_archive_reads(tmp_path, monkeypatch):
    path, spec, _ = runtime_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "is_holdout", lambda mid: True)
    spec["landmarks"]["capture"]["path"] = str(tmp_path / "missing.json")
    write(path, spec)
    with pytest.raises(ValueError, match="holdout|excluded|allowed"):
        cli.prepare(path, EvidencePins())


def test_letter_patch_does_not_reuse_captures(tmp_path, monkeypatch):
    path, spec, _ = runtime_fixture(tmp_path, monkeypatch)
    spec["exact_patch"] = "7.42a"
    write(path, spec)
    with pytest.raises(ValueError, match="patch"):
        cli.prepare(path, EvidencePins())


def test_changed_archive_cannot_be_reparsed_under_old_receipt(tmp_path, monkeypatch):
    path, _, _ = runtime_fixture(tmp_path, monkeypatch)
    (tmp_path / "123.dem").write_bytes(b"different archive")
    with pytest.raises(ValueError, match="drift"):
        cli.prepare(path, EvidencePins())


def test_no_overwrite_before_parser_work(tmp_path):
    output = tmp_path / "published"
    output.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        cli.run(tmp_path / "missing-spec.json", output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("bad", ["archive_size", "archive_hash", "dependencies"])
def test_manifest_source_and_dependencies_cannot_disagree_with_capture(tmp_path, monkeypatch, bad):
    path, spec, _ = runtime_fixture(tmp_path, monkeypatch)
    manifest = json.loads(Path(spec["replay"]["path"]).read_text())
    receipt = json.loads(Path(spec["landmarks"]["receipt"]["path"]).read_text())
    if bad == "archive_size":
        manifest["identity"]["source_references"][-1]["size_bytes"] += 1
    elif bad == "archive_hash":
        manifest["identity"]["source_references"][-1]["sha256"] = "f" * 64
    else:
        manifest["producer"]["dependencies"]["intentionally-missing"] = "0.0"
    spec["replay"] = write(Path(spec["replay"]["path"]), manifest)
    receipt["manifest"] = spec["replay"]
    spec["landmarks"]["receipt"] = write(Path(spec["landmarks"]["receipt"]["path"]), receipt)
    write(path, spec)
    with pytest.raises(ValueError):
        cli.prepare(path, EvidencePins())
