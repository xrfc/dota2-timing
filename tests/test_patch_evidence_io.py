import json
from pathlib import Path

import pytest
from test_capture_map_runtime import write
from test_patch_capture_receipt import fresh_fixture

from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.data.patch_evidence_io import producer_files, read_evidence_capture
from scripts.capture_patch_evidence import run


def supplementary(tmp_path, monkeypatch):
    anchor, receipt, source, root, compat = fresh_fixture(tmp_path, monkeypatch)
    old = json.loads(Path(receipt["path"]).read_text())
    pins = EvidencePins()
    for name, digest in old["used_files"].items():
        pins.add({"path": name, "sha256": digest})
    for ref in (anchor, receipt):
        pins.add(ref)
    for name in producer_files("objectives"):
        p = root / name
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# pinned\n")
        pins.track(p)
    spec = {
        "schema": "patch-evidence-capture-spec/1",
        "kind": "objectives",
        "exact_patch": "7.42",
        "anchor": {"capture": anchor, "receipt": receipt},
    }
    sref = write(tmp_path / "new-spec.json", spec)
    pins.add(sref)
    doc = {**json.loads(Path(anchor["path"]).read_text()), "schema": "map-objective-evidence/1"}
    cref = write(tmp_path / "new/capture.json", doc)
    rec = {
        **old,
        "schema": "patch-evidence-capture-receipt/1",
        "kind": "objectives",
        "spec": sref,
        "anchor": spec["anchor"],
        "used_files": pins.inventory,
        "output_sha256": {"capture.json": cref["sha256"]},
        "action_review_allowed": False,
    }
    rref = write(tmp_path / "new/receipt.json", rec)
    return cref, rref, root


def consume(cref, rref, root, allowed=True):
    pins = EvidencePins()
    doc = read_evidence_capture(
        cref, rref, pins=pins, repository_root=root, match_allowed=lambda _: allowed
    )
    pins.verify()
    return doc


def test_complete_supplementary_capture_and_no_overwrite(tmp_path, monkeypatch):
    c, r, root = supplementary(tmp_path, monkeypatch)
    assert consume(c, r, root)["match_id"] == 123
    with pytest.raises(ValueError, match="already exists"):
        run(tmp_path / "absent", Path(c["path"]).parent)
    with pytest.raises(ValueError, match="excluded"):
        consume(c, r, root, False)


@pytest.mark.parametrize(
    "change", ["producer", "anchor", "archive", "dependencies", "end", "purpose", "patch", "output"]
)
def test_incomplete_or_mismatched_receipts_are_rejected(tmp_path, monkeypatch, change):
    c, r, root = supplementary(tmp_path, monkeypatch)
    rec = json.loads(Path(r["path"]).read_text())
    doc = json.loads(Path(c["path"]).read_text())
    if change == "producer":
        rec["used_files"].pop(str(root / "src/dota_items/sources/map_objective_evidence.py"))
    elif change == "anchor":
        rec["anchor"]["capture"]["sha256"] = "a" * 64
    elif change == "archive":
        rec["demo_sha256"] = "a" * 64
    elif change == "dependencies":
        rec["dependencies"] = {}
    elif change == "end":
        doc["post_game_tick"] = 301
    elif change == "purpose":
        doc["training_allowed"] = True
    elif change == "patch":
        doc["patch"] = "7.42a"
    else:
        rec["output_sha256"] = {}
    if change in ("end", "purpose", "patch"):
        c = write(Path(c["path"]), doc)
        rec["output_sha256"] = {"capture.json": c["sha256"]}
    r = write(Path(r["path"]), rec)
    with pytest.raises(ValueError):
        consume(c, r, root)
