"""Project raw replay position/visibility channels without normalization or training."""

import argparse
import hashlib
import inspect
import json
import math
from pathlib import Path

from gem.catalog.heroes import hero_meta, hero_npc_name
from gem.state.game_clock import GameClock

from dota_items.data.replay_semantics import make_clock
from dota_items.data.source_io import parse_source_json, read_source_bytes


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    return parse_source_json(read_source_bytes(path, max_bytes=512 * 1024**2))


def hero_identity(player):
    reported = player["hero_id"]
    if type(reported) is int and reported > 0:
        return reported, {"method": "raw_hero_id", "reported_hero_id": reported}
    name = player.get("hero_name")
    if reported == 0 and isinstance(name, str):
        canonical = hero_npc_name(name.removeprefix("npc_dota_hero_"))
        resolved = hero_meta(canonical).get("id", 0) if canonical else 0
        if type(resolved) is int and resolved > 0:
            return resolved, {
                "method": "gem_catalog_alias",
                "reported_hero_id": reported,
                "source_name": name,
                "canonical_name": canonical,
            }
    raise ValueError("Unresolved hero identity")


def validate_identity(raw, metadata):
    if raw["match_id"] != metadata["match_id"]:
        raise ValueError("Match identity mismatch")
    players = raw["players"]
    ids = [p["player_id"] for p in players]
    if sorted(ids) != list(range(10)):
        raise ValueError("Expected ten unique player IDs")
    actual = {
        p["player_id"] if p["player_id"] < 5 else p["player_id"] + 123: hero_identity(p)[0]
        for p in players
    }
    expected = {p["player_slot"]: p["hero_id"] for p in metadata["players"]}
    if len(metadata["players"]) != 10 or actual != expected:
        raise ValueError("Hero identity mismatch")
    if not raw.get("hero_visibility_events"):
        raise ValueError("Missing visibility channel")


def positions(raw):
    clock = make_clock(raw)
    for pi, player in enumerate(raw["players"]):
        resolved_id, identity = hero_identity(player)
        previous = -1
        if not player["position_log"]:
            raise ValueError("Empty position channel")
        for ri, value in enumerate(player["position_log"]):
            tick, x, y = value
            if (
                type(tick) is not int
                or tick < previous
                or not all(type(v) in (int, float) and math.isfinite(v) for v in (x, y))
            ):
                raise ValueError("Invalid or unsorted position")
            previous = tick
            time = clock.game_seconds_at(tick)
            yield {
                "match_id": raw["match_id"],
                "player_id": player["player_id"],
                "player_slot": player["player_id"]
                if player["player_id"] < 5
                else player["player_id"] + 123,
                "hero_id": resolved_id,
                "hero_identity": identity,
                "source_tick": tick,
                "time": time,
                "x": x,
                "y": y,
                "time_scope": "unknown"
                if time is None
                else "pre_game"
                if time < 0
                else "post_duration"
                if time > raw["duration"]
                else "in_match",
                "source_ref": f"players[{pi}].position_log[{ri}]",
            }


def export(root, mid, output):
    if output.exists():
        raise ValueError("Output exists")
    inputs = {}

    def checked(path, expected=None):
        data = read_source_bytes(path, max_bytes=512 * 1024**2)
        digest = hashlib.sha256(data).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError("Input hash mismatch")
        inputs[str(path)] = digest
        return parse_source_json(data)

    plan = checked(root / "plan.json")
    selected = next(r for r in plan["candidates"] if r["match_id"] == mid)
    metadata = checked(Path(selected["metadata_path"]), selected["metadata_sha256"])
    receipt = checked(root / f"{mid}.receipt.json")
    archive = root / f"{mid}.dem.bz2"
    inputs[str(archive)] = sha(archive)
    if inputs[str(archive)] != receipt["archive_sha256"]:
        raise ValueError("Archive hash mismatch")
    cache = root / "workspaces" / str(mid) / "cache/matches" / receipt["archive_sha256"]
    manifest = checked(cache / "manifest.json")
    if manifest["source_sha256"] != receipt["archive_sha256"] or manifest["match_id"] != mid:
        raise ValueError("Cache identity mismatch")
    raw = checked(cache / "raw-gem.json", manifest["raw_json_sha256"])
    compat = checked(Path(plan["compat"]) / "manifest.json", plan["compat_manifest_sha256"])
    clock_path = Path(inspect.getfile(GameClock))
    if sha(clock_path) != compat["patched"]["state/game_clock.py"]:
        raise ValueError("Clock differs from frozen implementation")
    implementation = {
        str(p): sha(p)
        for p in [
            Path(__file__),
            clock_path,
            Path(inspect.getfile(make_clock)),
            Path(inspect.getfile(read_source_bytes)),
            Path(inspect.getfile(hero_meta)),
            Path(inspect.getfile(hero_meta)).parents[1] / "data/heroes.json",
        ]
    }
    validate_identity(raw, metadata)
    output.mkdir(parents=True, exist_ok=False)
    counts = {"positions": 0, "visibility": 0, "time_scope": {}}
    with (output / "positions.raw.jsonl").open("x") as stream:
        for row in positions(raw):
            row["raw_sha256"] = manifest["raw_json_sha256"]
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            counts["positions"] += 1
            scope = row["time_scope"]
            counts["time_scope"][scope] = counts["time_scope"].get(scope, 0) + 1
    clock = make_clock(raw)
    with (output / "visibility.raw.jsonl").open("x") as stream:
        for i, event in enumerate(raw["hero_visibility_events"]):
            if type(event.get("tick")) is not int or event.get("player_id") not in range(10):
                raise ValueError("Invalid visibility identity or tick")
            row = {
                "match_id": mid,
                "source_tick": event["tick"],
                "time": clock.game_seconds_at(event["tick"]),
                "payload": event,
                "source_ref": f"hero_visibility_events[{i}]",
                "raw_sha256": manifest["raw_json_sha256"],
            }
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            counts["visibility"] += 1
    for path, digest in {**inputs, **implementation}.items():
        if sha(Path(path)) != digest:
            raise ValueError("Inputs or implementation changed")
    result = {
        "schema": "raw-replay-channel-projection/2",
        "match_id": mid,
        "stage": "raw_not_cleaned_or_aligned",
        "counts": counts,
        "inputs": inputs,
        "implementation": implementation,
        "game_clock": raw["game_clock"],
        "duration": raw["duration"],
        "training_admission": False,
        "limitations": [
            "All ticks retained, including pauses and duplicate game seconds.",
            "No inferred visibility, interpolation or map transform.",
            "Source consistency is not independent gameplay verification.",
        ],
        "outputs": {p.name: sha(p) for p in output.glob("*.jsonl")},
    }
    with (output / "manifest.json").open("x") as stream:
        json.dump(result, stream, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--match-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    r = export(args.root.resolve(), args.match_id, args.output.resolve())
    print(json.dumps({"match_id": r["match_id"], "counts": r["counts"]}))
