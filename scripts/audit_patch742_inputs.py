"""Audit time coverage in one local, non-holdout OpenDota patch-61 replay.

Read the collector's meta, parsed, state-v3 and extras-v1 files. Emit aggregate
compatibility diagnostics to stdout. Missing in-game seconds or unavailable
channels exit 1. Unreadable inputs and identity or schema mismatches exit 2.
"""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from dota_items.contracts.replay_context import CONTEXT_SCHEMA
from dota_items.data.awareness_split import is_holdout
from dota_items.sources.gem_capture_extras import CAPTURE_VERSION as EXTRAS_SCHEMA
from dota_items.sources.gem_capture_v3 import CAPTURE_VERSION as STATE_SCHEMA
from dota_items.sources.gem_replay import ADAPTER_VERSION
from dota_items.storage import read_json

CHANNELS = ("combat_log", "hero_visibility_events", "wards")


def object_row(value, description):
    if not isinstance(value, dict):
        raise ValueError(f"{description}: expected a JSON object")
    return value


def capture_rows(path, mid, schema):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        header = object_row(json.loads(stream.readline()), f"{path.name} header")
        if header.get("schema") != schema or header.get("match_id") != mid:
            raise ValueError(f"{path.name}: expected match {mid} and schema {schema}")
        previous = None
        count = 0
        for line in stream:
            row = object_row(json.loads(line), path.name)
            second = row.get("t")
            if type(second) is not int or (previous is not None and second <= previous):
                raise ValueError(f"{path.name}: invalid, duplicate or out-of-order capture second")
            previous = second
            count += 1
            yield row
        if type(header.get("seconds")) is not int or count != header["seconds"]:
            raise ValueError(f"{path.name}: capture row count differs from header")


def time_summary(seconds, duration):
    observed = sum(0 <= t <= duration for t in seconds)
    return {
        "rows": len(seconds),
        "first_second": min(seconds, default=None),
        "last_second": max(seconds, default=None),
        "pregame_seconds": sum(t < 0 for t in seconds),
        "in_game_seconds": observed,
        "missing_in_game_seconds": duration + 1 - observed,
        "postgame_seconds": sum(t > duration for t in seconds),
    }


def state_coverage(rows, duration):
    seconds = set()
    coverage = Counter()
    for row in rows:
        t = row["t"]
        seconds.add(t)
        if 0 <= t <= duration:
            heroes = row.get("heroes")
            world = row.get("world")
            fronts = world.get("lane_fronts") if isinstance(world, dict) else None
            coverage["heroes_recorded"] += isinstance(heroes, list)
            coverage["heroes_nonempty"] += isinstance(heroes, list) and bool(heroes)
            coverage["fronts_recorded"] += isinstance(fronts, dict)
            coverage["fronts_nonempty"] += isinstance(fronts, dict) and any(
                isinstance(value, dict) and value.get("front") and value.get("count")
                for value in fronts.values()
            )
    return seconds, {
        key: coverage[key]
        for key in ("heroes_recorded", "heroes_nonempty", "fronts_recorded", "fronts_nonempty")
    }


def extras_coverage(rows, duration):
    seconds = set()
    coverage = Counter()
    for row in rows:
        t = row["t"]
        seconds.add(t)
        if 0 <= t <= duration:
            for key in ("creeps", "watchers"):
                units = row.get(key)
                coverage[f"{key}_recorded"] += isinstance(units, list)
                coverage[f"{key}_nonempty"] += isinstance(units, list) and bool(units)
    return seconds, {
        key: coverage[key]
        for key in ("creeps_recorded", "creeps_nonempty", "watchers_recorded", "watchers_nonempty")
    }


def audit(root, mid):
    if mid <= 0 or is_holdout(mid):
        raise ValueError("expected a positive non-holdout match ID")
    meta = object_row(read_json(root / "meta" / f"{mid}.json"), "match metadata")
    if meta.get("match_id") != mid or meta.get("patch") != 61:
        raise ValueError(f"{mid}: expected OpenDota metadata for this match and patch 61 (7.42)")
    with gzip.open(root / "parsed" / f"{mid}.normalized.json.gz", "rt", encoding="utf-8") as f:
        parsed = object_row(json.load(f), "normalized replay")
    if parsed.get("match_id") != mid or parsed.get("schema_version") != ADAPTER_VERSION:
        raise ValueError(f"{mid}: unexpected normalized replay identity or schema")
    if parsed.get("patch") not in (None, 61):
        raise ValueError(f"{mid}: normalized patch conflicts with metadata")
    duration = parsed.get("duration")
    if type(duration) is not int or duration <= 0:
        raise ValueError(f"{mid}: positive normalized duration required")
    context = object_row(parsed.get("context"), "replay context")
    if context.get("schema_version") != CONTEXT_SCHEMA or not isinstance(
        context.get("channels"), dict
    ):
        raise ValueError(f"{mid}: unexpected replay context format")
    channel_counts = {}
    for name in CHANNELS:
        events = context["channels"].get(name)
        if events is not None and not isinstance(events, list):
            raise ValueError(f"{mid}: invalid normalized channel {name}")
        channel_counts[name] = len(events) if events is not None else None

    state_t, state = state_coverage(
        capture_rows(root / "state-v3" / f"{mid}.jsonl.gz", mid, STATE_SCHEMA), duration
    )
    extras_t, extras = extras_coverage(
        capture_rows(root / "extras-v1" / f"{mid}.jsonl.gz", mid, EXTRAS_SCHEMA), duration
    )
    shared = {t for t in state_t & extras_t if 0 <= t <= duration}
    complete = (
        len(shared) == duration + 1
        and all(
            count == duration + 1
            for name, count in (state | extras).items()
            if name.endswith("_recorded")
        )
        and all(count is not None for count in channel_counts.values())
    )
    return {
        "schema": "patch742-input-coverage/1",
        "match_id": mid,
        "opendota_patch": 61,
        "normalized_duration": duration,
        "complete_input_coverage": complete,
        "normalized_channel_rows": channel_counts,
        "state_v3": time_summary(state_t, duration) | {"in_game_fields": state},
        "extras_v1": time_summary(extras_t, duration) | {"in_game_fields": extras},
        "shared_in_game_seconds": len(shared),
        "state_only_in_game_seconds": sum(0 <= t <= duration for t in state_t - extras_t),
        "extras_only_in_game_seconds": sum(0 <= t <= duration for t in extras_t - state_t),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--match", type=int, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.root, args.match)
    except (OSError, ValueError, EOFError) as exc:
        parser.exit(2, f"Input audit failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["complete_input_coverage"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
