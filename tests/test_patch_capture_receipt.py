import json
from pathlib import Path

import pytest
from test_capture_map_runtime import runtime_fixture, write

from dota_items.data.patch_asset_evidence import (
    RUNTIME_PRODUCER_FILES,
    EvidencePins,
    read_runtime_capture,
)
from scripts.capture_map_runtime import prepare


def fresh_fixture(tmp_path, monkeypatch):
    spec_path, spec, compat = runtime_fixture(tmp_path, monkeypatch)
    pins = EvidencePins()
    _, source, landmark, _, _, _, dependencies = prepare(spec_path, pins)
    repository = tmp_path / "repository"
    for name in RUNTIME_PRODUCER_FILES:
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixed producer\n")
        pins.track(path)
    capture = {**landmark, "schema": "map-runtime-capture/1", "omniscient": True}
    cref = write(tmp_path / "fresh/capture.json", capture)
    receipt = {
        "schema": "map-runtime-capture-receipt/1",
        "match_id": source.match_id,
        "patch": source.patch,
        "game_build": source.build,
        "manifest": spec["replay"],
        "landmarks": spec["landmarks"],
        "spec": pins.track(spec_path),
        "used_files": pins.inventory,
        "dependencies": dependencies,
        "demo_sha256": "d" * 64,
        "output_sha256": {"capture.json": cref["sha256"]},
        "training_allowed": False,
    }
    rref = write(tmp_path / "fresh/receipt.json", receipt)
    return cref, rref, source, repository, compat


def test_complete_capture_receipt_is_consumable(tmp_path, monkeypatch):
    cref, rref, source, repository, _ = fresh_fixture(tmp_path, monkeypatch)
    pins = EvidencePins()
    doc = read_runtime_capture(cref, rref, source=source, pins=pins, repository_root=repository)
    assert doc["post_game_tick"] == 300
    pins.verify()


@pytest.mark.parametrize("bad", ["producer", "original_archive", "end", "dependencies", "resource"])
def test_partial_or_mismatched_capture_cannot_claim_a_valid_receipt(tmp_path, monkeypatch, bad):
    cref, rref, source, repository, compat = fresh_fixture(tmp_path, monkeypatch)
    receipt = json.loads(Path(rref["path"]).read_text())
    if bad == "producer":
        del receipt["used_files"][str(repository / RUNTIME_PRODUCER_FILES[0])]
    elif bad == "original_archive":
        del receipt["used_files"][str(tmp_path / "123.dem")]
    elif bad == "dependencies":
        receipt["dependencies"] = {}
    elif bad == "resource":
        write(compat / "gem/late.json", {})
    else:
        capture = json.loads(Path(cref["path"]).read_text())
        capture["post_game_tick"] = 0
        cref = write(Path(cref["path"]), capture)
        receipt["output_sha256"] = {"capture.json": cref["sha256"]}
    rref = write(Path(rref["path"]), receipt)
    with pytest.raises(ValueError):
        read_runtime_capture(
            cref, rref, source=source, pins=EvidencePins(), repository_root=repository
        )
