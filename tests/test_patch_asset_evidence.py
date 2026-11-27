import hashlib
import json
from types import SimpleNamespace

import pytest

from dota_items.data.patch_asset_evidence import EvidencePins, decode_json, read_runtime_capture


@pytest.mark.parametrize("raw", [b'{"a": 1,"a": 2}', b"[NaN]", b'{"a": [1e999]}'])
def test_strict_evidence_does_not_accept_ambiguous_values(raw):
    with pytest.raises(ValueError):
        decode_json(raw)


def test_used_bytes_and_later_drift_are_checked(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"patch": "7.42"}))
    ref = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    pins = EvidencePins()
    assert pins.read(ref) == {"patch": "7.42"}
    exposed = pins.inventory
    exposed.clear()
    assert pins.inventory
    path.write_text(json.dumps({"patch": "7.42a"}))
    with pytest.raises(ValueError, match="changed"):
        pins.verify()
    with pytest.raises(ValueError, match="digest"):
        EvidencePins().read(ref)


def test_symlink_and_parent_symlink_are_not_evidence(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    path = root / "source.json"
    path.write_text("{}")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    ref = {"path": str(alias / path.name), "sha256": hashlib.sha256(b"{}").hexdigest()}
    with pytest.raises(ValueError, match="symbolic"):
        EvidencePins().read(ref)


def test_conflicting_pin_is_not_replaced(tmp_path):
    path = tmp_path / "source.json"
    path.write_text("{}")
    pins = EvidencePins()
    pins.track(path)
    path.write_text("[]")
    with pytest.raises(ValueError, match="Conflicting"):
        pins.track(path)


@pytest.mark.parametrize("bad", ["match_id", "patch", "manifest", "omniscient", "source_drift"])
def test_runtime_capture_cannot_mix_identity_or_hide_source_drift(tmp_path, bad):
    def write(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    source = SimpleNamespace(match_id=123, patch="7.42", build=6993)
    original = write("original.json", {})
    source.receipt = lambda: {"manifest": original}
    dep = write("producer.json", {"implementation": 1})
    capture = {
        "schema": "map-runtime-capture/1",
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "coordinate_space": "world",
        "omniscient": True,
        "post_game_tick": 100,
        "training_allowed": False,
    }
    if bad == "match_id":
        capture["match_id"] = 124
    elif bad == "patch":
        capture["patch"] = "7.42a"
    elif bad == "omniscient":
        capture["omniscient"] = False
    cref = write("capture.json", capture)
    receipt = {
        "schema": "map-runtime-capture-receipt/1",
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "manifest": original,
        "training_allowed": False,
        "output_sha256": {"capture.json": cref["sha256"]},
        "used_files": {dep["path"]: dep["sha256"]},
    }
    if bad == "manifest":
        receipt["manifest"] = {**original, "sha256": "1" * 64}
    rref = write("receipt.json", receipt)
    if bad == "source_drift":
        write("producer.json", {"implementation": 2})
    with pytest.raises(ValueError):
        read_runtime_capture(cref, rref, source=source, pins=EvidencePins())
