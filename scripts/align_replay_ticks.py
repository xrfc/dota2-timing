"""Export separate omniscient and observer tick tables from immutable raw/cleaned data."""

import argparse
import gc
import inspect
import json
from collections import Counter, defaultdict
from pathlib import Path

from export_raw_replay_channels import positions, validate_identity
from gem.state.game_clock import GameClock

from dota_items.data.replay_semantics import make_clock
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.data.tick_alignment import align_player
from dota_items.storage import file_hash


def read(path):
    return parse_source_json(read_source_bytes(path, max_bytes=512 * 1024**2))


def run(root, mid, preparation, compat, output):
    if output.exists():
        raise ValueError("Output exists")
    plan = read(root / "plan.json")
    candidate = next(c for c in plan["candidates"] if c["match_id"] == mid)
    metadata_path = Path(candidate["metadata_path"])
    if file_hash(metadata_path) != candidate["metadata_sha256"]:
        raise ValueError("Metadata changed")
    pm = read(preparation / "manifest.json")
    if pm["match_id"] != mid:
        raise ValueError("Preparation identity mismatch")
    paths = [
        root / "plan.json",
        metadata_path,
        preparation / "manifest.json",
        compat / "manifest.json",
    ]
    for name in ["raw.json", "cleaned.json", "quality.json"]:
        path = preparation / name
        if file_hash(path) != pm["files"][name]:
            raise ValueError("Preparation hash mismatch")
        paths.append(path)
    for name, h in read(compat / "manifest.json")["patched"].items():
        path = compat / "gem" / name
        if file_hash(path) != h:
            raise ValueError("Compatibility mismatch")
        paths.append(path)
    if Path(inspect.getfile(GameClock)).resolve() != (compat / "gem/state/game_clock.py").resolve():
        raise ValueError("Wrong clock implementation")
    paths += [
        Path(__file__),
        Path("scripts/export_raw_replay_channels.py"),
        Path(inspect.getfile(align_player)),
        Path(inspect.getfile(make_clock)),
        Path("src/dota_items/data/source_io.py"),
    ]
    before = {str(p): file_hash(p) for p in paths}
    cleaned = read(preparation / "cleaned.json")
    accepted = {
        p["player_slot"]: {r["source_ref"] for r in p["position_log"]} for p in cleaned["players"]
    }
    del cleaned
    gc.collect()
    raw = read(preparation / "raw.json")
    validate_identity(raw, read(metadata_path))
    ps = defaultdict(list)
    for row in positions(raw):
        ps[row["player_id"]].append(row)
    states = defaultdict(list)
    for i, row in enumerate(raw["coach_state_snapshots"]):
        states[row["player_id"]].append(
            {
                k: row.get(k)
                for k in ("tick", "player_id", "entity_index", "entity_serial", "life_state")
            }
            | {"source_ref": f"coach_state_snapshots[{i}]"}
        )
    visible = defaultdict(list)
    for i, row in enumerate(raw["hero_visibility_events"]):
        visible[row["player_id"]].append({**row, "source_ref": f"hero_visibility_events[{i}]"})
    pauses = raw["game_clock"]["pauses"]
    duration = raw["duration"]
    del raw
    gc.collect()
    output.mkdir(parents=True)
    totals = Counter()
    flags = Counter()
    views = Counter()
    with (
        (output / "omniscient.jsonl").open("x") as omni,
        (output / "radiant.jsonl").open("x") as rad,
        (output / "dire.jsonl").open("x") as dire,
    ):
        handles = {"radiant": rad, "dire": dire}
        for pid in sorted(ps):
            slot = pid if pid < 5 else pid + 123
            for row, observers in align_player(
                ps[pid], states[pid], visible[pid], accepted[slot], pauses
            ):
                omni.write(json.dumps(row, allow_nan=False) + "\n")
                totals["omniscient"] += 1
                flags.update(row["quality_flags"])
                for view in observers:
                    # Keep pre/post records in omniscient evidence only.
                    if view["time"] is None or not 0 <= view["time"] <= duration:
                        continue
                    if view["visibility"] != "visible" and view["current_position"] is not None:
                        raise AssertionError("Hidden position leak")
                    handles[view["observer_team"]].write(json.dumps(view, allow_nan=False) + "\n")
                    totals[view["observer_team"]] += 1
                    views[
                        f"{view['observer_team']}:{view['visibility']}:"
                        f"{'known' if view['current_position'] is not None else 'withheld'}"
                    ] += 1
    if before != {str(p): file_hash(p) for p in paths}:
        raise ValueError("Inputs/code changed")
    with (output / "manifest.json").open("x") as f:
        json.dump(
            {
                "schema": "replay-tick-alignment/1",
                "match_id": mid,
                "inputs_and_code": before,
                "counts": dict(totals),
                "flags": dict(flags),
                "observer_counts": dict(views),
                "files": {p.name: file_hash(p) for p in output.glob("*.jsonl")},
                "training_admission": False,
                "limitations": [
                    "Native coordinates only; no interpolation.",
                    "Observer positions require retained refs and unique same-tick living state.",
                    "Repeated game seconds preserved; tick is the ordering key.",
                    "Hidden life state, true positions and omniscient quality flags excluded.",
                    "No complete map fog or player attention reconstruction.",
                ],
            },
            f,
            indent=2,
        )
    print(json.dumps({"match_id": mid, "counts": dict(totals), "flags": dict(flags)}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for n in ["root", "preparation", "compat", "output"]:
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--mid", type=int, required=True)
    run(**vars(p.parse_args()))
