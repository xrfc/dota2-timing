import json
from pathlib import Path

import pytest
from test_capture_map_runtime import write

from dota_items.data import patch_decision_source as module
from dota_items.data.patch_decision_source import (
    EVIDENCE_PRODUCERS,
    EVIDENCE_TEXTS,
    OUTPUT_SCHEMAS,
    open_decision_evidence,
)
from dota_items.storage import file_hash


def fixture(tmp_path):
    root, output = tmp_path / "repo", tmp_path / "output"
    used = {}
    for name in EVIDENCE_PRODUCERS:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# frozen producer\n")
        used[str(p)] = file_hash(p)
    manifest = write(
        tmp_path / "manifest.json",
        {"identity": {"match_id": 123}, "quality": {"base": {"metadata_duration": 10}}},
    )
    base_output = write(tmp_path / "baseline/output.json", {})
    base = write(
        tmp_path / "baseline/receipt.json",
        {
            "schema": "patch-review-assets-receipt/1",
            "exact_patch": "7.42",
            "training_allowed": False,
            "action_review_allowed": False,
            "used_files": {manifest["path"]: manifest["sha256"]},
            "output_sha256": {"output.json": base_output["sha256"]},
        },
    )
    used[base_output["path"]] = base_output["sha256"]
    texts = {key: write(root / name, {}) for key, name in EVIDENCE_TEXTS.items()}
    used.update({ref["path"]: ref["sha256"] for ref in texts.values()})
    refs = []
    for kind in ("objectives", "vision"):
        common = {
            "match_id": 123,
            "patch": "7.42",
            "game_build": 6993,
            "post_game_tick": 300,
            "training_allowed": False,
            "action_review_allowed": False,
        }
        capture = write(tmp_path / kind / "capture.json", common)
        receipt = write(
            tmp_path / kind / "receipt.json",
            {
                **common,
                "schema": "patch-evidence-capture-receipt/1",
                "kind": kind,
                "manifest": manifest,
                "demo_sha256": "d" * 64,
                "used_files": {manifest["path"]: manifest["sha256"]},
                "output_sha256": {"capture.json": capture["sha256"]},
            },
        )
        refs.append({"capture": capture, "receipt": receipt})
        used.update({ref["path"]: ref["sha256"] for ref in (capture, receipt)})
    spec = {
        "schema": "patch-evidence-assets-spec/1",
        "exact_patch": "7.42",
        "base_receipt": base,
        "captures": refs,
    }
    sref = write(tmp_path / "spec.json", spec)
    used.update({ref["path"]: ref["sha256"] for ref in (sref, base, manifest)})
    hashes = {}
    for name, schema in OUTPUT_SCHEMAS.items():
        sources = {"base": base, "captures": refs, **texts}
        if name == "camp-semantics.json":
            sources["camp_assets"] = {
                "path": str(output / "camp-observations.json"),
                "sha256": hashes["camp-observations.json"],
            }
        doc = {
            "schema": schema,
            "exact_patch": "7.42",
            "match_ids": [123],
            "source_refs": sources,
            "training_allowed": False,
            "action_review_allowed": False,
        }
        hashes[name] = write(output / name, doc)["sha256"]
    rec = {
        "schema": "patch-evidence-assets-receipt/1",
        "patch": "7.42",
        "training_allowed": False,
        "action_review_allowed": False,
        "spec": sref,
        "used_files": used,
        "output_sha256": hashes,
    }
    return write(output / "receipt.json", rec), root, rec, spec


def test_registered_producer_closure_matches_original_writer():
    from scripts.build_patch_evidence import PRODUCER_FILES

    assert set(EVIDENCE_PRODUCERS) == set(PRODUCER_FILES)


def test_all_channels_must_be_consumed_and_postread_drift_is_detected(tmp_path, monkeypatch):
    ref, root, rec, _ = fixture(tmp_path)
    calls = []

    def read_capture(cref, rref, **kwargs):
        calls.append(kwargs["match_allowed"](123))
        return kwargs["pins"].read(cref)

    monkeypatch.setattr(module, "read_evidence_capture", read_capture)
    source = open_decision_evidence(ref, repository_root=root, match_allowed=lambda mid: mid == 123)
    with pytest.raises(ValueError, match="Every selected"):
        source.verify()
    assert source.read_match(123)["metadata_duration"] == 10
    assert calls == [True, True]
    source.verify()
    Path(next(iter(rec["used_files"]))).write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        source.verify()


