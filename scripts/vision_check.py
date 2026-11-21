"""Check the vision approximation against the replays' own visibility record (U152).

    PYTHONPATH=src .venv/bin/python scripts/vision_check.py \
        --root data/demos-2026-11 --out reports/vision-check-2026-11-13

For matches that have both local caches (`gank-inputs-v2` from detect_ganks.py and
`gank-clip-inputs-v1` from gank_review.py build, which holds the wards), every `--step`
seconds and for every living hero it asks each model of data.vision_sim whether the other
team's sources see him (with `--creeps` once with only the wave fronts and once with every
lane creep from `creeps-v1/`; then only matches that have that file are used), and
compares with the replay's record of whether that team did.
With `--extras` it adds, one at a time and then together ("full"), the Watchers a team
holds, its summons and illusions, and treats a hero whose state says invisible as hidden.
Heroes under Smoke of Deceit are left out (hidden by a rule the model does not have).
Holdout matches are skipped (U133). Writes `vision-check.json`. Description only.
"""

import argparse
import gzip
import json
import pickle
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.gank_review import smoke_intervals, smoked_at
from dota_items.data.unit_state import has
from dota_items.data.vision_sim import MODELS, Terrain, extra_sources, team_sources, visible

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/map-reference-2026-10-26-v1/coordinates/data"
ZONES = ROOT / "knowledge/awareness/map-zones-v1.json"


def load(path):
    with path.open("rb") as stream:
        return pickle.load(stream)  # written by this project's scripts, local only


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--creeps", action="store_true", help="also use every lane creep")
    parser.add_argument(
        "--extras",
        action="store_true",
        help="use extras-v1 (creeps, watcher holders) and state v3 (summons, invisibility)",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    elevation = json.loads((MAP / "elevationdata.json").read_text())["data"]
    trees = json.loads((MAP / "mapdata.json").read_text())["data"]["ent_dota_tree"]
    terrain = Terrain(elevation, [(t["x"], t["y"]) for t in trees])
    zones = json.loads(ZONES.read_text(encoding="utf-8"))
    ids = sorted(
        int(p.stem)
        for p in (args.root / "gank-clip-inputs-v1").glob("*.pkl")
        if (args.root / "gank-inputs-v2" / p.name).exists() and not is_holdout(int(p.stem))
    )
    if args.limit:
        ids = ids[: args.limit]
    variants = [
        (model, high) for model in MODELS for high in (1, 2) if model != "radius" or high == 1
    ]
    modes = ("fronts", "creeps") if args.creeps or args.extras else ("fronts",)
    if args.extras:
        modes += ("watchers", "summons", "full")
    counts = {
        f"{model}/high_from_{high}/{mode}": [0, 0, 0, 0]
        for model, high in variants
        for mode in modes
    }
    used = 0
    for mid in ids:
        clip_inputs = load(args.root / "gank-clip-inputs-v1" / f"{mid}.pkl")
        if "wards" not in clip_inputs:
            continue  # cache written before wards were kept
        creeps, watchers, summons, hidden = None, {}, {}, {}
        if args.creeps or args.extras:
            folder = "extras-v1" if args.extras else "creeps-v1"
            path = args.root / folder / f"{mid}.jsonl.gz"
            if not path.exists():
                continue
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                stream.readline()  # header
                rows = [json.loads(line) for line in stream]
            creeps = {row["t"]: row["creeps"] for row in rows}
            watchers = {row["t"]: row.get("watchers", ()) for row in rows}
        if args.extras:
            with gzip.open(
                args.root / "state-v3" / f"{mid}.jsonl.gz", "rt", encoding="utf-8"
            ) as stream:
                stream.readline()
                for line in stream:
                    row = json.loads(line)
                    if row["t"] % args.step:
                        continue
                    summons[row["t"]] = row["world"].get("summons") or ()
                    hidden[row["t"]] = {
                        h["hero"]
                        for h in row["heroes"]
                        if has(h.get("unit_state_raw"), "invisible")
                    }
        match = load(args.root / "gank-inputs-v2" / f"{mid}.pkl")
        tracks, seen, combat = match["tracks"], match["seen"], match["combat"]
        deaths = tower_deaths(combat)
        smoke = smoke_intervals(combat, match["last"])
        used += 1
        for second in range(0, match["last"] + 1, args.step):
            # standing_towers also returns the ancients; the fountains always stand.
            towers = standing_towers(zones, deaths, second) + zones["fountains"]
            fronts = match["fronts"].get(second)
            wards = clip_inputs["wards"]
            sources = {
                ("fronts", team): team_sources(team, second, tracks, wards, towers, fronts)
                for team in (2, 3)
            }
            if creeps is not None:
                alive = creeps.get(second, [])
                for team in (2, 3):
                    base = team_sources(team, second, tracks, wards, towers, fronts, alive)
                    sources[("creeps", team)] = base
                    if args.extras:
                        held = extra_sources(team, watchers.get(second, ()))
                        made = extra_sources(team, (), summons.get(second, ()))
                        sources[("watchers", team)] = base + held
                        sources[("summons", team)] = base + made
                        sources[("full", team)] = base + held + made
            for hero, track in tracks.items():
                spot = track["pos"].get(second)
                if spot is None or smoked_at(smoke, hero, second):
                    continue
                other = 5 - track["team"]
                truth = second in seen.get((hero, other), ())
                for model, high in variants:
                    for mode in modes:
                        said = visible(spot, sources[(mode, other)], second, terrain, model, high)
                        if mode == "full" and hero in hidden.get(second, ()):
                            said = False  # invisible; true sight is not modelled
                        counts[f"{model}/high_from_{high}/{mode}"][2 * truth + said] += 1
        print(f"{mid} [{used}/{len(ids)}]", flush=True)
    result = {"use": "exploration_only", "matches": used, "step": args.step, "models": {}}
    for name, (hid_no, hid_yes, vis_no, vis_yes) in counts.items():
        total = hid_no + hid_yes + vis_no + vis_yes
        result["models"][name] = {
            "hero_seconds": total,
            "recorded_visible": vis_no + vis_yes,
            "accuracy": round((hid_no + vis_yes) / total, 4),
            "visible_and_model_says_visible": round(vis_yes / max(1, vis_no + vis_yes), 4),
            "hidden_and_model_says_hidden": round(hid_no / max(1, hid_no + hid_yes), 4),
        }
    text = json.dumps(result, ensure_ascii=False, indent=1)
    (args.out / "vision-check.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
