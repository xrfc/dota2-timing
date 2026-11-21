"""Per-match tables for the death-risk model and the win-state model (track B, U160).

For every non-holdout match with parser-v3 state this writes
`<root>/<--table>/<match>.pkl` (local, untracked) with

* `risk`:   death_risk.samples for each position 1 hero (U132; --positions to change),
            with the version 2 features (own save means, own creep wave, own observer
            wards, missing initiators) and version 3 (could a missing enemy be here,
            trends over 5-15 seconds);
* `win`:    the public team state every 5 seconds (net worth, levels, towers, heroes
            alive) with the match result, for the win-state model that ranks deaths;
* `deaths`: every hero death (hero, team, second, position);
* `hits`:   for the same heroes as `risk`, every second they took damage, by source
            (enemy hero, illusion, tower, creep, neutral, other; death_risk.damage_taken),
            so that a fight-level alert measure can be computed without a rebuild;
* `contact`: for the same heroes, per living second: seen by the enemy team, nearest
            enemy hero his team could see, nearest real enemy hero (fight boundaries of
            the evaluation only, never features).

`--step` sets the sampling step (default 5; the 2026-11-18 trial compares 3, U174). The
trend features use lags in seconds, so rows at a given second are the same at any step.

The holdout matches (U133) are never read here.

The folder gets a `manifest.json` with the generation conditions (positions, parameters,
producer and knowledge file hashes; experiments.awareness.death_risk_tables). A folder
built under other conditions, or an old folder without a manifest (death-risk-v1 to v3),
is refused: a change needs a new `--table` name. A match file is reused only when its
conditions digest and source files match; nothing is overwritten.

    build_death_risk_table.py --root data/demos-2026-11 --table death-risk-v4 --workers 6
"""

import argparse
import gzip
import json
import pickle
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import detect_ganks
from detect_ganks import ZONES, match_inputs, source_key

