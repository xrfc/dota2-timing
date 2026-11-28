"""Prepare, capture and publish viewer wire evidence; CLI-independent orchestration."""

import json
import shutil
import sys
import tempfile
import time
from itertools import chain
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.map_capture_environment import prepare_capture_environment
from dota_items.data.map_tree_probe_io import MAX_PROBE_BYTES
from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.data.viewer_wire_io import (
    MIGRATION,
    open_viewer_anchor,
    validate_viewer_capture,
    viewer_producer_files,
)
from dota_items.sources.gem_replay import prepared_demo
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[4]


def _write_bounded_capture(path, payload):
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    written = 0
    with path.open("wb") as stream:
        for piece in chain(encoder.iterencode(payload), ("\n",)):
            encoded = piece.encode("utf-8")
            written += len(encoded)
            if written > MAX_PROBE_BYTES:
                raise ValueError("Raw tree probe payload exceeds its 256 MiB limit")
            stream.write(encoded)


def run(spec_path, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    if any(name == "gem" or name.startswith("gem.") for name in sys.modules):
        raise ValueError("Fresh process required")
    pins = EvidencePins()
    spec_ref = pins.track(Path(spec_path).absolute())
    spec = pins.read(spec_ref)
    source, anchor, old = open_viewer_anchor(
        spec, pins=pins, repository_root=ROOT, match_allowed=lambda mid: not is_holdout(mid)
    )
    for name in viewer_producer_files():
        pins.track(ROOT / name)
    _, _, _, archive, compat, files, dependencies = prepare_capture_environment(
        Path(old["spec"]["path"]), pins, match_allowed=lambda mid: not is_holdout(mid)
    )
    from dota_items.sources.viewer_wire_capture import capture

    initial = pins.inventory
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tree-probe-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        private, staging = temporary / "private", temporary / "result"
        staging.mkdir()
        for name, digest in files.items():
            target = private / "gem" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(compat / "gem" / name, target)
            if file_hash(target) != digest:
                raise ValueError("Private parser copy changed")
        sys.path.insert(0, str(private))
        import gem

        if Path(gem.__file__).resolve() != private / "gem/__init__.py":
            raise ValueError("Unexpected parser import")
        with prepared_demo(archive, temporary / "scratch") as demo:
            digest = file_hash(demo)
            if digest != old["demo_sha256"]:
                raise ValueError("Decompressed original replay mismatch")
            started = time.monotonic()
            result = capture(
                demo, expected_match_id=source.match_id, expected_game_build=source.build
            )
            elapsed = time.monotonic() - started
            if file_hash(demo) != digest:
                raise ValueError("Replay changed during parse")
        validate_viewer_capture(result, source=source, anchor=anchor)
        result.update(
            patch=source.patch, omniscient=True, training_allowed=False, action_review_allowed=False
        )
        _write_bounded_capture(staging / "capture.json", result)
        prepare_capture_environment(
            Path(old["spec"]["path"]), pins, match_allowed=lambda mid: not is_holdout(mid)
        )
        if pins.inventory != initial:
            raise ValueError("Probe input inventory changed")
        pins.verify()
        for name, digest in files.items():
            if file_hash(private / "gem" / name) != digest:
                raise ValueError("Private parser changed")
        receipt = {
            "schema": "viewer-wire-receipt/1",
            "migration": MIGRATION,
            "spec": spec_ref,
            "anchor": spec["anchor"],
            "manifest": old["manifest"],
            "match_id": source.match_id,
            "patch": source.patch,
            "game_build": source.build,
            "demo_sha256": old["demo_sha256"],
            "dependencies": dependencies,
            "used_files": initial,
            "output_sha256": {"capture.json": file_hash(staging / "capture.json")},
            "parse_elapsed_seconds": elapsed,
            "training_allowed": False,
            "action_review_allowed": False,
        }
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        publish_directory(staging, output)
    return {
        key: receipt[key] for key in ("match_id", "patch", "game_build", "parse_elapsed_seconds")
    }
