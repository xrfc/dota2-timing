"""Bounded clean-only recovery from frozen normalized caches; no samples or training."""

import argparse
import gc
import json
import shutil
from pathlib import Path

from dota_items.data.cleaning import clean_match
from dota_items.data.contracts import PreparationConfig
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.data.validation import validate_match
from dota_items.storage import file_hash


def read(path):
    return parse_source_json(read_source_bytes(path, max_bytes=512 * 1024**2))


def run(root, mid, output):
    if output.exists():
        raise ValueError("Output exists")
    receipt_path = root / f"{mid}.receipt.json"
    receipt = read(receipt_path)
    cache = root / "workspaces" / str(mid) / "cache/matches" / receipt["archive_sha256"]
    cm = read(cache / "manifest.json")
    archive = root / f"{mid}.dem.bz2"
    if (
        file_hash(archive) != receipt["archive_sha256"]
        or cm["source_sha256"] != receipt["archive_sha256"]
        or cm["match_id"] != mid
    ):
        raise ValueError("Archive/cache identity mismatch")
    for name, key in [
        ("normalized.json", "normalized_json_sha256"),
        ("raw-gem.json", "raw_json_sha256"),
    ]:
        if file_hash(cache / name) != cm[key]:
            raise ValueError("Cache hash mismatch")
    config_path = root / "workspaces" / str(mid) / "preparation.json"
    config = PreparationConfig.model_validate(read(config_path))
    paths = [
        receipt_path,
        cache / "manifest.json",
        cache / "normalized.json",
        cache / "raw-gem.json",
        config_path,
        Path(__file__),
    ]
    paths += list(Path("src/dota_items/data").glob("*.py"))
    paths += [
        Path("src/dota_items/contracts/replay_context.py"),
        Path("src/dota_items/normalize.py"),
    ]
    before = {str(p): file_hash(p) for p in paths}
    output.mkdir(parents=True)
    (output / "execution.json").write_text(
        json.dumps(
            {
                "inputs_and_code": before,
                "read_limit_bytes": 512 * 1024**2,
                "config": config.model_dump(),
                "scope": "clean_only_no_samples",
            },
            indent=2,
        )
    )
    raw = read(cache / "normalized.json")
    if raw["match_id"] != mid:
        raise ValueError("Match mismatch")
    cleaned, quality = clean_match(raw, config)
    del raw
    gc.collect()
    shutil.copyfile(cache / "raw-gem.json", output / "raw.json")
    cleaned["evidence_source"] = "raw.json"
    with (output / "cleaned.json").open("x") as f:
        json.dump(cleaned, f, allow_nan=False, separators=(",", ":"))
    count = sum(len(p["position_log"]) for p in cleaned["players"])
    del cleaned
    gc.collect()
    with (output / "quality.json").open("x") as f:
        json.dump(quality, f, indent=2)
    validate_match(output / "cleaned.json")
    if before != {str(p): file_hash(p) for p in paths}:
        raise ValueError("Input/code drift")
    files = {p.name: file_hash(p) for p in output.iterdir() if p.is_file()}
    with (output / "manifest.json").open("x") as f:
        json.dump(
            {
                "schema_version": "clean-only-recovery/1",
                "match_id": mid,
                "preparation_id": f"clean-only-{mid}",
                "files": files,
                "config": config.model_dump(),
                "training_admission": False,
                "position_count": count,
                "validation": "clean_match + validate_match; no samples or workspace import",
            },
            f,
            indent=2,
        )
    print(
        json.dumps({"match_id": mid, "positions": count, "quarantined": quality["quarantined"]}),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--mid", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    run(**vars(p.parse_args()))
