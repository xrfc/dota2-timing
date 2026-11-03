"""Read the frozen M1 match-table snapshot and write new JSON results.

Shared by the M2/M2b/U23 scripts, which previously loaded these functions from
scripts/train_item_timing.py via importlib. Behaviour is unchanged.
"""

import csv
import json

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

MANIFEST_SCHEMA = "m1-match-table/1"
SPLIT_SCHEMA = "m1-time-split/1"
REQUIRED_OUTPUTS = {"players.csv", "purchases.csv", "split.json"}


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


def check_snapshot_contract(manifest, players, purchases, split):
    """Reject tables a correct hash cannot vouch for: wrong schema or unsafe split."""
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"Unsupported snapshot schema: {manifest.get('schema')}")
    if split.get("schema") != SPLIT_SCHEMA:
        raise ValueError(f"Unsupported split schema: {split.get('schema')}")
    train, validation = split["train"], split["validation"]
    if not train or not validation:
        raise ValueError("Snapshot split needs train and validation matches")
    if len(set(train)) != len(train) or len(set(validation)) != len(validation):
        raise ValueError("Snapshot split repeats a match")
    if set(train) & set(validation):
        raise ValueError("Snapshot split shares matches between train and validation")
    assigned = set(train) | set(validation)
    if {row["match_id"] for row in players} != assigned:
        raise ValueError("Snapshot players do not match the split")
    if not {row["match_id"] for row in purchases} <= assigned:
        raise ValueError("Snapshot purchases include matches outside the split")


def load_snapshot(snapshot):
    """Check hashes and the contract; return (manifest, players, purchases, split)."""
    manifest = parse_source_json(read_source_bytes(snapshot / "manifest.json"))
    missing = sorted(REQUIRED_OUTPUTS - set(manifest["outputs"]))
    if missing:
        raise ValueError(f"Snapshot manifest does not cover: {missing}")
    for name, expected in manifest["outputs"].items():
        if file_hash(snapshot / name) != expected:
            raise ValueError(f"Snapshot file changed: {name}")
    players = read_csv(snapshot / "players.csv")
    purchases = [{**p, "item": str(p["item"])} for p in read_csv(snapshot / "purchases.csv")]
    split = parse_source_json(read_source_bytes(snapshot / "split.json"))
    check_snapshot_contract(manifest, players, purchases, split)
    return manifest, players, purchases, split
