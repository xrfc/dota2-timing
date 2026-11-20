"""Build a 7.41f lane-decision review from existing non-holdout replay data.

PYTHONPATH=src .venv/bin/python scripts/lane_decision_review.py --matches 9080976703 \
    --out reports/lane-decisions
Serve the output directory on localhost with python -m http.server --bind 127.0.0.1.
"""

import argparse
import gzip
import json
import shutil
import tempfile
from pathlib import Path

from detect_ganks import match_inputs
from gank_review import MAP, names

from dota_items.data.awareness_split import is_holdout
from dota_items.data.death_risk import death_times
from dota_items.data.lane_decisions import farm_seconds, make_cases
from dota_items.storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name("lane_decision_assets")


def build_match(root, mid, means):
    if is_holdout(mid):
        raise ValueError(f"{mid} is reserved for holdout evaluation")
    meta = read_json(root / "meta" / f"{mid}.json")
    if meta.get("match_id") != mid or meta.get("patch") != 60:
        raise ValueError(f"{mid}: expected the patch-60 cohort used for the 7.41f analysis")
    match = match_inputs(root, mid, root / "gank-inputs-v2")
    heroes = sorted(h for h, pos in match["positions"].items() if pos == 1)
    visibility = {key: sorted(times) for key, times in match["seen"].items()}
    with gzip.open(root / "parsed" / f"{mid}.normalized.json.gz", "rt") as stream:
        events = json.load(stream)["context"]["channels"]["combat_log"]
    hits = {h: farm_seconds(events, h, match["tracks"][h]["team"]) for h in heroes}
    del events
    states = {h: {} for h in heroes}
    wanted = {h: set(times) for h, times in hits.items()}
    with gzip.open(root / "state-v3" / f"{mid}.jsonl.gz", "rt") as stream:
        header = json.loads(next(stream))
        if header.get("match_id") != mid or header.get("schema") != "gem-state-capture/3":
            raise ValueError(f"{mid}: unexpected state header")
        for row in map(json.loads, stream):
            for state in row["heroes"]:
                h = state["hero"]
                if h in wanted and row["t"] in wanted[h]:
                    states[h][row["t"]] = state
    for h in heroes:
        yield from make_cases(
            match, mid, h, hits[h], visibility, states[h], means, death_times(match["combat"], h)
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "data/demos-2026-11")
    parser.add_argument("--matches", nargs="+", required=True, type=int)
    parser.add_argument("--out", type=Path, required=True)
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
        for mid in sorted(set(args.matches)):
            for evidence, action, outcome in build_match(args.root, mid, means):
                key = f"{mid}-{evidence['hero']}-{evidence['t']}"
                cases.append({**evidence, "id": key})
                write_json(folder / "actions" / f"{key}.json", action)
                write_json(folder / "outcomes" / f"{key}.json", outcome)
        if not cases:
            parser.error("no eligible lane decisions in these matches")
        write_json(
            folder / "cases.json",
            {
                "schema": "lane-decision-review/1",
                "names": names(),
                "cases": sorted(cases, key=lambda c: (c["match"], c["t"], c["hero"])),
            },
        )
        folder.rename(args.out)
    print(f"{len(cases)} decisions in {args.out}")


if __name__ == "__main__":
    main()
