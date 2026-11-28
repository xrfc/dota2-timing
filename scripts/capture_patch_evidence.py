"""Capture supplementary objective or vision evidence in a private pinned parser."""

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.data.patch_evidence_io import KINDS, open_anchor, producer_files
from dota_items.sources.gem_replay import prepared_demo
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


def run(spec_path, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    if any(name == "gem" or name.startswith("gem.") for name in sys.modules):
        raise ValueError("Fresh process required")
    pins = EvidencePins()
    spec_ref = pins.track(Path(spec_path).absolute())
    spec = pins.read(spec_ref)
    source, anchor, old = open_anchor(
        spec, pins=pins, repository_root=ROOT, match_allowed=lambda mid: not is_holdout(mid)
    )
    for name in producer_files(spec["kind"]):
        pins.track(ROOT / name)
    module_spec = importlib.util.spec_from_file_location(
        "pinned_runtime_cli", ROOT / "scripts/capture_map_runtime.py"
    )
    legacy = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(legacy)
    _, _, _, archive, compat, files, dependencies = legacy.prepare(Path(old["spec"]["path"]), pins)
    if spec["kind"] == "objectives":
        from dota_items.sources.map_objective_evidence import capture
    else:
        from dota_items.sources.map_vision_evidence import capture
    initial = pins.inventory
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".patch-evidence-", dir=output.parent) as temp:
        temp = Path(temp)
        private, staging = temp / "private", temp / "result"
        staging.mkdir()
        for name, digest in files.items():
            target = private / "gem" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(compat / "gem" / name, target)
            if file_hash(target) != digest:
                raise ValueError("Parser copy changed")
        sys.path.insert(0, str(private))
        import gem

        if Path(gem.__file__).resolve() != private / "gem/__init__.py":
            raise ValueError("Unexpected parser import")
        with prepared_demo(archive, temp / "scratch") as demo:
            digest = file_hash(demo)
            if digest != old["demo_sha256"]:
                raise ValueError("Decompressed original replay mismatch")
            result = capture(demo)
            if file_hash(demo) != digest:
                raise ValueError("Replay changed during parse")
        if (
            result.get("schema") != KINDS[spec["kind"]][1]
            or any(result.get(k) != anchor[k] for k in ("match_id", "game_build", "post_game_tick"))
            or result.get("parse_error") is not None
            or result.get("truncated_at_tick") is not None
        ):
            raise ValueError("Capture identity/completion differs from verified anchor")
        result.update(patch=source.patch, omniscient=True, training_allowed=False)
        (staging / "capture.json").write_text(
            json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        )
        legacy.prepare(Path(old["spec"]["path"]), pins)
        if pins.inventory != initial:
            raise ValueError("Capture inventory changed")
        pins.verify()
        for name, digest in files.items():
            if file_hash(private / "gem" / name) != digest:
                raise ValueError("Private parser changed")
        receipt = {
            "schema": "patch-evidence-capture-receipt/1",
            "kind": spec["kind"],
            "spec": spec_ref,
            "anchor": spec["anchor"],
            "manifest": old["manifest"],
            "match_id": source.match_id,
            "patch": source.patch,
            "game_build": source.build,
            "demo_sha256": old["demo_sha256"],
            "dependencies": dependencies,
            "used_files": pins.inventory,
            "output_sha256": {"capture.json": file_hash(staging / "capture.json")},
            "training_allowed": False,
            "action_review_allowed": False,
        }
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        publish_directory(staging, output)
    return {k: receipt[k] for k in ("kind", "match_id", "patch", "game_build")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.spec, args.output)))


if __name__ == "__main__":
    main()
