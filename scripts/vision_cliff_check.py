"""Are vision-model errors concentrated near cliff edges? (U186, exploration only)

    PYTHONPATH=src .venv/bin/python scripts/vision_cliff_check.py \
        --root data/demos-2026-11 --out reports/vision-cliff-check-2026-11-20

Same samples and model as the best variant of vision_check.py (sight model, only high
ground hides, every lane creep): every `--step` seconds, every living hero not under Smoke.
For each sample it records the hero's distance to the nearest cliff edge (a cell whose
height level differs from a neighbour's, among levels 1-2), and, for the closest source in
range, that source's distance to a cliff edge, the source kind, and what blocked it. Error
rates are then grouped by distance band. If the 64-unit grid were the cause, errors should
be clearly higher within a cell or two of an edge. Holdout matches skipped (U133).
"""

import argparse
import collections
import gzip
import json
import math
import pickle
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.gank_review import smoke_intervals, smoked_at
from dota_items.data.vision_sim import (
    CELL,
    RANGE,
    SIZE,
    Terrain,
    cell_of,
    is_day,
    sees,
    team_sources,
)

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/map-reference-2026-10-26-v1/coordinates/data"
ZONES = ROOT / "knowledge/awareness/map-zones-v1.json"
BANDS = (64, 128, 256, 512)
MODEL, HIGH = "sight", 2


def load(path):
    with path.open("rb") as stream:
        return pickle.load(stream)  # written by this project's scripts, local only


def edge_distance(elevation):
    """Cells to the nearest cliff edge (level 1 next to 2, either way), by breadth-first search."""
    far = SIZE * SIZE
    dist = [[far] * SIZE for _ in range(SIZE)]
    queue = collections.deque()
    for i in range(SIZE):
        for j in range(SIZE):
            here = elevation[i][j]
            if here not in (1, 2):
                continue
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = i + di, j + dj
                if 0 <= a < SIZE and 0 <= b < SIZE and elevation[a][b] in (1, 2):
                    if elevation[a][b] != here:
                        dist[i][j] = 0
                        queue.append((i, j))
                        break
    while queue:
        i, j = queue.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < SIZE and 0 <= b < SIZE and dist[a][b] > dist[i][j] + 1:
                dist[a][b] = dist[i][j] + 1
                queue.append((a, b))
    return dist


def band(cells):
    units = cells * CELL
    for limit in BANDS:
        if units < limit:
            return f"<{limit}"
    return f">={BANDS[-1]}"


def why_blocked(source, target, terrain):
    """'height' if the target stands higher, 'tree' or 'ground' for the first blocked cell."""
    mine, theirs = terrain.level(*source), terrain.level(*target)
    if theirs > mine and theirs >= HIGH:
        return "height"
    distance = math.dist(source, target)
    steps = int(distance // 32)
    first, last = cell_of(*source), cell_of(*target)
    for n in range(1, steps):
        x = source[0] + (target[0] - source[0]) * n / steps
        y = source[1] + (target[1] - source[1]) * n / steps
        cell = cell_of(x, y)
        if cell in (first, last):
            continue
        if cell in terrain.trees:
            return "tree"
        if terrain.elevation[cell[0]][cell[1]] > max(mine, HIGH - 1):
            return "ground"
    return "none"


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    elevation = json.loads((MAP / "elevationdata.json").read_text())["data"]
    trees = json.loads((MAP / "mapdata.json").read_text())["data"]["ent_dota_tree"]
    terrain = Terrain(elevation, [(t["x"], t["y"]) for t in trees])
    edges = edge_distance(elevation)
    zones = json.loads(ZONES.read_text(encoding="utf-8"))

    def edge_band(spot):
        i, j = cell_of(*spot)
        return band(edges[i][j]) if 0 <= i < SIZE and 0 <= j < SIZE else "off"

    ids = sorted(
        int(p.stem)
        for p in (args.root / "gank-clip-inputs-v1").glob("*.pkl")
        if (args.root / "gank-inputs-v2" / p.name).exists()
        and (args.root / "creeps-v1" / p.name.replace(".pkl", ".jsonl.gz")).exists()
        and not is_holdout(int(p.stem))
    )
    if args.limit:
        ids = ids[: args.limit]
    by_target = collections.defaultdict(lambda: [0, 0, 0, 0])
    blocked = collections.Counter()
    used = 0
    for mid in ids:
        clip_inputs = load(args.root / "gank-clip-inputs-v1" / f"{mid}.pkl")
        if "wards" not in clip_inputs:
            continue
        with gzip.open(args.root / "creeps-v1" / f"{mid}.jsonl.gz", "rt") as stream:
            stream.readline()
            creeps = {row["t"]: row["creeps"] for row in map(json.loads, stream)}
        match = load(args.root / "gank-inputs-v2" / f"{mid}.pkl")
        tracks, seen, combat = match["tracks"], match["seen"], match["combat"]
        deaths = tower_deaths(combat)
        smoke = smoke_intervals(combat, match["last"])
        used += 1
        for second in range(0, match["last"] + 1, args.step):
            towers = standing_towers(zones, deaths, second) + zones["fountains"]
            alive = creeps.get(second, [])
            sources = {
                team: team_sources(
                    team,
                    second,
                    tracks,
                    clip_inputs["wards"],
                    towers,
                    match["fronts"].get(second),
                    alive,
                )  # fmt: skip
                for team in (2, 3)
            }
            for hero, track in tracks.items():
                spot = track["pos"].get(second)
                if spot is None or smoked_at(smoke, hero, second):
                    continue
                other = 5 - track["team"]
                truth = second in seen.get((hero, other), ())
                said = any(
                    sees(s, spot, kind, second, terrain, MODEL, HIGH) for kind, s in sources[other]
                )
                by_target[edge_band(spot)][2 * truth + said] += 1
                if truth and not said:
                    day = 0 if is_day(second) else 1
                    near = [
                        (math.dist(s, spot), kind, s)
                        for kind, s in sources[other]
                        if math.dist(s, spot) <= RANGE[kind][day]
                    ]
                    if not near:
                        blocked[("no_source_in_range", "-", "-", edge_band(spot))] += 1
                        continue
                    _, kind, s = min(near)
                    kind = "ward" if kind == "observer" else kind
                    blocked[
                        (why_blocked(s, spot, terrain), kind, edge_band(s), edge_band(spot))
                    ] += 1
        print(f"{mid} [{used}/{len(ids)}]", flush=True)

    def rates(c):
        hid_no, hid_yes, vis_no, vis_yes = c
        total = sum(c)
        return {
            "samples": total,
            "accuracy": round((hid_no + vis_yes) / max(1, total), 4),
            "visible_missed": round(vis_no / max(1, vis_no + vis_yes), 4),
            "hidden_said_visible": round(hid_yes / max(1, hid_no + hid_yes), 4),
        }

    result = {
        "use": "exploration_only",
        "model": f"{MODEL}/high_from_{HIGH}/creeps",
        "matches": used,
        "step": args.step,
        "by_target_edge_distance": {k: rates(v) for k, v in sorted(by_target.items())},
        "missed_visible_breakdown": [
            {"cause": a, "closest_source": b, "source_edge": c, "target_edge": d, "count": n}
            for (a, b, c, d), n in blocked.most_common()
        ],
    }
    text = json.dumps(result, ensure_ascii=False, indent=1)
    (args.out / "vision-cliff-check.json").write_text(text + "\n", encoding="utf-8")
    print(json.dumps(result["by_target_edge_distance"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
