"""Strict source and producer closure for supplementary raw tree probes."""

import hashlib
from importlib.metadata import version
from pathlib import Path

from dota_items.data.patch_asset_evidence import decode_json, validate_ref
from dota_items.data.patch_evidence_io import open_anchor, producer_files
from dota_items.data.source_io import AuditInputError, read_source_bytes

MAX_PROBE_BYTES = 256 * 1024 * 1024

# Existing engineering captures only. A new source needs an explicit registration;
# this inventory does not override the caller's match scope or final-holdout gate.
REGISTERED_ANCHORS = {
    9103406291: {
        "directory": "reports/patch742-consumers-20261127/visibility-r3/9103406291",
        "sha256": "f506a7924f678b90440ccc1e344f56cb2b6b32d22ba7677b5e244e48bd1f7d8d",
    },
    9103406692: {
        "directory": "reports/patch742-consumers-20261127/visibility-r3/9103406692",
        "sha256": "db3faa1aa2322c1c7e9826a486d8a5ea1f093ce28aee8056e0745854d73f6457",
    },
    9103406760: {
        "directory": "reports/patch742-consumers-20261127/visibility-r3/9103406760",
        "sha256": "12b52202a959199881b6d47dc0dc7921f82c73dca777b21d92686f3ef301c0cc",
    },
    9103407326: {
        "directory": "reports/patch742-consumers-20261127/visibility-r3/9103407326",
        "sha256": "7163ead2da2452427a6764b309a82a4b47e06370cb8779b742a409f290813ebb",
    },
    9103408009: {
        "directory": "reports/patch742-consumers-20261127/visibility-r3/9103408009",
        "sha256": "beb6d5618a6758a2d7038e35235351a4967c1728b1eb14226203a225147f8800",
    },
    9103393259: {
        "directory": "reports/patch742-evidence-20261127/visibility-long-r1/9103393259",
        "sha256": "73193c9218c25d7423091b474ff9e73ec2c9df3979cbd7fac9d49ed3bb923230",
    },
    9103393854: {
        "directory": "reports/patch742-evidence-20261127/visibility-long-r1/9103393854",
        "sha256": "4c360c5f0e7a7e8bb64fde0e39efd3349e0af06c13aa2f3359ce3afc4a76a3d9",
    },
    9103395615: {
        "directory": "reports/patch742-evidence-20261127/visibility-long-r1/9103395615",
        "sha256": "22329f0c2bece1333de83b6854af317d4e07213c90aef0fbab1e053cf32e9ab2",
    },
}


def tree_probe_producer_files():
    return producer_files("vision") + (
        "scripts/capture_tree_probe.py",
        "src/dota_items/data/map_tree_probe_io.py",
        "src/dota_items/sources/map_tree_probe.py",
    )


def open_tree_anchor(spec, *, pins, repository_root, match_allowed, claimed_match_id=None):
    if (
        not isinstance(spec, dict)
        or set(spec) != {"schema", "exact_patch", "anchor"}
        or spec["schema"] != "map-tree-probe-spec/1"
        or spec["exact_patch"] != "7.42"
        or not isinstance(spec["anchor"], dict)
        or set(spec["anchor"]) != {"capture", "receipt"}
    ):
        raise ValueError("Invalid raw tree probe specification")
    receipt_ref, capture_ref = spec["anchor"]["receipt"], spec["anchor"]["capture"]
    root = Path(repository_root).resolve()
    registration = [
        (mid, root / entry["directory"])
        for mid, entry in REGISTERED_ANCHORS.items()
        if receipt_ref
        == {
            "path": str(root / entry["directory"] / "receipt.json"),
            "sha256": entry["sha256"],
        }
    ]
    if len(registration) != 1:
        raise ValueError("Unregistered raw tree probe visibility anchor")
    registered_mid, directory = registration[0]
    old = pins.read(receipt_ref)
    if (
        not isinstance(old, dict)
        or type(old.get("match_id")) is not int
        or old["match_id"] != registered_mid
        or not isinstance(capture_ref, dict)
        or set(capture_ref) != {"path", "sha256"}
        or capture_ref.get("path") != str(directory / "capture.json")
        or old.get("output_sha256") != {"capture.json": capture_ref.get("sha256")}
    ):
        raise ValueError("Registered raw tree probe anchor identity or output binding mismatch")

    def permitted(actual):
        claims = [old.get("match_id")]
        if claimed_match_id is not None:
            claims.append(claimed_match_id)
        if any(type(mid) is not int or mid != actual for mid in claims):
            raise ValueError("Raw tree probe claimed match identity mismatch")
        return match_allowed(actual)

    # The existing visibility anchor already closes the real replay identity,
    # final-holdout exclusion, original archive and immutable parser sources.
    return open_anchor(
        {**spec, "schema": "patch-evidence-capture-spec/1", "kind": "vision"},
        pins=pins,
        repository_root=repository_root,
        match_allowed=permitted,
    )


