"""Strict supplementary capture receipts anchored to previously verified evidence."""

from importlib.metadata import version
from pathlib import Path

from dota_items.data.map_replay_source import open_geometry_source
from dota_items.data.patch_asset_evidence import capture_producer_files, read_fresh_capture

KINDS = {
    "objectives": ("runtime", "map-objective-evidence/1", "map_objective_evidence"),
    "vision": ("visibility", "map-vision-evidence/1", "map_vision_evidence"),
}


def producer_files(kind):
    if kind not in KINDS:
        raise ValueError("Unknown supplementary capture kind")
    anchor_kind, _, module = KINDS[kind]
    return capture_producer_files(anchor_kind) + (
        "scripts/capture_patch_evidence.py",
        "src/dota_items/data/patch_evidence_io.py",
        f"src/dota_items/sources/{module}.py",
    )


def open_anchor(spec, *, pins, repository_root, match_allowed):
    if (
        not isinstance(spec, dict)
        or set(spec) != {"schema", "kind", "exact_patch", "anchor"}
        or spec["schema"] != "patch-evidence-capture-spec/1"
        or spec["kind"] not in KINDS
        or spec["exact_patch"] != "7.42"
        or not isinstance(spec["anchor"], dict)
        or set(spec["anchor"]) != {"capture", "receipt"}
    ):
        raise ValueError("Invalid supplementary capture specification")
    refs = spec["anchor"]
    receipt = pins.read(refs["receipt"])
    manifest = receipt["manifest"]
    source = open_geometry_source(
        manifest["path"],
        expected_sha256=manifest["sha256"],
        exact_patch=spec["exact_patch"],
        match_allowed=match_allowed,
    )
    doc = read_fresh_capture(
        refs["capture"],
        refs["receipt"],
        source=source,
        pins=pins,
        kind=KINDS[spec["kind"]][0],
        repository_root=repository_root,
    )
    return source, doc, receipt


def read_evidence_capture(capture_ref, receipt_ref, *, pins, repository_root, match_allowed):
    receipt = pins.read(receipt_ref)
    if receipt.get("schema") != "patch-evidence-capture-receipt/1":
        raise ValueError("Invalid supplementary receipt")
    spec_ref = receipt.get("spec")
    spec = pins.read(spec_ref)
    source, anchor, old = open_anchor(
        spec, pins=pins, repository_root=repository_root, match_allowed=match_allowed
    )
    doc = pins.read(capture_ref)
    expected = {
        "match_id": source.match_id,
        "patch": source.patch,
        "game_build": source.build,
    }
    if (
        doc.get("schema") != KINDS[spec["kind"]][1]
        or receipt.get("kind") != spec["kind"]
        or receipt.get("anchor") != spec["anchor"]
        or receipt.get("manifest") != old["manifest"]
        or receipt.get("demo_sha256") != old["demo_sha256"]
        or any(row.get(k) != v for row in (doc, receipt) for k, v in expected.items())
        or type(doc.get("post_game_tick")) is not int
        or doc["post_game_tick"] != anchor["post_game_tick"]
        or doc.get("parse_error") is not None
        or doc.get("truncated_at_tick") is not None
        or doc.get("coordinate_space") != "world"
        or doc.get("omniscient") is not True
        or any(row.get("training_allowed") is not False for row in (doc, receipt))
        or receipt.get("action_review_allowed") is not False
        or receipt.get("output_sha256") != {"capture.json": capture_ref["sha256"]}
        or receipt.get("dependencies") != old["dependencies"]
        or any(version(n) != v for n, v in old["dependencies"].items())
    ):
        raise ValueError("Supplementary capture identity, purpose or completion mismatch")
    required = {**old["used_files"], spec_ref["path"]: spec_ref["sha256"]}
    for ref in spec["anchor"].values():
        required[ref["path"]] = ref["sha256"]
    for name in producer_files(spec["kind"]):
        ref = pins.track(Path(repository_root) / name)
        required[ref["path"]] = ref["sha256"]
    used = receipt.get("used_files")
    if not isinstance(used, dict) or any(used.get(n) != h for n, h in required.items()):
        raise ValueError("Incomplete supplementary producer/source inventory")
    for name, digest in used.items():
        pins.add({"path": name, "sha256": digest})
    return doc
