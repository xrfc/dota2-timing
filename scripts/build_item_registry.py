"""Build knowledge/items/item-registry.json from the hash-checked downloaded sources (U14)."""

import argparse
import json
from pathlib import Path

from dota_items.data.item_registry import build_registry
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
SOURCES = "knowledge/items/sources"


def run(output, sources=SOURCES, repo=ROOT, overwrite=False):
    sources, output = repo / sources, repo / output
    manifest = parse_source_json(read_source_bytes(sources / "manifest.json"))
    for name, meta in manifest["files"].items():
        if file_hash(sources / name) != meta["sha256"]:
            raise ValueError(f"Source changed: {name}")
    registry = build_registry(
        parse_source_json(read_source_bytes(sources / "itemlist-schinese.json")),
        parse_source_json(read_source_bytes(sources / "dotaconstants-items.json")),
    )
    registry["sources"] = {
        "manifest_sha256": file_hash(sources / "manifest.json"),
        "fetched_at": manifest["fetched_at"],
    }
    if output.exists() and not overwrite:
        raise ValueError("Output exists (pass --overwrite only when regenerating from new sources)")
    output.write_text(json.dumps(registry, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    items = registry["items"]
    return {
        "items": len(items),
        "completed": sum(i["completed"] for i in items.values()),
        "with_zh_name": sum(bool(i["name_zh"]) for i in items.values()),
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", default="knowledge/items/item-registry.json")
    cli.add_argument("--overwrite", action="store_true")
    args = cli.parse_args()
    print(json.dumps(run(args.output, overwrite=args.overwrite)))
