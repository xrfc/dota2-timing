"""Death-risk alerts split by the main reason of each death (track B, U160).

Joins the out-of-fold scores of train_death_risk.py with the B0 episodes: every
position 1 death that falls inside a death episode gets that episode's main reason
(data.death_tags.primary_reason; the order of the reasons is the assistant's draft, U156).
The reasons are omniscient labels used to explain the model, never model input (U55).

For each reason it reports how many deaths the alert (the threshold of the risk report:
5% false alarms on not-yet-hit samples) caught before he was first hit, the median lead,
and the median of the highest risk in the 20 seconds before the death.

    death_risk_by_reason.py --root data/demos-2026-11 \
        --risk reports/death-risk-v2-2026-11-17 \
        --episodes reports/gank-episodes-2026-11-17-r7-draft2 --out reports/<folder>
"""

import argparse
import json
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np

from dota_items.data.death_tags import death_tags, primary_reason

SCHEMA = "death-risk-by-reason/1"
HORIZON = 20


def load_deaths(root, table):
    deaths = []
    for path in sorted((root / table).glob("*.pkl")):
        with path.open("rb") as stream:
            deaths += pickle.load(stream)["deaths"]  # build_death_risk_table.py, local only
    return deaths


def episode_index(folder):
    """{(match, hero): [(t0, end, reason id, reason zh)]} for the episodes ending in death."""
    index = defaultdict(list)
    with (folder / "episodes.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            episode = json.loads(line)
            if episode["outcome"] != "death":
                continue
            key, name = primary_reason(death_tags(episode))
            index[(episode["match_id"], episode["victim"])].append(
                (episode["t0"], episode["end"], key, name)
            )
    return index


def reason_of(index, match_id, hero, t, slack=2):
    for t0, end, key, name in index.get((match_id, hero), ()):
        if t0 <= t <= end + slack:
            return key, name
    return "no_episode", "没有对应片段"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--risk", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--table", default="death-risk-v2")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=False)
    report = json.loads((args.risk / "report.json").read_text(encoding="utf-8"))
    threshold = report["alerts"]["threshold"]
    oof = np.load(args.risk / "out-of-fold.npz")
    series = defaultdict(list)
    for mid, hero, t, score, hit in zip(
        oof["match_id"], oof["hero"], oof["t"], oof["boosting"], oof["hit_recent"], strict=True
    ):
        series[(int(mid), str(hero))].append((int(t), float(score), int(hit)))
    index = episode_index(args.episodes)
    groups = defaultdict(list)
    for death in load_deaths(args.root, args.table):
        key = (int(death["match_id"]), death["hero"])
        if key not in series:
            continue  # not a tracked position 1 hero
        t = death["t"]
        before = [(s, score, hit) for s, score, hit in series[key] if t - HORIZON <= s < t]
        if not before:
            continue
        alerts = [s for s, score, hit in before if not hit and score >= threshold]
        reason = reason_of(index, *key, t)
        groups[reason].append(
            {
                "alerted": bool(alerts),
                "lead": t - min(alerts) if alerts else None,
                "peak": max(score for _, score, _ in before),
            }
        )
    rows = []
    for (key, name), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        leads = [i["lead"] for i in items if i["alerted"]]
        rows.append(
            {
                "reason": key,
                "reason_zh": name,
                "deaths": len(items),
                "alerted_before_being_hit": round(sum(i["alerted"] for i in items) / len(items), 3),
                "median_lead_seconds": float(np.median(leads)) if leads else None,
                "median_peak_risk": round(float(np.median([i["peak"] for i in items])), 3),
            }
        )
    result = {
        "schema": SCHEMA,
        "use": "explains the risk model by omniscient death reasons; review only (U55)",
        "risk_report": str(args.risk),
        "episodes": str(args.episodes),
        "threshold": threshold,
        "horizon": HORIZON,
        "reasons": rows,
    }
    (args.out / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    for row in rows:
        print(row, flush=True)


if __name__ == "__main__":
    main()
