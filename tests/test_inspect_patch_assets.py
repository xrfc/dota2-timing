"""Publication rejects source/code drift even when all diagnostics computed."""

import importlib.util
import json
from pathlib import Path

import pytest

from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inspection(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "inspect_patch_assets_test", ROOT / "scripts/inspect_patch_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in module.PRODUCER_FILES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source")
    binding_file = tmp_path / "binding.json"
    binding_file.write_text("{}")
    config = {
        "schema": "patch-assets-inspection/1",
        "exact_patch": "7.42",
        "binding": {"path": str(binding_file), "sha256": file_hash(binding_file)},
        "replays": [{"path": "manifest", "sha256": "a" * 64}],
        "older_map": None,
        "landmarks": [],
    }
    config_file = tmp_path / "spec.json"
    config_file.write_text(json.dumps(config))

    class Map:
        def read(self, _):
            return {}

    class Binding:
        map = Map()
        binding = {"map": {"client_version": 6989}}

        def summary(self):
            return {"status": "candidate"}

        def verify_again(self):
            return self.summary()

    class Source:
        match_id, patch, build, duration = 123, "7.42", 6993, 1

        def rows(self, _):
            return iter([])

        def verify_again(self):
            return {"verified": True}

    monkeypatch.setattr(module, "verify_patch_assets", lambda *a, **k: Binding())
    monkeypatch.setattr(module, "open_geometry_source", lambda *a, **k: Source())
    monkeypatch.setattr(module, "audit_replay_geometry", lambda *a, **k: {"diagnostic": True})
    return module, config_file, tmp_path / "out", repo, Binding, Source


def test_published_report_keeps_versions_separate_and_pins_output(inspection):
    module, config, output, repo, _, _ = inspection
    result = module.run(config, output, repository_root=repo)
    assert result["map_client_version"] == 6989
    assert result["replay_builds"] == [6993]
    assert result["compatibility_approved"] is False
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["outputs"]["report.json"] == file_hash(output / "report.json")
    with pytest.raises(ValueError, match="already exists"):
        module.run(config, output, repository_root=repo)


def test_code_drift_during_initial_asset_verification_blocks_publication(inspection, monkeypatch):
    module, config, output, repo, Binding, _ = inspection

    def changed(*args, **kwargs):
        (repo / module.PRODUCER_FILES[0]).write_text("changed during input validation")
        return Binding()

    monkeypatch.setattr(module, "verify_patch_assets", changed)
    with pytest.raises(ValueError, match="Consumer code changed"):
        module.run(config, output, repository_root=repo)
    assert not output.exists()
    assert not list(output.parent.glob(".patch-inspection-*"))


def test_input_drift_after_diagnostics_blocks_publication(inspection, monkeypatch):
    module, config, output, repo, _, Source = inspection

    def drift(self):
        raise ValueError("Replay geometry source drift")

    monkeypatch.setattr(Source, "verify_again", drift)
    with pytest.raises(ValueError, match="drift"):
        module.run(config, output, repository_root=repo)
    assert not output.exists()


def test_binding_reference_drift_blocks_publication(inspection, monkeypatch):
    module, config, output, repo, _, _ = inspection

    def alter(*args, **kwargs):
        (config.parent / "binding.json").write_text('{"changed": true}')
        return {}

    monkeypatch.setattr(module, "audit_replay_geometry", alter)
    with pytest.raises(ValueError, match="Pinned JSON changed"):
        module.run(config, output, repository_root=repo)
    assert not output.exists()
