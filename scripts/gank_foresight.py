"""Exploratory: is a gank visible in advance from what the player's team could see?

    PYTHONPATH=src .venv/bin/python scripts/gank_foresight.py \
        --root data/demos-2026-11 --episodes reports/gank-episodes-2026-11-11-r6 \
        --out reports/gank-foresight-2026-11-12

Reads the frozen round's `episodes.jsonl` and the per-match input cache written by
`detect_ganks.py` (`<root>/gank-inputs-v2/`); holdout matches are refused (U133). For each
gank (death or escape by a save) it takes a visible-only snapshot `--lead` seconds before
the start, and for the same players snapshots at quiet seconds (no episode within
`--margin` seconds). Writes `foresight.json`: medians and the AUC of each raw feature.
No model is trained; the numbers describe, they are not an accuracy.
"""

import argparse
import json
import pickle
from collections import Counter
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.gank_foresight import compare, quiet_seconds, snapshot

GANK_LABELS = ("death", "save_escape")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lead", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--start", type=int, default=600, help="first quiet second sampled")
    parser.add_argument("--step", type=int, default=30)
    parser.add_argument("--margin", type=int, default=30)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    by_match = {}
    with (args.episodes / "episodes.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            episode = json.loads(line)
            by_match.setdefault(episode["match_id"], []).append(episode)
    before = {lead: [] for lead in args.lead}
    quiet = []
    missing_before, missing_quiet = Counter(), Counter()
    for mid, episodes in sorted(by_match.items()):
        if is_holdout(mid):
            raise SystemExit(f"{mid} is in the track B holdout (U133)")
        with (args.root / "gank-inputs-v2" / f"{mid}.pkl").open("rb") as stream:
            match = pickle.load(stream)  # written by detect_ganks.py, local only
        tracks, seen = match["tracks"], match["seen"]
        for victim in sorted({e["victim"] for e in episodes}):
            mine = [e for e in episodes if e["victim"] == victim]
            for episode in mine:
                # Only ganks after the laning minutes, to match the quiet seconds.
                if episode["label"] not in GANK_LABELS or episode["t0"] < args.start:
                    continue
                for lead in args.lead:
                    row = snapshot(victim, episode["t0"] - lead, tracks, seen)
                    if row:
                        before[lead].append(row)
                        if lead == args.lead[0]:
                            missing_before[row["enemies_missing"]] += 1
            for second in quiet_seconds(victim, tracks, mine, args.start, args.step, args.margin):
                row = snapshot(victim, second, tracks, seen)
                if row:
                    quiet.append(row)
                    missing_quiet[row["enemies_missing"]] += 1
    result = {
        "use": "exploration_only",
        "frozen_round": str(args.episodes),
        "matches": len(by_match),
        "start": args.start,
        "step": args.step,
        "margin": args.margin,
        "quiet_snapshots": len(quiet),
        "by_lead": {
            str(lead): {"gank_snapshots": len(rows), "features": compare(rows, quiet)}
            for lead, rows in before.items()
        },
        "enemies_missing_share": {
            "before_gank": {
                k: round(v / sum(missing_before.values()), 3)
                for k, v in sorted(missing_before.items())
            },
            "quiet": {
                k: round(v / sum(missing_quiet.values()), 3)
                for k, v in sorted(missing_quiet.items())
            },
        },  # fmt: skip
    }
    text = json.dumps(result, ensure_ascii=False, indent=1)
    (args.out / "foresight.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
