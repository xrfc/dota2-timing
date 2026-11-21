"""Build a 7.41f lane or jungle decision review from existing non-holdout replay data.

PYTHONPATH=src .venv/bin/python scripts/lane_decision_review.py --matches 9080976703 \
    --out reports/lane-decisions
Serve the output directory on localhost with python -m http.server --bind 127.0.0.1.
"""

import argparse
import base64
import gzip
import json
import shutil
import tempfile
from functools import lru_cache
from math import dist
from pathlib import Path

from detect_ganks import match_inputs
from gank_review import MAP, names

from dota_items.data.awareness_split import is_holdout
from dota_items.data.catch_threat import catch_comparison
from dota_items.data.death_risk import death_times
from dota_items.data.farm_value import farm_comparison
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.gank_review import ward_spans
from dota_items.data.lane_decisions import (
    farm_seconds,
    jungle_seconds,
    make_cases,
    make_jungle_cases,
    route_from_lane,
    wave_opportunities,
)
from dota_items.data.support_arrival import (
    observed_approach,
    support_comparison,
    support_followup,
    walk_hit_window,
)
from dota_items.data.vision_sim import (
    RANGE,
    Terrain,
    extra_sources,
    is_day,
    read_creep_samples,
    sees,
    team_sources,
)
from dota_items.storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name("lane_decision_assets")


# Fixed grid in replay coordinates. Each bit describes the centre of a 128-unit cell.
ORIGIN = 5920
STEP = 128
WIDTH = 163


@lru_cache(maxsize=1)
def terrain_map():
    folder = ROOT / "data/map-reference-2026-10-26-v1/coordinates/data"
    trees = read_json(folder / "mapdata.json")["data"]["ent_dota_tree"]
    return Terrain(
        read_json(folder / "elevationdata.json")["data"], [(t["x"], t["y"]) for t in trees]
    )


