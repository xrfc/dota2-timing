"""Publish camp semantics, observed objective cycles and explicit vision coverage."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.map_snapshot import FILES as MAP_FILES
from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.data.patch_assets import verify_patch_assets
from dota_items.data.patch_camp_semantics import build_camp_semantics
from dota_items.data.patch_evidence_io import producer_files, read_evidence_capture
from dota_items.data.patch_objective_cycles import analyze_objective_evidence
from dota_items.data.patch_objectives import build_camp_assets
from dota_items.data.patch_vision_evidence import analyze_vision_evidence
from dota_items.data.source_io import read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_FILES = tuple(
    sorted(
        set(producer_files("objectives") + producer_files("vision"))
        | {
            "scripts/build_patch_evidence.py",
            "src/dota_items/data/patch_assets.py",
            "src/dota_items/data/map_snapshot.py",
            "src/dota_items/data/mechanics_candidate.py",
            "src/dota_items/data/patch_camp_semantics.py",
            "src/dota_items/data/patch_objective_cycles.py",
            "src/dota_items/data/patch_objectives.py",
            "src/dota_items/data/patch_vision_evidence.py",
        }
    )
)
TEXTS = {
    "official_notes": "knowledge/mechanics/reviews/patch-update-2026-11-19/notes/"
    "datafeed-7.42-english.json",
    "historical_patchnotes": "knowledge/mechanics/reviews/patch-update-2026-11-19/notes/"
    "patchnotes_english.txt",
    "localization": "knowledge/game-files/snapshots/2026-11-19/sources/resource/localization/"
    "abilities_english.txt",
}


def read_base(ref, pins):
    receipt = pins.read(ref)
    if (
        receipt.get("schema") != "patch-review-assets-receipt/1"
        or receipt.get("exact_patch") != "7.42"
        or receipt.get("training_allowed") is not False
        or receipt.get("action_review_allowed") is not False
        or not receipt.get("used_files")
        or not receipt.get("output_sha256")
    ):
        raise ValueError("Invalid baseline asset receipt")
    for name, digest in receipt["used_files"].items():
        pins.add({"path": name, "sha256": digest})
    for name, digest in receipt["output_sha256"].items():
        if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Invalid baseline output path")
        pins.add({"path": str(Path(ref["path"]).parent / name), "sha256": digest})
    return receipt


def _add_capture(captures, identities, doc, receipt, manifest):
    identity = {
        "manifest": receipt["manifest"],
        "demo_sha256": receipt["demo_sha256"],
        "patch": doc["patch"],
        "game_build": doc["game_build"],
        "post_game_tick": doc["post_game_tick"],
        "duration": manifest["quality"]["base"]["metadata_duration"],
    }
    mid = doc["match_id"]
    if mid in identities and identities[mid] != identity:
        raise ValueError("Conflicting cross-channel replay identity")
    channel = captures[doc["schema"]]
    if mid in channel:
        raise ValueError("Duplicate supplementary capture")
    identities[mid] = identity
    channel[mid] = doc


def run(spec_path, output, *, repository_root=ROOT):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    pins = EvidencePins()
    for name in PRODUCER_FILES:
        pins.track(repository_root / name)
    spec_ref = pins.track(Path(spec_path).absolute())
    spec = pins.read(spec_ref)
    if (
        set(spec) != {"schema", "exact_patch", "base_receipt", "captures"}
        or spec["schema"] != "patch-evidence-assets-spec/1"
        or spec["exact_patch"] != "7.42"
        or not isinstance(spec["captures"], list)
        or not spec["captures"]
    ):
        raise ValueError("Invalid evidence asset specification")
    base = read_base(spec["base_receipt"], pins)
    binding = verify_patch_assets(
        base["binding"], exact_patch="7.42", repository_root=repository_root
    )
    documents = {name: binding.map.read(name) for name in MAP_FILES}
    captures = {"map-objective-evidence/1": {}, "map-vision-evidence/1": {}}
    identities = {}
    for refs in spec["captures"]:
        if not isinstance(refs, dict) or set(refs) != {"capture", "receipt"}:
            raise ValueError("Capture and receipt both required")
        doc = read_evidence_capture(
            refs["capture"],
            refs["receipt"],
            pins=pins,
            repository_root=repository_root,
            match_allowed=lambda mid: not is_holdout(mid),
        )
        receipt = pins.read(refs["receipt"])
        manifest = pins.read(receipt["manifest"])
        _add_capture(captures, identities, doc, receipt, manifest)
    objectives = captures["map-objective-evidence/1"]
    visions = captures["map-vision-evidence/1"]
    if not objectives or objectives.keys() != visions.keys():
        raise ValueError("Objective and vision match coverage must agree")
    texts, refs = {}, {"base": spec["base_receipt"], "captures": spec["captures"]}
    for key, name in TEXTS.items():
        ref = pins.track(repository_root / name)
        refs[key] = ref
        raw = read_source_bytes(Path(ref["path"]))
        if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("Evidence text changed during read")
        texts[key] = raw.decode("utf-8-sig")
    notes = pins.read(refs["official_notes"])
    runtime = [{**doc, "schema": "map-runtime-capture/1"} for doc in objectives.values()]
    camps = build_camp_assets(
        documents, runtime, exact_patch="7.42", source_refs=refs, official_notes=notes
    )
    refs["camp_assets"] = {
        "path": str(output / "camp-observations.json"),
        "sha256": hashlib.sha256(
            (json.dumps(camps, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        ).hexdigest(),
    }
    semantics = build_camp_semantics(
        camps,
        runtime,
        notes,
        texts["historical_patchnotes"],
        texts["localization"],
        exact_patch="7.42",
        source_refs=refs,
    )
    payloads = {
        "camp-observations.json": camps,
        "camp-semantics.json": semantics,
        "objective-cycles.json": analyze_objective_evidence(
            list(objectives.values()),
            map_documents=documents,
            exact_patch="7.42",
            source_refs=refs,
        ),
        "vision-evidence.json": {
            "schema": "patch-vision-evidence-batch/1",
            "patch": "7.42",
            "source_refs": refs,
            "matches": [
                analyze_vision_evidence(
                    doc, expected_duration=identities[doc["match_id"]]["duration"]
                )
                for doc in visions.values()
            ],
            "training_allowed": False,
            "action_review_allowed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".patch-evidence-assets-", dir=output.parent) as temp:
        staging = Path(temp) / "result"
        staging.mkdir()
        for name, doc in payloads.items():
            (staging / name).write_text(
                json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            )
        binding.verify_again()
        pins.verify()
        receipt = {
            "schema": "patch-evidence-assets-receipt/1",
            "patch": "7.42",
            "spec": spec_ref,
            "used_files": pins.inventory,
            "output_sha256": {p.name: file_hash(p) for p in sorted(staging.iterdir())},
            "training_allowed": False,
            "action_review_allowed": False,
        }
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        publish_directory(staging, output)
    return {"matches": len(objectives), "outputs": len(payloads), "inputs": len(pins.inventory)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.spec, args.output)))


if __name__ == "__main__":
    main()
