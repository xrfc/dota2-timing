"""Paired lineup diagnostics, not causal estimates or recommendation validation."""

import math

from .lineup_analysis import ITEM_NAMES, analyze


def compare(a, b, model, baseline, samples):
    train = [row for row in samples if row["split"] == "train"]
    left = analyze(a, model, baseline, train)
    right = analyze(b, model, baseline, train)
    changed = []
    groups = []
    for side in ("ally", "enemy"):
        key = side + "_hero_ids"
        removed = sorted(set(a[key]) - set(b[key]))
        added = sorted(set(b[key]) - set(a[key]))
        for direction, heroes in [("removed", removed), ("added", added)]:
            for hero in heroes:
                group = [row for row in train if hero in row["features"][key]]
                support = {}
                for index, item in enumerate(ITEM_NAMES):
                    observed = [row for row in group if row["label_mask"][index]]
                    support[item] = dict(
                        observed=len(observed),
                        positive=sum(row["labels"][index] for row in observed),
                        unknown=len(group) - len(observed),
                    )
                changed.append(dict(side=side, direction=direction, hero_id=hero))
                groups.append(
                    dict(
                        side=side,
                        direction=direction,
                        hero_id=hero,
                        matches=len(group),
                        items=support,
                    )
                )
    right_items = {r["item"]: r for r in right["items"]}
    rows = []
    for row in left["items"]:
        other = right_items[row["item"]]
        ta = {t["feature"]: t["contribution"] for t in row["contributions"]}
        tb = {t["feature"]: t["contribution"] for t in other["contributions"]}
        terms = [
            dict(feature=f, a=ta.get(f, 0), b=tb.get(f, 0), difference=tb.get(f, 0) - ta.get(f, 0))
            for f in sorted(ta.keys() | tb.keys())
            if ta.get(f, 0) != tb.get(f, 0)
        ]
        delta_logit = other["logit"] - row["logit"]
        if not math.isclose(math.fsum(t["difference"] for t in terms), delta_logit, abs_tol=1e-12):
            raise ValueError("Paired explanation failed reconstruction")
        if row["baseline"] != other["baseline"]:
            raise ValueError("Frequency baseline changed with lineup")
        rows.append(
            dict(
                item=row["item"],
                name=row["name"],
                a=row["probability"],
                b=other["probability"],
                delta_pp=100 * (other["probability"] - row["probability"]),
                baseline=row["baseline"],
                delta_logit=delta_logit,
                contribution_changes=terms,
            )
        )
    exact = {}
    for label, lineup in [("a", a), ("b", b)]:
        exact[label] = sum(
            all(
                set(row["features"][key]) == set(lineup[key])
                for key in ("ally_hero_ids", "enemy_hero_ids")
            )
            for row in train
        )
    return dict(
        a=left,
        b=right,
        changes=changed,
        hero_support=groups,
        exact_lineup_support=exact,
        items=sorted(rows, key=lambda r: -abs(r["delta_pp"])),
        causal_effect=False,
        independent_evaluation=False,
        limitation="英雄边际支持数不是当前阵容支持数；两组可重叠，不能据其购买率作因果解释。",
    )
