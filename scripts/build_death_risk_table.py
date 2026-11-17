"""Per-match tables for the death-risk model and the win-state model (track B, U160).

For every non-holdout match with parser-v3 state this writes
`<root>/death-risk-v2/<match>.pkl` (local, untracked; v1 of 2026-11-17 is kept) with

* `risk`:   death_risk.samples for each position 1 hero (U132; --positions to change),
            with the version 2 features (own save means, own creep wave, own observer
            wards, missing initiators);
* `win`:    the public team state every 5 seconds (net worth, levels, towers, heroes
            alive) with the match result, for the win-state model that ranks deaths;
* `deaths`: every hero death (hero, team, second, position).

The holdout matches (U133) are never read here.

    build_death_risk_table.py --root data/demos-2026-11 --workers 6
"""

import argparse
import gzip
import json
import pickle
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from detect_ganks import ZONES, match_inputs

from dota_items.data.awareness_split import is_holdout
from dota_items.data.death_risk import PARAMS, death_times, samples, save_state, vitals_row
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.gank_review import ward_spans

SCHEMA = "death-risk-table/2"  # 2: version 2 features
FOLDER = "death-risk-v2"
ROOT = Path(__file__).resolve().parents[1]
SAVE_MEANS = ROOT / "knowledge/awareness/save-means-v2.json"
REGISTRY = ROOT / "knowledge/hero-capabilities/hero-registry.json"


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


def build(job):
    root, mid, positions = job
    target = root / FOLDER / f"{mid}.pkl"
    if target.exists():
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
    fallen = tower_deaths(combat)
    risk = []
    for hero, position in m["positions"].items():
        if position in positions:
            context = {
                "kit": kit.get(hero, {}),
                "fronts": m["fronts"],
                "wards": [
                    w for w in wards
                    if w["type"] == "observer" and w["team"] == tracks[hero]["team"]
                ],
                "initiators": starters,
            }  # fmt: skip
            rows = samples(
                mid, hero, tracks, vitals, m["seen"], combat, zones, fallen, m["last"],
                context=context,
            )  # fmt: skip
            risk += [{**row, "position": position, "team": tracks[hero]["team"]} for row in rows]
    deaths = [
        {"match_id": mid, "hero": hero, "team": track["team"], "t": t,
         "position": m["positions"].get(hero)}
        for hero, track in tracks.items()
        for t in death_times(combat, hero)
    ]  # fmt: skip
    value = {
        "schema": SCHEMA,
        "params": PARAMS,
        "risk": risk,
        "win": win_rows(mid, tracks, vitals, worth, zones, fallen, m["last"], meta["radiant_win"]),
        "deaths": deaths,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(target)
    return mid, f"risk {len(risk)} win {len(value['win'])}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--positions", type=int, nargs="+", default=[1])
    args = parser.parse_args(argv)
    ids = sorted(
        int(p.name.split(".")[0])
        for p in (args.root / "state-v3").glob("*.jsonl.gz")
        if (args.root / "parsed" / f"{p.name.split('.')[0]}.normalized.json.gz").exists()
    )
    ids = [m for m in ids if not is_holdout(m)]  # U133
    if args.limit:
        ids = ids[: args.limit]
    jobs = [(args.root, mid, tuple(args.positions)) for mid in ids]
    with ProcessPoolExecutor(args.workers) as pool:
        for number, (mid, note) in enumerate(pool.map(build, jobs), 1):
            if number % 50 == 0 or number == len(jobs):
                print(f"{mid} {note} [{number}/{len(jobs)}]", flush=True)


if __name__ == "__main__":
    main()