def validate_probe_header(doc, *, source, anchor):
    if (
        not isinstance(doc, dict)
        or doc.get("schema") != "map-tree-probe/1"
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
        or doc.get("coordinate_space") != "world"
    ):
        raise ValueError("Raw tree probe identity or completion mismatch")


def read_tree_probe(capture_ref, receipt_ref, *, pins, repository_root, match_allowed):
    receipt = pins.read(receipt_ref)
    if not isinstance(receipt, dict) or receipt.get("schema") != "map-tree-probe-receipt/1":
        raise ValueError("Invalid raw tree probe receipt")
    if type(receipt.get("match_id")) is not int or receipt["match_id"] <= 0:
        raise ValueError("Invalid raw tree probe match identity")
    spec_ref = receipt.get("spec")
    spec = pins.read(spec_ref)
    source, anchor, old = open_tree_anchor(
        spec,
        pins=pins,
        repository_root=repository_root,
        match_allowed=match_allowed,
        claimed_match_id=receipt["match_id"],
    )
    # Resolve actual manifest identity and exclusions before opening probe bytes.
    if (
        type(receipt.get("match_id")) is not int
        or receipt["match_id"] != source.match_id
        or type(receipt.get("game_build")) is not int
        or receipt["game_build"] != source.build
        or receipt.get("patch") != source.patch
        or receipt.get("anchor") != spec["anchor"]
        or receipt.get("manifest") != old["manifest"]
        or receipt.get("demo_sha256") != old["demo_sha256"]
        or receipt.get("output_sha256") != {"capture.json": capture_ref["sha256"]}
        or receipt.get("dependencies") != old["dependencies"]
        or any(version(name) != value for name, value in old["dependencies"].items())
        or receipt.get("training_allowed") is not False
        or receipt.get("action_review_allowed") is not False
    ):
        raise ValueError("Raw tree probe receipt identity, purpose or dependencies mismatch")
    required = {**old["used_files"], spec_ref["path"]: spec_ref["sha256"]}
    for ref in spec["anchor"].values():
        required[ref["path"]] = ref["sha256"]
    for name in tree_probe_producer_files():
        ref = pins.track(Path(repository_root) / name)
        required[ref["path"]] = ref["sha256"]
    if receipt.get("used_files") != required:
        raise ValueError("Raw tree probe producer/source inventory differs from exact closure")
    for name, digest in required.items():
        pins.add({"path": name, "sha256": digest})
    path = validate_ref(capture_ref)
    try:
        raw = read_source_bytes(path, max_bytes=MAX_PROBE_BYTES)
    except AuditInputError as exc:
        raise ValueError("Raw tree probe payload exceeds its 256 MiB limit") from exc
    if hashlib.sha256(raw).hexdigest() != capture_ref["sha256"]:
        raise ValueError("Raw tree probe payload digest mismatch")
    pins.add(capture_ref)
    doc = decode_json(raw)
    validate_probe_header(doc, source=source, anchor=anchor)
    if (
        doc.get("patch") != source.patch
        or doc.get("omniscient") is not True
        or doc.get("training_allowed") is not False
        or doc.get("action_review_allowed") is not False
    ):
        raise ValueError("Raw tree probe purpose mismatch")
    return doc
