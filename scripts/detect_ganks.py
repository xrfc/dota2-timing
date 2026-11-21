"""B0: build the save-means list and find gank episodes in collected matches (U131).

    PYTHONPATH=src .venv/bin/python scripts/detect_ganks.py save-means
    PYTHONPATH=src .venv/bin/python scripts/detect_ganks.py run \
        --root data/demos-2026-11 --out reports/gank-episodes-2026-11-09

`save-means` writes knowledge/awareness/save-means-v1.json (refuses to overwrite).
`run` reads every match with both `state-v3/<id>.jsonl.gz` and
`parsed/<id>.normalized.json.gz` **except the track B holdout (U133)**, writes
`episodes.jsonl`, `summary.json` and `sample.json`: three strata of 20 for the user's
review (U134): deaths, escapes by a save, and episodes one condition short. Read-only on
the data folder except for its cache (below); the output folder must not exist yet.
`--sample-from FOLDER` keeps the
episodes of an earlier sample (matched by match, victim and start) instead of drawing a
new one, so judgments already made stay attached.

Reading a match takes seconds, the rules take milliseconds, so what the rules need from
each match (hero tracks, visibility, positions, lane fronts, the hero-related combat log)
is kept in `<root>/gank-inputs-v2/<id>.pkl` and reused while the two source files are
unchanged. `--no-cache` reads the sources again. The cache is a local convenience, not an
artifact: delete the folder at any time.

Since U136-U138 every episode also carries the depth signals (data.gank_depth) and the
attackers who came under Smoke of Deceit; ganks that start on a high ground or where the
victim overextended, or that are laning-phase fights with nobody from another lane, get
their own label and no longer count as ganks (U137, U138, U140).
"""

import argparse
import gzip
import json
import pickle
import random
from pathlib import Path

from dota_items.data.awareness_split import describe as holdout_rule
from dota_items.data.awareness_split import is_holdout
from dota_items.data.gank_depth import PARAMS as DEPTH_PARAMS
from dota_items.data.gank_depth import annotate
from dota_items.data.gank_events import (
    PARAMS,
    build_save_means,
    detect_ganks,
    hero_tracks,
    infer_positions,
    summarize,
    visibility_table,
)
from dota_items.data.gank_review import SMOKE_MODIFIER, smoke_intervals
from dota_items.data.mechanics_api import Knowledge

SAVE_MEANS = Path("knowledge/awareness/save-means-v2.json")
ZONES = Path("knowledge/awareness/map-zones-v1.json")
GANK_LABELS = ("death", "save_escape")
SAMPLE_SEED = 20261109
CACHE_SCHEMA = "gank-inputs/2"
# The payload fields data.gank_events, data.gank_depth and smoke_intervals read.
COMBAT_FIELDS = (
    "log_type",
    "attacker_name",
    "target_name",
    "inflictor_name",
    "attacker_is_hero",
    "attacker_is_illusion",
    "target_is_illusion",
    "value",
    "tick",
)
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
    """Hero rows per second; each row also keeps that second's lane fronts."""
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        stream.readline()  # header
        for line in stream:
            row = json.loads(line)
            rows.append(
                {
                    "t": row["t"],
                    "heroes": [{k: h.get(k) for k in KEEP} for h in row["heroes"]],
                    "fronts": (row.get("world") or {}).get("lane_fronts"),
                }
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


def source_key(root, mid):
    """What a cached match was read from: name, size and modification time of both files."""
    files = (
        root / "state-v3" / f"{mid}.jsonl.gz",
        root / "parsed" / f"{mid}.normalized.json.gz",
    )
    return [CACHE_SCHEMA, *([f.name, f.stat().st_size, f.stat().st_mtime_ns] for f in files)]


def slim_combat(combat, heroes):
    """The combat-log entries and fields the rules read: hero damage, deaths, casts, smoke."""
    kept = []
    for entry in combat:
        p = entry["payload"]
        kind = p.get("log_type")
        if kind == "DAMAGE":
            keep = p.get("attacker_name") in heroes or p.get("target_name") in heroes
        elif kind in ("MODIFIER_ADD", "MODIFIER_REMOVE"):
            keep = p.get("inflictor_name") == SMOKE_MODIFIER
        else:
            keep = kind in ("DEATH", "ABILITY", "ITEM")
        if keep:
            kept.append(
                {"time": entry["time"], "payload": {k: p[k] for k in COMBAT_FIELDS if k in p}}
            )
    return kept


def read_match(root, mid):
    """Everything the rules need from one match, parsed from the two source files."""
    rows = load_rows(root / "state-v3" / f"{mid}.jsonl.gz")
    with gzip.open(root / "parsed" / f"{mid}.normalized.json.gz", "rt", encoding="utf-8") as stream:
        parsed = json.load(stream)
    channels = parsed["context"]["channels"]
    tracks = hero_tracks(rows)
    return {
        "key": source_key(root, mid),
        "tracks": tracks,
        "seen": visibility_table(channels["hero_visibility_events"], rows[-1]["t"]),
        "positions": infer_positions(tracks, last_hits_at(parsed, tracks)),
        "combat": slim_combat(channels["combat_log"], tracks),
        "fronts": {row["t"]: row["fronts"] for row in rows},
        "last": rows[-1]["t"],
    }


def match_inputs(root, mid, cache):
    """read_match, kept in `cache`/<id>.pkl so a rule change does not re-read the match.

    The cache holds only this script's own output and is rebuilt when either source file
    changes. It lives under the untracked data folder and is never an artifact.
    """
    if cache is None:
        return read_match(root, mid)
    path = cache / f"{mid}.pkl"
    if path.exists():
        with path.open("rb") as stream:
            value = pickle.load(stream)  # written by this script, local only
        if value["key"] == source_key(root, mid):
            return value
    value = read_match(root, mid)
    cache.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)
    return value


