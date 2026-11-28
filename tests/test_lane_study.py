import json

import numpy as np
import pytest

from dota_items.data.awareness_split import is_holdout
from scripts.lane_study import load_rows, paired, summarize


def test_rows_keep_matches_together_and_exclude_holdout(tmp_path):
    rows_path = tmp_path / "rows.jsonl"

    def read(*cases):
        rows_path.write_text("\n".join(json.dumps(c) for c in cases))
        return load_rows(rows_path)

    dev = next(i for i in range(1, 100) if not is_holdout(i))
    holdout = next(i for i in range(1, 100) if is_holdout(i))
    a = dict(match=dev, hero="antimage", t=900, fold=2)
    b = {**a, "hero": "sven"}
    assert read(a, b) == [a, b]
    for invalid in (a, {**b, "fold": 3}, {**b, "fold": 5}, {**b, "match": holdout}):
        with pytest.raises(ValueError):
            read(a, invalid)


def _case(match, t, hits_pred, death_prob):
    return dict(
        match=match,
        hero="sven",
        t=t,
        hits=1,
        hits_pred=hits_pred,
        death=0,
        p_death=death_prob,
        action="farm",
        fold=match % 5,
    )


def test_outcome_metrics_include_zero_alert_matches_and_single_class_ap():
    rows = [_case(1, 900, 2, 1), _case(1, 920, 0, 0.5), _case(2, 900, 1, 0)]
    result = summarize(rows, False)
    assert result["death_ap"] is None
    assert result["hits_mae"] == pytest.approx(2 / 3)
    assert result["death_brier"] == pytest.approx(1.25 / 3)
    assert result["false_alerts_per_represented_match"] == 1
    assert [b["count"] for b in result["calibration"]] == [1, 1, 1]
    assert result["calibration"][-1]["predicted"] == 1
    assert summarize([], False)["matches"] == 0


def test_behavior_recall_conditions_on_observed_action():
    rows = [
        {"match": 1, "action": "farm", "p_farm": 0.5},
        {"match": 1, "action": "farm", "p_farm": 0.25},
        {"match": 1, "action": "retreat", "p_farm": 0.25},
    ]
    result = summarize(rows, True)
    assert result["farm_recall"] == 0.5
    assert result["retreat_recall"] == 1
    assert result["log_loss"] == pytest.approx(-np.log([0.5, 0.25, 0.75]).mean())
    assert summarize(rows[:2], True)["retreat_recall"] is None


def test_paired_intervals_resample_whole_matches_and_match_by_key():
    # First model is worse by 2 hits for one game and exact for the other game's three rows.
    base = [_case(8, 10, 1, 0.0)] + [_case(7, t, 1, 0.0) for t in (10, 20, 30)]
    model = [{**base[0], "hits_pred": 3, "p_death": 1.0}, *base[1:]]
    result = paired(model, base[::-1])
    assert result["hits_mae"] == {"difference": 1.0, "ci95": [0.0, 2.0]}
    assert result["death_brier"] == {"difference": 0.5, "ci95": [0.0, 1.0]}
    assert paired(model[::-1], base) == result
    with pytest.raises(ValueError):
        paired(model[:1], base)
