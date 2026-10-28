"""Offline isolated reparse for direct coordinate identity and replay-native landmarks."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from dota_items.data.replay_identity import compare_positions
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.replay_identity import instrument_players
from dota_items.storage import file_hash


def read(path):
    return parse_source_json(read_source_bytes(path, max_bytes=512 * 1024**2))


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)


def run(archive, receipt, preparation, compat, output):
    if output.exists():
        raise ValueError("Output already exists")
    if "gem" in sys.modules:
        raise ValueError("Run in a fresh process; Gem is already imported")
    manifest_path = compat / "manifest.json"
    manifest = read(manifest_path)
    frozen = read(preparation / "manifest.json")
    expected_archive = read(receipt)["archive_sha256"]
    if file_hash(archive) != expected_archive:
        raise ValueError("Archive hash mismatch")
    if file_hash(preparation / "raw.json") != frozen["files"]["raw.json"]:
        raise ValueError("Frozen raw hash mismatch")
    actual_sources = {str(p.relative_to(compat / "gem")) for p in (compat / "gem").rglob("*.py")}
    if actual_sources != set(manifest["patched"]):
        raise ValueError("Compatibility source file set mismatch")
    for name, expected in manifest["patched"].items():
        if file_hash(compat / "gem" / name) != expected:
            raise ValueError(f"Compatibility source hash mismatch: {name}")
    raw = read(preparation / "raw.json")
    if raw["match_id"] != frozen["match_id"]:
        raise ValueError("Manifest identity mismatch")
    code_root = Path(__file__).resolve().parents[1]
    tracked = [
        archive,
        receipt,
        preparation / "manifest.json",
        preparation / "raw.json",
        manifest_path,
        Path(__file__),
        *[
            code_root / "src/dota_items" / name
            for name in (
                "sources/replay_identity.py",
                "data/replay_identity.py",
                "sources/gem_replay.py",
                "data/source_io.py",
                "storage.py",
            )
        ],
        *[compat / "gem" / name for name in manifest["patched"]],
    ]
    before = {str(p): file_hash(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    private = output / "instrumented"
    shutil.copytree(
        compat / "gem", private / "gem", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    source = private / "gem/extractors/players.py"
    source.write_text(instrument_players(source.read_text()))
    private_hashes = {
        str(p.relative_to(private)): file_hash(p) for p in sorted(private.rglob("*.py"))
    }
    save(
        output / "execution.json",
        {"inputs_and_code": before, "instrumented": private_hashes, "training_executed": False},
    )
    sys.path.insert(0, str(private.resolve()))
    import gem

    from dota_items.sources.gem_replay import prepared_demo
    from dota_items.sources.replay_identity import capture

    if Path(gem.__file__).resolve().parent != (private / "gem").resolve():
        raise ValueError("Wrong Gem loaded")
    with prepared_demo(archive, output / "scratch") as demo:
        demo_hash = file_hash(demo)
        captured = capture(demo)
    save(output / "capture.json", captured)
    audit = compare_positions(raw, captured)
    if before != {str(p): file_hash(p) for p in tracked}:
        raise ValueError("Input or implementation drift during audit")
    if private_hashes != {
        str(p.relative_to(private)): file_hash(p) for p in sorted(private.rglob("*.py"))
    }:
        raise ValueError("Instrumented source drift")
    audit["provenance"] = {
        "raw_sha256": before[str(preparation / "raw.json")],
        "capture_sha256": file_hash(output / "capture.json"),
        "demo_sha256": demo_hash,
        "execution_sha256": file_hash(output / "execution.json"),
    }
    save(output / "audit.json", audit)
    save(
        output / "receipt.json",
        {"audit_sha256": file_hash(output / "audit.json"), "status": "source-consistency-verified"},
    )
    return {
        "match_id": audit["match_id"],
        "positions": audit["positions_compared"],
        "noncanonical": sum(p["noncanonical_samples"] for p in audit["players"]),
        "landmark_records": len(audit["landmarks"]),
        "game_build": audit["game_build"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "receipt", "preparation", "compat", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    print(json.dumps(run(**vars(parser.parse_args()))))