def match_episodes(root, mid, means, zones, cache=None):
    m = match_inputs(root, mid, cache)
    tracks, combat, seen, positions = m["tracks"], m["combat"], m["seen"], m["positions"]
    episodes = detect_ganks(mid, tracks, combat, seen, positions, means)
    smoke = smoke_intervals(combat, m["last"])
    annotate(episodes, tracks, combat, m["fronts"], zones, smoke, seen)
    return episodes, positions


def run(args):
    means = json.loads(SAVE_MEANS.read_text(encoding="utf-8"))["means"]
    zones = json.loads(ZONES.read_text(encoding="utf-8"))
    root = args.root
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    available = sorted(
        int(p.name.split(".")[0])
        for p in (root / "state-v3").glob("*.jsonl.gz")
        if (root / "parsed" / f"{p.name.split('.')[0]}.normalized.json.gz").exists()
    )
    ids = [m for m in available if not is_holdout(m)]  # U133: never read the holdout here
    if args.limit:
        ids = ids[: args.limit]
    cache = None if args.no_cache else root / "gank-inputs-v2"
    episodes, unknown_positions = [], 0
    with (out / "episodes.jsonl").open("w", encoding="utf-8") as stream:
        for count, mid in enumerate(ids, 1):
            found, positions = match_episodes(root, mid, means, zones, cache)
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
        # Episodes are found with both teams' positions and the full combat log, and the
        # laning lanes use the whole first ten minutes: labels and review only (U55).
        "use": "label_and_review_only",
        "omniscient": True,
        "not_model_input": "contains information the evaluated player could not see",
        **summarize(episodes, len(ids)),
        "matches_missing_an_evaluated_position": unknown_positions,
        "holdout": {**holdout_rule(), "skipped_matches": len(available) - len(ids)},
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in PARAMS.items()},
        "save_means": str(SAVE_MEANS),
        "zones": str(ZONES),
        "depth_params": DEPTH_PARAMS,
        "by_final_label": {
            label: sum(e["label"] == label for e in episodes)
            for label in (*GANK_LABELS, *NOT_GANK_LABELS)
        },
        "overextended_by_rule_label": {
            label: sum(e["label"] == "overextended" and e["rule_label"] == label for e in episodes)
            for label in GANK_LABELS
        },
        "ganks_with_smoked_attacker": {
            label: sum(e["label"] == label and bool(e["smoked_attackers"]) for e in episodes)
            for label in GANK_LABELS
        },
    }
    write_json(out / "summary.json", summary)
    if args.sample_from:
        earlier = json.loads((args.sample_from / "sample.json").read_text(encoding="utf-8"))
        by_key = {(e["match_id"], e["victim"], e["t0"]): e for e in episodes}
        kept = {
            k: [by_key[(e["match_id"], e["victim"], e["t0"])] for e in earlier[k]]
            for k in ("death", "save_escape", "near_miss")
        }
        write_json(
            out / "sample.json",
            {
                "seed": earlier["seed"],
                "decision": "U134; same episodes as " + str(args.sample_from),
                "strata_are": "the four-condition labels of the earlier round (rule_label)",
                "population": earlier["population"],
                **kept,
            },
        )
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return
    rng = random.Random(SAMPLE_SEED)
    strata = {
        "death": [e for e in episodes if e["label"] == "death"],
        "save_escape": [e for e in episodes if e["label"] == "save_escape"],
        "near_miss": [
            e for e in episodes if not e["is_gank"] and sum(not v for v in e["flags"].values()) == 1
        ],
    }
    write_json(
        out / "sample.json",
        {
            "seed": SAMPLE_SEED,
            "decision": "U134",
            "population": {k: len(v) for k, v in strata.items()},
            **{k: rng.sample(v, min(20, len(v))) for k, v in strata.items()},
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))


NOT_GANK_LABELS = ("overextended", "laning", "after_fight", "teamfight", "high_ground")


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
    r.add_argument("--sample-from", type=Path, default=None)
    r.add_argument("--no-cache", action="store_true", help="read the source files again")
    args = parser.parse_args()
    save_means(args) if args.command == "save-means" else run(args)


if __name__ == "__main__":
    main()