from dota_items.contracts.death_risk import TABLE_SCHEMA
from dota_items.data.awareness_split import is_holdout
from dota_items.data.death_risk import (
    PARAMS,
    contact_track,
    damage_taken,
    death_times,
    samples,
    save_state,
    vitals_row,
)
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.gank_review import ward_spans
from dota_items.experiments.awareness.death_risk_tables import (
    describe_conditions,
    prepare_folder,
    reusable,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/dota_items"
PRODUCER_FILES = (
    Path(__file__).resolve(),
    Path(detect_ganks.__file__).resolve(),
    PACKAGE / "contracts/death_risk.py",
    PACKAGE / "data/death_risk.py",
    PACKAGE / "data/gank_depth.py",
    PACKAGE / "data/gank_review.py",
    PACKAGE / "data/gank_events.py",
    PACKAGE / "data/awareness_split.py",
)
SAVE_MEANS = ROOT / "knowledge/awareness/save-means-v2.json"
REGISTRY = ROOT / "knowledge/hero-capabilities/hero-registry.json"
KNOWLEDGE_FILES = (SAVE_MEANS, REGISTRY, ROOT / ZONES)


def move_speeds():
    """{hero: base move speed} from the hero registry (public game data)."""
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {h["npc_name"]: h["base_stats"]["movement_speed"] for h in registry["heroes"]}


def initiators():
    """Heroes with Valve's published "Initiator" role label (hero registry)."""
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {
        hero["npc_name"]
        for hero in registry["heroes"]
        if "Initiator" in (hero.get("published_role_labels") or ())
    }


WIN_STEP = 5


def read_vitals(path, means):
    """({hero: {t: vitals_row}}, {hero: {t: (saves owned, ready)}}) from parser-v3 state."""
    vitals, kit = {}, {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        stream.readline()  # header
        for line in stream:
            row = json.loads(line)
            for hero in row["heroes"]:
                vitals.setdefault(hero["hero"], {})[row["t"]] = vitals_row(hero)
                kit.setdefault(hero["hero"], {})[row["t"]] = save_state(hero, means)
    return vitals, kit


def net_worth(parsed):
    """{team: {t: summed net worth}} from the per-second economy logs."""
    totals = {2: {}, 3: {}}
    for player in parsed["players"]:
        team = 2 if player["player_slot"] < 128 else 3
        for entry in player.get("economy_log") or ():
            if entry.get("net_worth") is not None:
                totals[team][entry["time"]] = (
                    totals[team].get(entry["time"], 0) + entry["net_worth"]
                )
    return totals


def win_rows(match_id, tracks, vitals, worth, zones, fallen, last, radiant_win):
    rows = []
    for t in range(0, last + 1, WIN_STEP):
        if t not in worth[2] or t not in worth[3]:
            continue
        towers = standing_towers(zones, fallen, t)
        side = {
            2: {"levels": 0, "alive": 0, "towers": 0},
            3: {"levels": 0, "alive": 0, "towers": 0},
        }
        for hero, track in tracks.items():
            mine = vitals.get(hero, {}).get(t)
            side[track["team"]]["levels"] += mine[4] if mine and mine[4] else 0
            side[track["team"]]["alive"] += t in track["pos"]
        for tower in towers:
            if "tower" in tower["name"]:
                side[tower["team"]]["towers"] += 1
        rows.append(
            {
                "match_id": match_id,
                "t": t,
                "minute": t / 60,
                "net_worth_diff": worth[2][t] - worth[3][t],
                "net_worth_total": worth[2][t] + worth[3][t],
                "level_diff": side[2]["levels"] - side[3]["levels"],
                "alive_diff": side[2]["alive"] - side[3]["alive"],
                "tower_diff": side[2]["towers"] - side[3]["towers"],
                "radiant_win": int(radiant_win),
            }
        )
    return rows


def match_source_key(root, mid):
    """What one match file is built from: the cached inputs' key plus the meta file."""
    meta = root / "meta" / f"{mid}.json"
    return [*source_key(root, mid), [meta.name, meta.stat().st_size, meta.stat().st_mtime_ns]]


def build(job):
    root, folder, mid, positions, conditions_digest, params = job
    target = folder / f"{mid}.pkl"
    key = match_source_key(root, mid)
    if reusable(target, conditions_digest, key):
        return mid, "kept"
    meta = json.loads((root / "meta" / f"{mid}.json").read_text(encoding="utf-8"))
    if meta.get("radiant_win") is None:
        return mid, "no result"
    zones = json.loads(ZONES.read_text(encoding="utf-8"))
    m = match_inputs(root, mid, root / "gank-inputs-v2")
    tracks, combat = m["tracks"], m["combat"]
    means = json.loads(SAVE_MEANS.read_text(encoding="utf-8"))["means"]
    vitals, kit = read_vitals(root / "state-v3" / f"{mid}.jsonl.gz", means)
    with gzip.open(root / "parsed" / f"{mid}.normalized.json.gz", "rt", encoding="utf-8") as s:
        parsed = json.load(s)
    worth = net_worth(parsed)
    wards = ward_spans(parsed["context"]["channels"].get("wards") or ())
    starters = initiators()
    speeds = move_speeds()
    fallen = tower_deaths(combat)
    risk, hits, contact = [], [], []
    team = {name: track["team"] for name, track in tracks.items()}
    for hero, position in m["positions"].items():
        if position in positions:
            hits += [
                {"match_id": mid, "hero": hero, **row} for row in damage_taken(combat, hero, team)
            ]
            contact.append(
                {"match_id": mid, "hero": hero,
                 **contact_track(hero, tracks, m["seen"], params["start"], m["last"])}
            )  # fmt: skip
            context = {
                "kit": kit.get(hero, {}),
                "fronts": m["fronts"],
                "wards": [
                    w for w in wards
                    if w["type"] == "observer" and w["team"] == tracks[hero]["team"]
                ],
                "initiators": starters,
                "speeds": speeds,
            }  # fmt: skip
            rows = samples(
                mid, hero, tracks, vitals, m["seen"], combat, zones, fallen, m["last"],
                params=params, context=context,
            )  # fmt: skip
            risk += [{**row, "position": position, "team": tracks[hero]["team"]} for row in rows]
    deaths = [
        {"match_id": mid, "hero": hero, "team": track["team"], "t": t,
         "position": m["positions"].get(hero)}
        for hero, track in tracks.items()
        for t in death_times(combat, hero)
    ]  # fmt: skip
    value = {
        "schema": TABLE_SCHEMA,
        "match_id": mid,
        "conditions_digest": conditions_digest,
        "source_key": key,
        "params": params,
        "risk": risk,
        "win": win_rows(mid, tracks, vitals, worth, zones, fallen, m["last"], meta["radiant_win"]),
        "deaths": deaths,
        "hits": hits,
        "contact": contact,
    }
    temporary = target.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(target)
    return mid, f"risk {len(risk)} win {len(value['win'])}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--table", required=True, help="output folder name under --root")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--positions", type=int, nargs="+", default=[1])
    parser.add_argument("--step", type=int, default=PARAMS["step"], help="seconds per sample")
    args = parser.parse_args(argv)
    ids = sorted(
        int(p.name.split(".")[0])
        for p in (args.root / "state-v3").glob("*.jsonl.gz")
        if (args.root / "parsed" / f"{p.name.split('.')[0]}.normalized.json.gz").exists()
    )
    ids = [m for m in ids if not is_holdout(m)]  # U133
    if args.limit:
        ids = ids[: args.limit]
    params = {**PARAMS, "step": args.step}
    conditions = describe_conditions(
        args.positions, params, WIN_STEP, PRODUCER_FILES, KNOWLEDGE_FILES, ROOT
    )
    folder = args.root / args.table
    conditions_digest = prepare_folder(folder, conditions)
    positions = tuple(args.positions)
    jobs = [(args.root, folder, mid, positions, conditions_digest, params) for mid in ids]
    with ProcessPoolExecutor(args.workers) as pool:
        for number, (mid, note) in enumerate(pool.map(build, jobs), 1):
            if number % 50 == 0 or number == len(jobs):
                print(f"{mid} {note} [{number}/{len(jobs)}]", flush=True)


if __name__ == "__main__":
    main()