@lru_cache(maxsize=4096)
def source_cells(kind, pos, day):
    reach = RANGE[kind][0 if day else 1]
    terrain = terrain_map()

    def indices(v):
        return range(
            max(0, (v - reach - ORIGIN) // STEP), min(WIDTH, (v + reach - ORIGIN) // STEP + 1)
        )

    cells = []
    for y in indices(int(pos[1])):
        for x in indices(int(pos[0])):
            target = (ORIGIN + (x + 0.5) * STEP, ORIGIN + (y + 0.5) * STEP)
            if sees(pos, target, kind, 0 if day else 300, terrain, "sight"):
                cells.append(y * WIDTH + x)
    return cells


def vision_grid(sources, second):
    bits = bytearray((WIDTH * WIDTH + 7) // 8)
    for kind, pos in sources:
        for cell in source_cells(kind, tuple(pos), is_day(second)):
            bits[cell // 8] |= 1 << (cell % 8)
    return {"origin": ORIGIN, "step": STEP, "width": WIDTH, "bits": base64.b64encode(bits).decode()}


def hero_hits_by_second(match):
    tracks = match["tracks"]
    hits = {}
    for event in match["combat"]:
        p = event["payload"]
        target, attacker = p.get("target_name"), p.get("attacker_name")
        if (
            p.get("log_type") == "DAMAGE"
            and (p.get("value") or 0) > 0
            and not p.get("target_is_illusion")
            and not p.get("attacker_is_illusion")
            and target in tracks
            and attacker in tracks
            and tracks[target]["team"] != tracks[attacker]["team"]
        ):
            hits.setdefault(event["time"], set()).add(target)
    return hits


def support_opportunity(tracks, hits, hero, t):
    own = tracks[hero]
    recent = {
        target: sec
        for sec in range(t - 7, t + 1)
        for target in hits.get(sec, ())
        if target != hero and tracks[target]["team"] == own["team"] and t in tracks[target]["pos"]
    }
    if not recent:
        return None
    distance, ally = min((dist(own["pos"][t], tracks[h]["pos"][t]), h) for h in recent)
    return {"hero": ally, "seconds_ago": t - recent[ally], "distance": round(distance)}


def build_match(root, mid, means, mode="lane", *, wave_coverage=None):
    if is_holdout(mid):
        raise ValueError(f"{mid} is reserved for holdout evaluation")
    meta = read_json(root / "meta" / f"{mid}.json")
    if meta.get("match_id") != mid or meta.get("patch") != 60:
        raise ValueError(f"{mid}: expected the patch-60 cohort used for the 7.41f analysis")
    match = match_inputs(root, mid, root / "gank-inputs-v2")
    damage = hero_hits_by_second(match)
    heroes = sorted(h for h, pos in match["positions"].items() if pos == 1)
    visibility = {key: sorted(times) for key, times in match["seen"].items()}
    with gzip.open(root / "parsed" / f"{mid}.normalized.json.gz", "rt") as stream:
        parsed = json.load(stream)
        if parsed.get("match_id") != mid:
            raise ValueError(f"{mid}: unexpected match in normalized replay")
        duration = parsed.get("duration")
        if type(duration) is not int or duration < 0:
            raise ValueError(f"{mid}: missing or invalid normalized match duration")
        last_state_second = match["last"]
        match["last"] = min(duration, last_state_second)
        channels = parsed["context"]["channels"]
        del parsed
        events = channels["combat_log"]
        match["wards"] = ward_spans(channels["wards"])
        del channels
    lane_hits = {h: farm_seconds(events, h, match["tracks"][h]["team"]) for h in heroes}
    jungle_hits = {h: jungle_seconds(events, h) for h in heroes}
    hits = jungle_hits if mode == "jungle" else lane_hits
    del events
    extras = {}
    path = root / "extras-v1" / f"{mid}.jsonl.gz"
    if path.exists():
        extras = {row["t"]: row for row in read_creep_samples(path, mid, "gem-extras-capture/1")}
    opportunities = {}
    if mode == "wave":

        def can_see(origin, target, sec):
            return sees(origin, target, "hero", sec, terrain_map(), "sight")

        by_hero = {}
        for h in heroes:
            by_hero[h] = {}
            opportunities[h] = wave_opportunities(
                match, h, lane_hits[h], extras, can_see, coverage=by_hero[h]
            )
        if wave_coverage is not None:
            wave_coverage.update(extras_file_present=path.is_file(), heroes=by_hero)
    inventories = {}
    summons = {}
    match["dead_at"] = {}
    states = {h: {} for h in heroes}
    wanted = {h: set(times) for h, times in hits.items()}
    if mode == "wave":
        wanted = opportunities
    with gzip.open(root / "state-v3" / f"{mid}.jsonl.gz", "rt") as stream:
        header = json.loads(next(stream))
        if header.get("match_id") != mid or header.get("schema") != "gem-state-capture/3":
            raise ValueError(f"{mid}: unexpected state header")
        for row in map(json.loads, stream):
            summons[row["t"]] = row["world"].get("summons") or ()
            for state in row["heroes"]:
                h = state["hero"]
                if state.get("life_state") in (1, 2):
                    match["dead_at"].setdefault(row["t"], set()).add(h)
                if state.get("items") is not None:
                    inventories[h, row["t"]] = {
                        slot: item["name"]
                        for slot, item in state["items"].items()
                        if int(slot) in (*range(9), 15, 16) and item.get("name")
                    }
                if h in wanted and row["t"] in wanted[h]:
                    states[h][row["t"]] = state
    zones = read_json(ROOT / "knowledge/awareness/map-zones-v1.json")
    mobility = read_json(ROOT / "knowledge/awareness/hero-mobility-v1.json")
    display_names = names()
    deaths = tower_deaths(match["combat"])
    for h in heroes:
        team = match["tracks"][h]["team"]
        inputs = (
            match,
            mid,
            h,
            hits[h],
            visibility,
            states[h],
            means,
            death_times(match["combat"], h),
        )
        cases = (
            make_jungle_cases(*inputs, zones["camps"])
            if mode == "jungle"
            else make_cases(*inputs, opportunities=opportunities.get(h))
        )
        for evidence, action, outcome in cases:
            outcome.update(match_duration=duration, last_state_second=last_state_second)
            if mode == "jungle":
                evidence["route_from_lane"] = route_from_lane(
                    match["tracks"][h]["pos"], lane_hits[h], evidence["t"], zones["camps"]
                )
            t = evidence["t"]
            signal = support_opportunity(match["tracks"], damage, h, t)
            evidence["support_opportunity"] = signal
            if signal:
                ally = signal["hero"]
                buildings = standing_towers(zones, deaths, t)
                evidence["arrival"] = support_comparison(
                    states[h][t], match["tracks"][ally]["pos"][t], buildings, mobility
                )
                outcome["support_followup"] = support_followup(damage, ally, t, match["last"])
                outcome["walk_hit_window"] = walk_hit_window(
                    evidence["arrival"]["routes"].get("walk", {}), outcome["support_followup"]
                )
                outcome["observed_approach"] = observed_approach(
                    match["tracks"][h]["pos"], t, match["last"], match["tracks"][ally]["pos"][t]
                )
                outcome["support_followup"]["summary"] += outcome["observed_approach"]["summary"]
            evidence["farm_value"], outcome["farm_value"] = farm_comparison(
                match, h, t, lane_hits[h], jungle_hits[h], zones["camps"]
            )
            for frame in evidence["history"]:
                sec = frame["t"]
                last_seen = {e["hero"]: e["last_seen"] for e in frame["enemies"]}
                equipment = []
                for name, track in sorted(match["tracks"].items()):
                    ally = track["team"] == team
                    observed = sec if ally else last_seen.get(name)
                    equipment.append(
                        {
                            "hero": name,
                            "ally": ally,
                            "observed": observed,
                            "items": inventories.get((name, observed)),
                        }
                    )
                frame["equipment"] = equipment
                row = extras.get(sec, {})
                buildings = standing_towers(zones, deaths, sec) + zones["fountains"]
                sources = team_sources(
                    team,
                    sec,
                    match["tracks"],
                    match["wards"],
                    buildings,
                    match["fronts"].get(sec),
                    row.get("creeps"),
                )
                sources += extra_sources(team, row.get("watchers", ()), summons.get(sec, ()))
                frame["vision"] = vision_grid(sources, sec)
                frame["vision"]["extras_sampled"] = sec in extras
            evidence["catch"] = catch_comparison(evidence, display_names)
            yield evidence, action, outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "data/demos-2026-11")
    parser.add_argument("--matches", nargs="+", required=True, type=int)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("lane", "jungle", "wave"), default="lane")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output directory")
    if any(is_holdout(mid) for mid in args.matches):
        parser.error("holdout matches are excluded")
    means = read_json(ROOT / "knowledge/awareness/save-means-v2.json")["means"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as staging:
        folder = Path(staging) / "site"
        shutil.copytree(ASSETS, folder)
        shutil.copyfile(MAP, folder / "map.jpg")
        (folder / "actions").mkdir()
        (folder / "outcomes").mkdir()
        cases = []
        wave_sampling = {}
        for mid in sorted(set(args.matches)):
            coverage = wave_sampling.setdefault(mid, {}) if args.mode == "wave" else None
            for evidence, action, outcome in build_match(
                args.root, mid, means, args.mode, wave_coverage=coverage
            ):
                key = f"{mid}-{evidence['hero']}-{evidence['t']}"
                if args.mode != "lane":
                    key = args.mode + "-" + key
                cases.append({**evidence, "id": key})
                write_json(folder / "actions" / f"{key}.json", action)
                write_json(folder / "outcomes" / f"{key}.json", outcome)
        if not cases:
            if wave_sampling:
                missing = sum(
                    hero["missing_hero_seconds"]
                    for match in wave_sampling.values()
                    for hero in match["heroes"].values()
                )
                absent = [
                    mid for mid, match in wave_sampling.items() if not match["extras_file_present"]
                ]
                parser.error(
                    f"no eligible wave decisions; {missing} near-wave hero-seconds lack creep "
                    f"samples; matches without extras-v1: {absent}"
                )
            parser.error("no eligible decisions in these matches")
        write_json(
            folder / "cases.json",
            {
                "schema": f"{args.mode}-decision-review/1",
                "mode": args.mode,
                **({"wave_sampling": wave_sampling} if wave_sampling else {}),
                "names": names(),
                "cases": sorted(cases, key=lambda c: (c["match"], c["t"], c["hero"])),
            },
        )
        folder.rename(args.out)
    print(f"{len(cases)} decisions in {args.out}")


if __name__ == "__main__":
    main()
