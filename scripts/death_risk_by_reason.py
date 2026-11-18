"""Death-risk alerts split by the main reason of each death (track B, U160).

Joins the out-of-fold scores of train_death_risk.py with the B0 episodes: every
position 1 death that falls inside a death episode gets that episode's main reason
(data.death_tags.primary_reason; the order of the reasons is the assistant's draft, U156).
The reasons are omniscient labels used to explain the model, never model input (U55).

For each reason it reports the share of deaths with an alert on a sample not hit in the
last 3 seconds within the 20 seconds before the death (threshold of the risk report: 5%
false alarms on such samples; modeling.awareness.death_risk_eval.death_alerts), the
median lead and the median of the highest risk in those 20 seconds. The share is not a
"before the first hit of the fight" recall.

    death_risk_by_reason.py --root data/demos-2026-11 --table death-risk-v4 \
        --risk reports/<risk report> \
        --episodes reports/gank-episodes-2026-11-17-r7-draft2 --out reports/<folder>
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from dota_items.data.death_tags import death_tags, primary_reason
from dota_items.experiments.awareness.death_risk_tables import load_tables
from dota_items.modeling.awareness.death_risk_eval import death_alerts, summarize_alerts

SCHEMA = "death-risk-by-reason/2"  # 2: shared alert measure, renamed (not hit in 3 s)
HORIZON = 20


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


def by_reason(found, index):
    """[{reason, reason_zh, summary...}] from death_alerts output, largest group first."""
    groups = defaultdict(list)
    for row in found:
        groups[reason_of(index, row["match_id"], row["hero"], row["t"])].append(row)
    return [
        {"reason": key, "reason_zh": name, **summarize_alerts(rows)}
        for (key, name), rows in sorted(groups.items(), key=lambda kv: -len(kv[1]))
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--allow-legacy", action="store_true")
    parser.add_argument("--risk", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    _, _, deaths, info = load_tables(args.root / args.table, args.allow_legacy)
    args.out.mkdir(parents=True, exist_ok=False)
    report = json.loads((args.risk / "report.json").read_text(encoding="utf-8"))
    threshold = report["alerts"]["threshold"]
    oof = np.load(args.risk / "out-of-fold.npz")
    frame = pd.DataFrame(
        {
            "match_id": oof["match_id"],
            "hero": oof["hero"].astype(str),
            "t": oof["t"],
            "hit_recent": oof["hit_recent"],
        }
    )
    found = death_alerts(frame, pd.DataFrame(deaths), oof["boosting"], threshold, HORIZON)
    rows = by_reason(found, episode_index(args.episodes))
    result = {
        "schema": SCHEMA,
        "use": "explains the risk model by omniscient death reasons; review only (U55)",
        "input": info,
        "risk_report": str(args.risk),
        "episodes": str(args.episodes),
        "threshold": threshold,
        "horizon": HORIZON,
        "alert_measure": "alert on a sample not hit in the last 3 s; not 'before the first hit'",
        "reasons": rows,
    }
    (args.out / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    for row in rows:
        print(row, flush=True)


if __name__ == "__main__":
    main()
