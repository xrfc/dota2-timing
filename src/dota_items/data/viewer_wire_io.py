"""Strict new-capture-only preparation migration and viewer receipt reader."""

import hashlib
from pathlib import Path

from dota_items.data.map_tree_probe_io import MAX_PROBE_BYTES, open_tree_anchor
from dota_items.data.patch_asset_evidence import decode_json, validate_ref
from dota_items.data.patch_evidence_io import producer_files
from dota_items.data.source_io import read_source_bytes

# Filled from the reviewed frozen predecessor, not accepted as an arbitrary old hash.
LEGACY_PREPARE_SHA256 = "b5b16f78d4c4330e9909c98a7ab5bc31e1fb2fde4cdb3ffc3a27e1fde032504b"
MIGRATION = {
    "id": "pinned-capture-preparation/1",
    "mode": "new-capture-only",
    "predecessor": "scripts/capture_map_runtime.py",
    "predecessor_sha256": LEGACY_PREPARE_SHA256,
    "replacement": "src/dota_items/data/map_capture_environment.py",
    "old_output_relabeling_allowed": False,
}


def viewer_producer_files():
    return producer_files("vision") + (
        "src/dota_items/data/map_tree_probe_io.py",
        "src/dota_items/data/map_capture_environment.py",
        "src/dota_items/data/viewer_wire_io.py",
        "src/dota_items/sources/viewer_wire_capture.py",
        "src/dota_items/experiments/__init__.py",
        "src/dota_items/experiments/awareness/__init__.py",
        "src/dota_items/experiments/awareness/viewer_capture.py",
        "scripts/capture_viewer_wire.py",
    )


def open_viewer_anchor(spec, *, pins, repository_root, match_allowed, claimed_match_id=None):
    if not isinstance(spec, dict) or spec.get("schema") != "viewer-wire-spec/1":
        raise ValueError("Invalid viewer wire spec")
    source, anchor, old = open_tree_anchor(
        {**spec, "schema": "map-tree-probe-spec/1"},
        pins=pins,
        repository_root=repository_root,
        match_allowed=match_allowed,
        claimed_match_id=claimed_match_id,
    )
    legacy = str(Path(repository_root) / MIGRATION["predecessor"])
    if old["used_files"].get(legacy) != LEGACY_PREPARE_SHA256:
        raise ValueError("Unregistered preparation predecessor")
    return source, anchor, old


def validate_viewer_capture(doc, *, source, anchor):
    if (
        not isinstance(doc, dict)
        or doc.get("schema") != "viewer-wire-capture/1"
        or any(
            type(doc.get(key)) is not int or doc[key] != value
            for key, value in {
                "match_id": source.match_id,
                "game_build": source.build,
                "post_game_tick": anchor["post_game_tick"],
            }.items()
        )
        or "parse_error" not in doc
        or doc["parse_error"] is not None
        or "truncated_at_tick" not in doc
        or doc["truncated_at_tick"] is not None
        or doc.get("action_review_allowed") is not False
        or doc.get("training_allowed") is not False
        or doc.get("coordinate_space") != "raw_uninterpreted"
        or type(doc.get("terminal_packet_ordinal")) is not int
        or doc["terminal_packet_ordinal"] <= 0
    ):
        raise ValueError("Viewer capture identity/completion/purpose mismatch")


def read_viewer_capture(capture_ref, receipt_ref, *, pins, repository_root, match_allowed):
    receipt = pins.read(receipt_ref)
    if not isinstance(receipt, dict) or receipt.get("schema") != "viewer-wire-receipt/1":
        raise ValueError("Invalid viewer receipt")
    spec = pins.read(receipt["spec"])
    source, anchor, old = open_viewer_anchor(
        spec,
        pins=pins,
        repository_root=repository_root,
        match_allowed=match_allowed,
        claimed_match_id=receipt.get("match_id"),
    )
    expected = {**old["used_files"], receipt["spec"]["path"]: receipt["spec"]["sha256"]}
    for ref in spec["anchor"].values():
        expected[ref["path"]] = ref["sha256"]
    for name in viewer_producer_files():
        ref = pins.track(Path(repository_root) / name)
        expected[ref["path"]] = ref["sha256"]
    if (
        receipt.get("used_files") != expected
        or receipt.get("migration") != MIGRATION
        or receipt.get("manifest") != old["manifest"]
        or receipt.get("anchor") != spec["anchor"]
        or receipt.get("dependencies") != old["dependencies"]
        or receipt.get("demo_sha256") != old["demo_sha256"]
        or receipt.get("output_sha256") != {"capture.json": capture_ref.get("sha256")}
        or type(receipt.get("match_id")) is not int
        or receipt["match_id"] != source.match_id
        or type(receipt.get("game_build")) is not int
        or receipt["game_build"] != source.build
        or receipt.get("patch") != source.patch
        or receipt.get("training_allowed") is not False
        or receipt.get("action_review_allowed") is not False
    ):
        raise ValueError("Viewer receipt closure/migration mismatch")
    for path, digest in expected.items():
        pins.add({"path": path, "sha256": digest})
    raw = read_source_bytes(validate_ref(capture_ref), max_bytes=MAX_PROBE_BYTES)
    if hashlib.sha256(raw).hexdigest() != capture_ref["sha256"]:
        raise ValueError("Viewer capture digest mismatch")
    pins.add(capture_ref)
    doc = decode_json(raw)
    validate_viewer_capture(doc, source=source, anchor=anchor)
    if doc.get("patch") != source.patch or doc.get("omniscient") is not True:
        raise ValueError("Viewer capture patch/purpose mismatch")
    pins.verify()
    return doc
