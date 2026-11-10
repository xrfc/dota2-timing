"""B0: build the save-means list and find gank episodes in collected matches (U131).

    PYTHONPATH=src .venv/bin/python scripts/detect_ganks.py save-means
    PYTHONPATH=src .venv/bin/python scripts/detect_ganks.py run \
        --root data/demos-2026-11 --out reports/gank-episodes-2026-11-09

`save-means` writes knowledge/awareness/save-means-v1.json (refuses to overwrite).
`run` reads every match with both `state-v3/<id>.jsonl.gz` and
`parsed/<id>.normalized.json.gz`, writes `episodes.jsonl`, `summary.json` and
`sample.json` (20 ganks and 20 near misses for the user to check in replays). Read-only
on the data folder; the output folder must not exist yet.
"""

import argparse
import gzip
import json
import random
from pathlib import Path

from dota_items.data.gank_events import (
    PARAMS,
    build_save_means,
    detect_ganks,
    hero_tracks,
    infer_positions,
    summarize,
    visibility_table,
)
from dota_items.data.mechanics_api import Knowledge

SAVE_MEANS = Path("knowledge/awareness/save-means-v1.json")
SAMPLE_SEED = 20261109
KEEP = ("hero", "team", "player_id", "life_state", "pos")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def save_means(args):
    if SAVE_MEANS.exists():
        raise SystemExit(f"{SAVE_MEANS} exists; make a new version instead of overwriting")
    SAVE_MEANS.parent.mkdir(parents=True, exist_ok=True)
    value = build_save_means(Knowledge())
    write_json(SAVE_MEANS, value)
    print(f"{len(value['means'])} save means -> {SAVE_MEANS}")


def load_rows(path):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        stream.readline()  # header
        for line in stream:
            row = json.loads(line)
            rows.append(
                {"t": row["t"], "heroes": [{k: h.get(k) for k in KEEP} for h in row["heroes"]]}
            )
    return rows


def last_hits_at(parsed, tracks, second=900):
    by_player = {tr["player_id"]: hero for hero, tr in tracks.items()}
    result = {}
    for p in parsed["players"]:
        pid = p["player_slot"] if p["player_slot"] < 128 else p["player_slot"] - 128 + 5
        before = [e["last_hits"] for e in p.get("economy_log") or [] if e["time"] <= second]
        if pid in by_player and before:
            result[by_player[pid]] = before[-1]
    return result


def match_episodes(root, mid, means):
    rows = load_rows(root / "state-v3" / f"{mid}.jsonl.gz")
    with gzip.open(root / "parsed" / f"{mid}.normalized.json.gz", "rt", encoding="utf-8") as stream:
        parsed = json.load(stream)
    channels = parsed["context"]["channels"]
    tracks = hero_tracks(rows)
    seen = visibility_table(channels["hero_visibility_events"], rows[-1]["t"])
    positions = infer_positions(tracks, last_hits_at(parsed, tracks))
    episodes = detect_ganks(mid, tracks, channels["combat_log"], seen, positions, means)
    return episodes, positions


def run(args):
    means = json.loads(SAVE_MEANS.read_text(encoding="utf-8"))["means"]
    root = args.root
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    ids = sorted(
        int(p.name.split(".")[0])
        for p in (root / "state-v3").glob("*.jsonl.gz")
        if (root / "parsed" / f"{p.name.split('.')[0]}.normalized.json.gz").exists()
    )
    if args.limit:
        ids = ids[: args.limit]
    episodes, unknown_positions = [], 0
    with (out / "episodes.jsonl").open("w", encoding="utf-8") as stream:
        for count, mid in enumerate(ids, 1):
            found, positions = match_episodes(root, mid, means)
            wanted = 2 * len(PARAMS["positions"])
            unknown_positions += sum(p in PARAMS["positions"] for p in positions.values()) < wanted
            for e in found:
                stream.write(json.dumps(e, ensure_ascii=False) + "\n")
            episodes += found
            print(
                f"{mid} episodes {len(found)} ganks {sum(e['is_gank'] for e in found)} "
                f"[{count}/{len(ids)}]",
                flush=True,
            )
    summary = {
        **summarize(episodes, len(ids)),
        "matches_missing_an_evaluated_position": unknown_positions,
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in PARAMS.items()},
        "save_means": str(SAVE_MEANS),
    }
    write_json(out / "summary.json", summary)
    rng = random.Random(SAMPLE_SEED)
    ganks = [e for e in episodes if e["is_gank"]]
    near = [
        e for e in episodes if not e["is_gank"] and sum(not v for v in e["flags"].values()) == 1
    ]
    write_json(
        out / "sample.json",
        {
            "seed": SAMPLE_SEED,
            "ganks": rng.sample(ganks, min(20, len(ganks))),
            "near_misses": rng.sample(near, min(20, len(near))),
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("save-means")
    r = sub.add_parser("run")
    r.add_argument("--root", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    save_means(args) if args.command == "save-means" else run(args)


if __name__ == "__main__":
    main()
