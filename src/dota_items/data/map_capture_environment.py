"""Pinned replay preparation independent of CLI and product-line policy.

New-capture-only extraction of capture_map_runtime.prepare. Old receipts stay strict;
this does not re-label old output as having been produced by the new implementation.
"""

from importlib.metadata import version
from pathlib import Path

from dota_items.data.map_replay_source import open_geometry_source, read_landmark_capture


def prepare_capture_environment(spec_path, pins, *, match_allowed):
    spec_ref = pins.track(spec_path)
    spec = pins.read(spec_ref)
    if (
        not isinstance(spec, dict)
        or set(spec) != {"schema", "capture_kind", "exact_patch", "replay", "landmarks", "compat"}
        or spec["schema"] != "map-runtime-capture-spec/1"
    ):
        raise ValueError("Invalid runtime capture specification")
    if spec["capture_kind"] not in {"runtime", "visibility"}:
        raise ValueError("Unknown map capture kind")
    ref = spec["replay"]
    source = open_geometry_source(
        ref["path"],
        expected_sha256=ref["sha256"],
        exact_patch=spec["exact_patch"],
        match_allowed=match_allowed,
    )
    old = spec["landmarks"]
    if not isinstance(old, dict) or set(old) != {"capture", "receipt"}:
        raise ValueError("Both original landmark output and receipt are required")
    landmark = read_landmark_capture(old["capture"], old["receipt"], replay_source=source)
    pins.read(old["capture"])
    receipt = pins.read(old["receipt"])
    for inventory in (source.receipt()["used_files"], receipt["used_files"]):
        for name, digest in inventory.items():
            pins.add({"path": name, "sha256": digest})
    manifest = pins.read(ref)
    demos = [
        Path(item["path"])
        for item in manifest["identity"]["source_references"]
        if Path(item["path"]).name
        in {
            f"{source.match_id}.dem",
            f"{source.match_id}.dem.bz2",
            f"{source.match_id}.dem.zst",
            f"{source.match_id}.dem.zip",
        }
    ]
    if len(demos) != 1 or str(demos[0]) not in pins.inventory:
        raise ValueError("Original pinned replay archive is missing or ambiguous")
    archive_ref = next(
        item for item in manifest["identity"]["source_references"] if item["path"] == str(demos[0])
    )
    pins.add({"path": archive_ref["path"], "sha256": archive_ref["sha256"]})
    if (
        type(archive_ref.get("size_bytes")) is not int
        or archive_ref["size_bytes"] <= 0
        or demos[0].stat().st_size != archive_ref["size_bytes"]
    ):
        raise ValueError("Original replay archive size mismatch")
    compat = Path(spec["compat"])
    if not compat.is_absolute() or compat.resolve() != compat or compat.is_symlink():
        raise ValueError("Compatibility directory must be canonical and absolute")
    cm_path = compat / "manifest.json"
    cm_digest = manifest["producer"]["parser"]["manifest_sha256"]
    cm = pins.read({"path": str(cm_path), "sha256": cm_digest})
    if cm.get("schema") != "gem-isolated-backport/1" or cm.get("base_version") != "0.10.0":
        raise ValueError("Unsupported compatibility source")
    # Inventory is inherited from the previous fresh capture, including JSON resources.
    expected = {
        Path(name).relative_to(compat / "gem").as_posix(): digest
        for name, digest in receipt["used_files"].items()
        if Path(name).is_relative_to(compat / "gem")
    }
    actual = {
        p.relative_to(compat / "gem").as_posix()
        for p in (compat / "gem").rglob("*")
        if p.suffix in {".py", ".json"}
    }
    if (
        actual != set(expected)
        or not expected
        or {k: v for k, v in expected.items() if k.endswith(".py")} != cm.get("patched")
    ):
        raise ValueError("Compatibility source/resource inventory changed")
    dependencies = receipt.get("dependencies")
    if (
        not isinstance(dependencies, dict)
        or not dependencies
        or dependencies != manifest["producer"].get("dependencies")
        or any(version(name) != value for name, value in dependencies.items())
    ):
        raise ValueError("Runtime dependencies differ from pinned capture")
    return spec, source, landmark, demos[0], compat, expected, dependencies
