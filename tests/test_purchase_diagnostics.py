import copy

import pytest
from test_purchase_baseline import snapshot

from dota_items.modeling.purchase_baseline import run_experiment
from dota_items.modeling.purchase_diagnostics import calibration, diagnose


def inputs():
    data = snapshot()
    data["preprocessing"] = {"columns": ["a", "b"]}
    return data, run_experiment(data, repeats=1)


def test_test_data_is_not_used():
    data, experiment = inputs()
    expected = diagnose(data, experiment)
    changed = copy.deepcopy(data)
    for row in changed["samples"]:
        if row["split"] == "test":
            row["encoded_features"] = None
            row["labels"] = None
    experiment["predictions"]["manta"] = experiment["predictions"]["manta"][:16]
    assert diagnose(changed, experiment) == expected


def test_predictions_join_by_id_and_reject_missing_duplicate_or_corrupt():
    data, experiment = inputs()
    expected = diagnose(data, experiment)
    experiment["predictions"]["manta"].reverse()
    assert diagnose(data, experiment) == expected
    for mutation in ("missing", "duplicate", "probability"):
        changed = copy.deepcopy(experiment)
        rows = changed["predictions"]["manta"]
        if mutation == "missing":
            rows.pop()
        elif mutation == "duplicate":
            rows.append(rows[-1])
        else:
            rows[-1]["linear"] = 0.999
        with pytest.raises(ValueError):
            diagnose(data, changed)


def test_unknown_labels_excluded_and_empty_bins_retained():
    data, _ = inputs()
    data["samples"][8]["label_mask"][0] = False
    data["samples"][8]["labels"][0] = None
    result = diagnose(data, run_experiment(data, repeats=1))["items"]["manta"]
    assert result["support"]["validation"]["unknown"] == 1
    assert result["validation"]["linear"]["observed"] == 7
    assert sum(b["count"] for b in result["validation"]["calibration"]) == 7
    bins = calibration([0, 1], [0, 1])
    assert bins[0]["count"] == bins[9]["count"] == 1
    assert bins[1]["positive_rate"] is None


def test_group_support_partition_and_error_conservation():
    data, experiment = inputs()
    result = diagnose(data, experiment)["items"]["manta"]
    support = result["support"]
    assert support["train_largest_group"]["rows"] + support["train_other_groups"]["rows"] == 8
    val = result["validation"]
    assert sum(r["brier_delta"] for r in val["largest_harms"]) / 8 == pytest.approx(
        val["linear"]["brier"] - val["frequency"]["brier"]
    )
