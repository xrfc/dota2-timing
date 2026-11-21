"""Compare death-risk reports trained at different sampling steps, fairly (U174, U176).

Each report of train_death_risk.py sets its alert threshold at 5% false alarms per
sample. A finer step checks more often, so that threshold gives more alarms per hour and
more deaths "alerted". This script re-reads the out-of-fold scores of every report and
sets each threshold to the same number of false-alarm onsets per hour outside fights as
the first report, and within its false-alarm time share, then gives the fight-level alert shares.

    compare_death_risk_steps.py --root data/demos-2026-11 --table death-risk-v4-1s \
        --reports reports/death-risk-v4-every5-2026-11-18 reports/death-risk-v4-every3-2026-11-18
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dota_items.experiments.awareness.death_risk_tables import load_parts, load_risk_frame
from dota_items.modeling.awareness.death_risk_eval import (
    false_alarm_rate,
    fight_alerts,
    fight_spans,
    in_fight,
    summarize_fight_alerts,
    threshold_for_rate,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--reports", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    folder = args.root / args.table
    parts, info = load_parts(folder)
    spans = fight_spans(parts["hits"], parts["contact"])
    del parts
    keys = ["match_id", "hero", "t"]
    base, deaths, _ = load_risk_frame(folder, columns=[*keys, "dies_20"])
    base = base.set_index(keys)["dies_20"].sort_index()
    deaths = pd.DataFrame(deaths)
    rows, target = [], None
    for path in args.reports:
        report = json.loads((path / "report.json").read_text(encoding="utf-8"))
        if report["input"]["conditions_digest"] != info["conditions_digest"]:
            parser.error(f"{path}: input differs from comparison table")
        step = report["every_seconds"]
        if step <= 0 or step % info["params"]["step"]:
            parser.error(f"{path}: incompatible sampling step")
        scores = np.load(path / "out-of-fold.npz", allow_pickle=False)
        frame = pd.DataFrame({k: scores[k] for k in ("match_id", "hero", "t")})
        y, boosting = scores["y"], scores["boosting"]
        expected = base[(base.index.get_level_values("t") - info["params"]["start"]) % step == 0]
        actual = frame.assign(label=y).set_index(keys)["label"].sort_index()
        if not actual.index.equals(expected.index) or not np.array_equal(actual, expected):
            parser.error(f"{path}: prediction rows or death labels differ from the table")
        outside = ~in_fight(frame, spans)
        if target is None:
            threshold = report["fight_alerts"]["threshold"]
            target, max_share = false_alarm_rate(frame, boosting, y, outside, threshold, step)
        else:
            threshold = threshold_for_rate(
                frame, boosting, y, outside, step, target, max_share=max_share
            )
        onsets, share = false_alarm_rate(frame, boosting, y, outside, threshold, step)
        found = fight_alerts(frame, deaths, boosting, threshold, 20, spans)
        rows.append({
            "report": str(path),
            "every_seconds": step,
            "threshold": threshold,
            "false_alarm_onsets_per_hour": round(onsets, 2),
            "share_of_time_in_false_alarm": round(share, 4),
            **summarize_fight_alerts(found),
        })  # fmt: skip
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "report.json").write_text(
            json.dumps({"schema": "death-risk-step-comparison/1",
                        "onsets_per_hour_target": target, "false_alarm_share_limit": max_share,
                        "rows": rows},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )  # fmt: skip


if __name__ == "__main__":
    main()
