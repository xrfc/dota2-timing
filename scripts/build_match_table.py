"""M1 match table commands.

``inventory`` counts coverage only. ``snapshot`` writes the frozen M1 tables to a
new directory; ``verify`` rebuilds them in memory and compares byte hashes.
None of these filter by outcome, train, or touch the network.
"""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from dota_items.data.match_table import (
    COLLAPSED_CARRY_LH_10,
    DEFAULT_ROOTS,
    LANE_MINUTE,
    POSITION_MIN_GAP,
    POSITION_MINUTE,
    PURCHASE_AVAILABILITY,
    assign_positions,
    availability,
    fully_parsed,
    inventory,
    load_match,
    match_files,
    player_rows,
    purchase_rows,
    time_split,
)
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ("scripts/build_match_table.py", "src/dota_items/data/match_table.py")
VALIDATION_FRACTION = 0.2


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run_inventory(output, roots=DEFAULT_ROOTS, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output exists")
    files = list(match_files([repo / r for r in roots]))
    result = inventory(load_match(path, manifest) for path, manifest in files)
    result["roots"] = list(roots)
    result["implementation"] = {name: file_hash(repo / name) for name in IMPLEMENTATION}
    output.mkdir(parents=True)
    write(output / "inventory.json", result)
    return {k: result[k] for k in ("matches", "unique_matches", "players", "distinct_heroes")}


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def csv_bytes(rows, columns):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row[c]) for c in columns])
    return buffer.getvalue().encode("utf-8")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def build_tables(roots=DEFAULT_ROOTS, repo=ROOT):
    """Return {output name: bytes} plus the input digest; deterministic for fixed inputs."""
    inputs, players, purchases, starts, excluded = [], [], [], {}, []
    for path, manifest in match_files([repo / r for r in roots]):
        match = load_match(path, manifest)
        inputs.append(f"{path.relative_to(repo)} {file_hash(path)}")
        if not fully_parsed(match):
            excluded.append(match["match_id"])
            continue
        starts[match["match_id"]] = match["start_time"]
        players.extend(player_rows(match))
        purchases.extend(purchase_rows(match))
    players = sorted(assign_positions(players), key=lambda r: (r["match_id"], r["player_slot"]))
    # Stable sort keeps each player's log order.
    purchases.sort(key=lambda r: (r["match_id"], r["player_slot"]))
    player_columns = list(players[0])
    purchase_columns = list(PURCHASE_AVAILABILITY)
    split = time_split(starts, VALIDATION_FRACTION)
    outputs = {
        "players.csv": csv_bytes(players, player_columns),
        "purchases.csv": csv_bytes(purchases, purchase_columns),
        "split.json": json_bytes(split),
    }
    digest = hashlib.sha256("\n".join(sorted(inputs)).encode()).hexdigest()
    summary = {
        "input_files": len(inputs),
        "input_digest_sha256": digest,
        "matches": len(starts),
        "excluded_unparsed_match_ids": sorted(excluded),
        "player_rows": len(players),
        "purchase_rows": len(purchases),
        "train_matches": len(split["train"]),
        "validation_matches": len(split["validation"]),
        "columns": {c: availability(c) for c in player_columns},
        "purchase_columns": PURCHASE_AVAILABILITY,
        "rules": {
            "lane_window_s": [0, LANE_MINUTE * 60],
            "position_minute": POSITION_MINUTE,
            "position_min_gap": POSITION_MIN_GAP,
            "collapsed_carry_lh_10_below": COLLAPSED_CARRY_LH_10,
            "decisions": ["U7", "U8"],
        },
    }
    return outputs, summary


def run_snapshot(output, roots=DEFAULT_ROOTS, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output exists")
    before = {name: file_hash(repo / name) for name in IMPLEMENTATION}
    outputs, summary = build_tables(roots, repo)
    if {name: file_hash(repo / name) for name in IMPLEMENTATION} != before:
        raise ValueError("Implementation changed during build")
    output.mkdir(parents=True)
    for name, data in outputs.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    manifest = {
        "schema": "m1-match-table/1",
        "roots": list(roots),
        **summary,
        "implementation": before,
        "outputs": {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
        "training_performed": False,
    }
    write(output / "manifest.json", manifest)
    return {k: summary[k] for k in ("matches", "player_rows", "purchase_rows")} | {
        "train": summary["train_matches"],
        "validation": summary["validation_matches"],
    }


def run_verify(snapshot, repo=ROOT):
    """Rebuild in memory; any input, implementation or output drift is a failure."""
    snapshot = Path(snapshot)
    manifest = parse_source_json(read_source_bytes(snapshot / "manifest.json"))
    problems = []
    current = {name: file_hash(repo / name) for name in IMPLEMENTATION}
    if current != manifest["implementation"]:
        problems.append("implementation_changed")
    for name, expected in manifest["outputs"].items():
        if file_hash(snapshot / name) != expected:
            problems.append(f"stored_output_changed:{name}")
    outputs, summary = build_tables(tuple(manifest["roots"]), repo)
    if summary["input_digest_sha256"] != manifest["input_digest_sha256"]:
        problems.append("inputs_changed")
    for name, data in outputs.items():
        if hashlib.sha256(data).hexdigest() != manifest["outputs"].get(name):
            problems.append(f"rebuild_differs:{name}")
    return {"snapshot": str(snapshot), "ok": not problems, "problems": problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "snapshot"):
        sub.add_parser(name).add_argument("--output", required=True)
    sub.add_parser("verify").add_argument("--snapshot", required=True)
    args = parser.parse_args()
    if args.command == "inventory":
        print(json.dumps(run_inventory(args.output)))
    elif args.command == "snapshot":
        print(json.dumps(run_snapshot(args.output)))
    else:
        result = run_verify(args.snapshot)
        print(json.dumps(result))
        if not result["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