def test_exclusion_precedes_capture_bodies_and_producer_file_reads(tmp_path):
    ref, root, _, spec = fixture(tmp_path)
    Path(spec["captures"][0]["capture"]["path"]).unlink()
    with pytest.raises(ValueError, match="excluded"):
        open_decision_evidence(
            ref, repository_root=tmp_path / "missing", match_allowed=lambda _: False
        )


@pytest.mark.parametrize(
    "change",
    ["producer", "purpose", "patch", "output", "cross_channel", "coverage", "camp_reference"],
)
def test_incomplete_or_inconsistent_published_evidence_rejected(tmp_path, change):
    ref, root, rec, spec = fixture(tmp_path)
    if change == "producer":
        rec["used_files"].pop(str(root / EVIDENCE_PRODUCERS[0]))
    elif change == "purpose":
        rec["action_review_allowed"] = True
    elif change == "patch":
        rec["patch"] = "7.42a"
    elif change == "output":
        rec["output_sha256"]["../escape.json"] = "a" * 64
    elif change == "cross_channel":
        old = spec["captures"][1]["receipt"]
        doc = json.loads(Path(old["path"]).read_text())
        doc["game_build"] = 6994
        spec["captures"][1]["receipt"] = write(Path(old["path"]), doc)
        rec["spec"] = write(Path(rec["spec"]["path"]), spec)
    else:
        p = Path(ref["path"]).parent / "camp-semantics.json"
        doc = json.loads(p.read_text())
        if change == "coverage":
            doc["match_ids"] = [123, 123]
        else:
            doc["source_refs"]["camp_assets"]["sha256"] = "a" * 64
        rec["output_sha256"][p.name] = write(p, doc)["sha256"]
    ref = write(Path(ref["path"]), rec)
    with pytest.raises(ValueError):
        open_decision_evidence(ref, repository_root=root, match_allowed=lambda _: True)


def test_forged_allowed_receipt_cannot_read_an_excluded_manifest_payload(tmp_path, monkeypatch):
    ref, root, rec, spec = fixture(tmp_path)
    for refs in spec["captures"]:
        path = Path(refs["receipt"]["path"])
        row = json.loads(path.read_text())
        manifest_path = Path(row["manifest"]["path"])
        manifest = json.loads(manifest_path.read_text())
        manifest["identity"]["match_id"] = 999
        row["manifest"] = write(manifest_path, manifest)
        refs["receipt"] = write(path, row)
    rec["spec"] = write(Path(rec["spec"]["path"]), spec)
    ref = write(Path(ref["path"]), rec)
    touched = []
    original = module.EvidencePins.add

    def guard(self, reference):
        touched.append(reference["path"])
        if reference["path"].startswith(str(root)):
            raise AssertionError("producer/payload reads occurred before actual identity check")
        return original(self, reference)

    monkeypatch.setattr(module.EvidencePins, "add", guard)
    with pytest.raises(ValueError, match="Manifest match excluded"):
        open_decision_evidence(ref, repository_root=root, match_allowed=lambda mid: mid == 123)
    assert not any("/capture.json" in name for name in touched)


def test_unreferenced_top_level_payload_rejected_before_read(tmp_path, monkeypatch):
    ref, root, rec, _ = fixture(tmp_path)
    unrelated = tmp_path / "unreferenced.dem"
    rec["used_files"][str(unrelated)] = "e" * 64
    ref = write(Path(ref["path"]), rec)
    original = module.EvidencePins.add

    def guard(self, reference):
        assert reference["path"] != str(unrelated), "unreferenced payload read"
        return original(self, reference)

    monkeypatch.setattr(module.EvidencePins, "add", guard)
    with pytest.raises(ValueError, match="Unexpected or incomplete"):
        open_decision_evidence(ref, repository_root=root, match_allowed=lambda _: True)
