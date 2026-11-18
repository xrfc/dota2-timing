"""Baselines for "will he die in the next seconds" (track B, B2 baseline, U160).

Reads one table folder of build_death_risk_table.py (checked by
experiments.awareness.death_risk_tables: schema, generation conditions, match IDs and
the U133 holdout) and compares, by match-grouped cross-validation:

* rule      enemies in sight within 1500 plus missing health, no fitting;
* logistic  standardised logistic regression;
* boosting  sklearn HistGradientBoostingClassifier.

A death is rare, so the report leads with average precision, precision at fixed recall,
recall at a fixed false-alarm rate and calibration. Everything is given on all samples
and on the samples not hit by an enemy hero in the last 3 seconds (`hit_recent == 0`).
That subset is NOT "before the first hit of the fight" (contracts.death_risk).

The boosting model is also refitted on the older feature sets the table holds, on the
same rows, so the gain of new features is measured on identical samples.

    train_death_risk.py --root data/demos-2026-11 --table death-risk-v4 \
        --out reports/death-risk-<date>

Folders built before the generation guard (death-risk-v1 to v3) need --allow-legacy;
the report then says the input was not verified.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from dota_items.contracts.death_risk import FEATURES, FEATURES_V1, FEATURES_V2
from dota_items.experiments.awareness.death_risk_tables import load_tables
from dota_items.modeling.awareness.death_risk_eval import (
    ALERT_FALSE_ALARM,
    FOLDS,
    SEED,
    at_false_alarm,
    bootstrap_gap,
    death_alerts,
    measure,
    models,
    out_of_fold,
    rule_score,
    summarize_alerts,
)

SCHEMA = "death-risk-baseline/4"  # 4: checked input, alert measure renamed (not hit in 3 s)
MAIN_HORIZON = 20  # U115's provisional window


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--allow-legacy", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=100)
    args = parser.parse_args(argv)
    risk, _, deaths, info = load_tables(args.root / args.table, args.allow_legacy)
    args.out.mkdir(parents=True, exist_ok=False)
    frame, deaths = pd.DataFrame(risk), pd.DataFrame(deaths)
    del risk
    rng = np.random.default_rng(SEED)
    early = frame["hit_recent"].to_numpy() == 0
    sets = [v for v in (FEATURES, FEATURES_V2, FEATURES_V1) if set(v) <= set(frame.columns)]
    features = list(sets[0])
    older = {
        name: columns
        for name, columns in (("v2", FEATURES_V2), ("v1", FEATURES_V1))
        if columns in sets and len(columns) < len(features)
    }
    report = {
        "schema": SCHEMA,
        "use": "track B baseline on non-holdout matches; holdout untouched (U133)",
        "input": info,
        "matches": int(frame["match_id"].nunique()),
        "hero_games": int(frame[["match_id", "hero"]].drop_duplicates().shape[0]),
        "samples": len(frame),
        "features": features,
        "folds": FOLDS,
        "main_horizon": MAIN_HORIZON,
        "subset_not_hit_last_3s": "samples with hit_recent == 0; not 'before the first hit'",
        "horizons": {},
    }
    kept = {}
    for horizon in (10, 15, 20):
        target = f"dies_{horizon}"
        y = frame[target].to_numpy()
        rule = rule_score(frame)
        entry = {"rule": {"all": measure(y, rule, False),
                          "not_hit_last_3s": measure(y[early], rule[early], False)}}  # fmt: skip
        for name, make in models().items():
            if horizon != MAIN_HORIZON and name != "boosting":
                continue
            scores, fitted = out_of_fold(frame, target, features, make)
            entry[name] = {
                "all": measure(y, scores),
                "not_hit_last_3s": measure(y[early], scores[early]),
            }
            if horizon == MAIN_HORIZON:
                kept[name] = (scores, fitted)
            print(horizon, name, entry[name]["not_hit_last_3s"]["average_precision"], flush=True)
        report["horizons"][str(horizon)] = entry
    target = f"dies_{MAIN_HORIZON}"
    y = frame[target].to_numpy()
    boosting, fitted = kept["boosting"]
    early_frame = frame[early].reset_index(drop=True)
    report["boosting_minus_logistic_not_hit_last_3s"] = bootstrap_gap(
        early_frame, target, boosting[early], kept["logistic"][0][early], args.bootstrap, rng
    )
    report["boosting_minus_rule_not_hit_last_3s"] = bootstrap_gap(
        early_frame, target, boosting[early], rule_score(frame)[early], args.bootstrap, rng
    )
    for name, columns in older.items():
        old, _ = out_of_fold(frame, target, columns, models()["boosting"])
        report[f"boosting_{name}_features_same_rows"] = {
            "all": measure(y, old, False),
            "not_hit_last_3s": measure(y[early], old[early], False),
        }
        report[f"boosting_minus_{name}_not_hit_last_3s"] = bootstrap_gap(
            early_frame, target, boosting[early], old[early], args.bootstrap, rng
        )
    _, threshold = at_false_alarm(y[early], boosting[early], ALERT_FALSE_ALARM)
    report["alerts"] = {
        "threshold": round(threshold, 4),
        "false_alarm_rate_on_samples_not_hit_last_3s": ALERT_FALSE_ALARM,
        "horizon": MAIN_HORIZON,
        **summarize_alerts(death_alerts(frame, deaths, boosting, threshold, MAIN_HORIZON)),
    }
    model, test = fitted[0]
    pick = rng.choice(test, min(len(test), 100_000), replace=False)
    importance = permutation_importance(
        model, frame[features].to_numpy()[pick], y[pick], scoring="average_precision",
        n_repeats=3, random_state=SEED,
    )  # fmt: skip
    report["permutation_importance_fold_1"] = sorted(
        ({"feature": f, "drop_in_average_precision": round(float(v), 4)}
         for f, v in zip(features, importance.importances_mean, strict=True)),
        key=lambda row: -row["drop_in_average_precision"],
    )  # fmt: skip
    np.savez_compressed(
        args.out / "out-of-fold.npz",
        match_id=frame["match_id"].to_numpy(),
        t=frame["t"].to_numpy(),
        hero=frame["hero"].to_numpy().astype(str),
        y=y,
        hit_recent=frame["hit_recent"].to_numpy(),
        boosting=boosting,
        logistic=kept["logistic"][0],
    )
    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out / 'report.json'}")


if __name__ == "__main__":
    main()
