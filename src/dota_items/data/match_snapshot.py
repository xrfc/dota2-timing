"""Read the frozen M1 match-table snapshot and write new JSON results.

Shared by the M2/M2b/U23 scripts, which previously loaded these functions from
scripts/train_item_timing.py via importlib. Behaviour is unchanged.
"""

import csv
import json

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash


def write_new_json(path, value):
    """Write JSON to a file that must not exist yet (no overwrite of old results)."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _value(text):
    if text == "":
        return None
    if text in ("true", "false"):
        return text == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return [{k: _value(v) for k, v in row.items()} for row in csv.DictReader(stream)]


def load_snapshot(snapshot):
    """Check manifest output hashes; return (manifest, players, purchases, split)."""
    manifest = parse_source_json(read_source_bytes(snapshot / "manifest.json"))
    for name, expected in manifest["outputs"].items():
        if file_hash(snapshot / name) != expected:
            raise ValueError(f"Snapshot file changed: {name}")
    players = read_csv(snapshot / "players.csv")
    purchases = [{**p, "item": str(p["item"])} for p in read_csv(snapshot / "purchases.csv")]
    split = parse_source_json(read_source_bytes(snapshot / "split.json"))
    return manifest, players, purchases, split
