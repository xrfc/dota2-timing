"""Death-risk alerts split by the main reason of each death (track B, U160).

For current reports before_fight groups the saved U171 fight-level evaluations by exact
death key; the older not-hit measure remains separately available.

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

from dota_items.data.death_tags import (
    coverage_reason,
    death_episode_index,
    death_tags,
    primary_reason,
)
from dota_items.experiments.awareness.death_risk_tables import load_risk_frame
from dota_items.modeling.awareness.death_risk_eval import (
    death_alerts,
    summarize_alerts,
    summarize_fight_alerts,
)

SCHEMA = "death-risk-by-reason/3"  # One row per match, hero and death second.
HORIZON = 20


def episode_index(folder):
    with (folder / "episodes.jsonl").open(encoding="utf-8") as stream:
        groups = death_episode_index(map(json.loads, stream))
    return {
        key: coverage_reason(group) or primary_reason(death_tags(group[0]))
        for key, group in groups.items()
    }


def reason_of(index, match_id, hero, t):
    return index.get((match_id, hero, t), coverage_reason([]))


def by_reason(found, index, summary=summarize_alerts):
    """[{reason, reason_zh, summary...}] from death_alerts output, largest group first."""
    groups = defaultdict(list)
    for row in found:
        groups[reason_of(index, row["match_id"], row["hero"], row["t"])].append(row)
    return [
        {"reason": key, "reason_zh": name, **summary(rows)}
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
    if args.out.exists():
        raise SystemExit(f"{args.out} already exists")
    report = json.loads((args.risk / "report.json").read_text(encoding="utf-8"))
    keys = ["match_id", "hero", "t"]
    expected, deaths, info = load_risk_frame(
        args.root / args.table,
        every=report.get("every_seconds", 0),
        allow_legacy=args.allow_legacy,
        columns=[*keys, "hit_recent", "dies_20"],
    )
    reported = (report.get("input") or {}).get("conditions_digest")
    if reported is not None and reported != info["conditions_digest"]:
        raise ValueError("Risk report and death table conditions differ")
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
    actual = frame.set_index(keys).sort_index()
    reference = expected.set_index(keys).sort_index()
    if not actual.index.is_unique or not actual.index.equals(reference.index):
        raise ValueError("Risk report and table prediction keys differ")
    if not np.array_equal(actual.hit_recent, reference.hit_recent):
        raise ValueError("Recent damage labels differ")
    if "y" in oof and not np.array_equal(
        frame.assign(y=oof["y"]).set_index(keys).sort_index().y, reference.dies_20
    ):
        raise ValueError("Death labels differ")
    unique_deaths = pd.DataFrame(deaths).drop_duplicates(keys)
    found = death_alerts(frame, unique_deaths, oof["boosting"], threshold, HORIZON)
    index = episode_index(args.episodes)
    rows = by_reason(found, index)
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
    if "fight_alerts" in report:
        raw = pd.read_csv(args.risk / "fight-alerts.csv")
        fights = raw.drop_duplicates()
        result["duplicate_fight_evaluations"] = len(raw) - len(fights)
        scored = {(r["match_id"], r["hero"], r["t"]) for r in found}
        fight_keys = list(zip(fights.match_id, fights.hero, fights.t, strict=True))
        expected_keys = scored
        if "has_sample" in fights:
            positions = info["positions"]
            expected_keys = set(
                unique_deaths.loc[unique_deaths.position.isin(positions), keys].itertuples(
                    index=False, name=None
                )
            )
            sampled_keys = set(
                fights.loc[fights.has_sample, keys].itertuples(index=False, name=None)
            )
            if sampled_keys != scored:
                raise ValueError("Fight sample coverage differs from the table")
        if len(fight_keys) != len(set(fight_keys)) or set(fight_keys) != expected_keys:
            raise ValueError("Fight evaluation and death samples differ")
        result["before_fight"] = by_reason(fights.to_dict("records"), index, summarize_fight_alerts)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    for row in rows:
        print(row, flush=True)


if __name__ == "__main__":
    main()
