"""Does blocking sight with each tree's real footprint beat whole 64-unit tree cells? (U186)

    PYTHONPATH=src .venv/bin/python scripts/vision_tree_check.py \
        --root data/demos-2026-11 --out reports/vision-tree-check-2026-11-20

Exploration only. Same samples and best model as vision_check.py (sight model, only high
ground hides, every lane creep). The current model treats a tree as filling its whole
64-unit cell. Here a tree blocks a line of sight only where the line passes within `r`
units of the tree's centre, for several `r`. Matches are split in two halves (alternate
match ids): pick on one half, confirm on the other, as in map-knowledge-design §10.4.
Cut trees are still unknown (the replays carry no tree-cut record, 2026-11-20).
Holdout matches skipped (U133).
"""

import argparse
import gzip
import json
import math
import pickle
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.gank_review import smoke_intervals, smoked_at
from dota_items.data.vision_sim import OFFSET, RANGE, STEP, Terrain, cell_of, is_day, team_sources

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/map-reference-2026-10-26-v1/coordinates/data"
ZONES = ROOT / "knowledge/awareness/map-zones-v1.json"
HIGH = 2
RADII = ("cell", 32, 48, 64, 96)
BUCKET = 128


def load(path):
    with path.open("rb") as stream:
        return pickle.load(stream)  # written by this project's scripts, local only


class TreeTerrain(Terrain):
    """Terrain whose trees block within `radius` of their centre instead of a whole cell."""

    def __init__(self, elevation, trees, radius):
        super().__init__(elevation, trees)
        self.radius = radius
        self.points = {}
        for x, y in trees:
            px, py = x + OFFSET, y + OFFSET
            self.points.setdefault((px // BUCKET, py // BUCKET), []).append((px, py))

    def intersects_tree(self, source, target):
        """Test the closed segment against tree disks, including the endpoint cells."""
        x, y = source
        tx, ty = target
        dx, dy = tx - x, ty - y
        length2 = dx * dx + dy * dy
        radius = self.radius
        left = math.floor((min(x, tx) - radius) / BUCKET)
        right = math.floor((max(x, tx) + radius) / BUCKET)
        bottom = math.floor((min(y, ty) - radius) / BUCKET)
        top = math.floor((max(y, ty) + radius) / BUCKET)
        for i in range(left, right + 1):
            for j in range(bottom, top + 1):
                for px, py in self.points.get((i, j), ()):
                    projection = ((px - x) * dx + (py - y) * dy) / length2 if length2 else 0
                    share = max(0, min(1, projection))
                    if (px - x - share * dx) ** 2 + (py - y - share * dy) ** 2 <= radius**2:
                        return True
        return False

    def clear(self, source, target, height):
        distance = math.dist(source, target)
        steps = int(distance // STEP)
        first, last = cell_of(*source), cell_of(*target)
        for n in range(1, steps):
            share = n / steps
            x = source[0] + (target[0] - source[0]) * share
            y = source[1] + (target[1] - source[1]) * share
            cell = cell_of(x, y)
            if cell in (first, last):
                continue
            if self.level(x, y) > height:
                return False
        return not self.intersects_tree(source, target)


def sees(source, target, kind, second, terrain):
    if math.dist(source, target) > RANGE[kind][0 if is_day(second) else 1]:
        return False
    mine, theirs = terrain.level(*source), terrain.level(*target)
    if theirs > mine and theirs >= HIGH:
        return False
    return terrain.clear(source, target, max(mine, HIGH - 1))


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
    trees = [
        (t["x"], t["y"])
        for t in json.loads((MAP / "mapdata.json").read_text())["data"]["ent_dota_tree"]
    ]
    terrains = {
        r: Terrain(elevation, trees) if r == "cell" else TreeTerrain(elevation, trees, r)
        for r in RADII
    }
    zones = json.loads(ZONES.read_text(encoding="utf-8"))
    ids = sorted(
        int(p.stem)
        for p in (args.root / "gank-clip-inputs-v1").glob("*.pkl")
        if (args.root / "gank-inputs-v2" / p.name).exists()
        and (args.root / "creeps-v1" / p.name.replace(".pkl", ".jsonl.gz")).exists()
        and not is_holdout(int(p.stem))
    )
    if args.limit:
        ids = ids[: args.limit]
    counts = {(half, r): [0, 0, 0, 0] for half in (0, 1) for r in RADII}
    used = 0
    for n, mid in enumerate(ids):
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
        half = n % 2
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
                truth = second in seen.get((hero, 5 - track["team"]), ())
                for r, terrain in terrains.items():
                    said = any(
                        sees(s, spot, kind, second, terrain)
                        for kind, s in sources[5 - track["team"]]
                    )
                    counts[(half, r)][2 * truth + said] += 1
        print(f"{mid} [{used}/{len(ids)}]", flush=True)
    result = {
        "tree_geometry": "segment_circle",
        "use": "exploration_only",
        "matches": used,
        "step": args.step,
        "halves": {},
    }
    for (half, r), (hid_no, hid_yes, vis_no, vis_yes) in counts.items():
        total = hid_no + hid_yes + vis_no + vis_yes
        result["halves"].setdefault(f"half_{half}", {})[str(r)] = {
            "samples": total,
            "accuracy": round((hid_no + vis_yes) / max(1, total), 4),
            "visible_and_model_says_visible": round(vis_yes / max(1, vis_no + vis_yes), 4),
            "hidden_and_model_says_hidden": round(hid_no / max(1, hid_no + hid_yes), 4),
        }
    text = json.dumps(result, ensure_ascii=False, indent=1)
    (args.out / "vision-tree-check.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
