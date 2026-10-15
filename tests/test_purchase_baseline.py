import copy

import numpy as np
import pytest

from dota_items.modeling.purchase_baseline import (
    group_draws,
    metrics,
    paired_intervals,
    run_experiment,
)


def snapshot():
    rows = []
    for split in ("train", "validation", "test"):
        for i in range(8):
            rows.append(
                {
                    "match_id": len(rows),
                    "split": split,
                    "group_id": f"{split}-{i // 2}",
                    "encoded_features": [i % 2, i / 8],
                    "labels": [i % 2, 0],
                    "label_mask": [True, True],
                    "role_hint": "estimated_carry",
                }
            )
    return {
        "samples": rows,
        "task": {"candidate_items": ["manta", "bkb"]},
        "train_model_items": ["manta"],
        "constant_train_items": ["bkb"],
        "limitations": [],
    }


def test_metrics_undefined_and_frequency_ap():
    assert metrics([], [])["brier"] is None
    assert metrics([0, 0], [0.1, 0.1])["average_precision"] is None
    assert metrics([1, 1], [0.1, 0.1])["roc_auc"] is None
    assert metrics([0, 1, 0, 0], [0.25] * 4)["average_precision"] == 0.25


def test_group_bootstrap_preserves_whole_groups():
    for draw in group_draws(["a", "a", "b"], 20, 5):
        assert sum(draw == 0) == sum(draw == 1)
    assert any(len(d) != 3 for d in group_draws(["a", "a", "b"], 20, 5))


def test_paired_identical_predictions_zero_interval():
    result = paired_intervals(
        np.array([0, 1]),
        np.array([0.3, 0.7]),
        np.array([0.3, 0.7]),
        np.array(["a", "b"]),
        repeats=20,
    )
    assert result["brier"]["low"] == result["brier"]["high"] == 0
    assert result["roc_auc"]["valid_replicates"] < 20


def test_test_labels_and_features_cannot_change_selection():
    original = snapshot()
    changed = copy.deepcopy(original)
    for row in changed["samples"]:
        if row["split"] == "test":
            row["labels"][0] = 1 - row["labels"][0]
            row["encoded_features"] = [100, -100]
    first = run_experiment(original, repeats=3)
    second = run_experiment(changed, repeats=3)
    assert first["selected_models"] == second["selected_models"]
    assert (
        first["evaluations"]["manta"]["validation"] == second["evaluations"]["manta"]["validation"]
    )
    assert first["excluded_items"] == ["bkb"]
    assert first["modeled_items"] == ["manta"]


def test_mask_excludes_unknown_labels():
    data = snapshot()
    data["samples"][0]["label_mask"][0] = False
    data["samples"][0]["labels"][0] = None
    data["samples"][-1]["label_mask"][0] = False
    data["samples"][-1]["labels"][0] = None
    result = run_experiment(data, repeats=3)
    assert result["selected_models"]["manta"]["frequency"] == 4 / 7
    evaluation = result["evaluations"]["manta"]["test"]["all"]
    assert evaluation["unknown"] == 1
    assert evaluation["linear"]["observed"] == 7


def test_reproducible_and_rejects_invalid_protocol():
    assert run_experiment(snapshot(), repeats=3) == run_experiment(snapshot(), repeats=3)
    with pytest.raises(ValueError):
        run_experiment(snapshot(), repeats=0)
    data = snapshot()
    data["train_model_items"] = ["bkb"]
    with pytest.raises(ValueError, match="eligibility"):
        run_experiment(data, repeats=3)
