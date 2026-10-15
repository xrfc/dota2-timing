import copy

import pytest

from dota_items.modeling.purchase_sensitivity import compare


def fixture():
    return {
        "task": {"candidate_items": ["manta", "bkb"]},
        "samples": [
            {
                "match_id": f"{split}-{i}",
                "split": split,
                "encoded_features": [i % 2, i / 10],
                "labels": [i % 2, 0],
                "label_mask": [True, True],
            }
            for split in ["train", "validation"]
            for i in range(10)
        ],
    }


def test_test_payload_is_never_read():
    clean = fixture()
    poisoned = copy.deepcopy(clean)
    poisoned["samples"].append({"split": "test", "labels": object()})
    assert compare(clean) == compare(poisoned)


def test_frequency_can_win_and_unknown_labels_are_excluded():
    data = fixture()
    for r in data["samples"]:
        r["encoded_features"] = [0, 0]
    unknown = copy.deepcopy(data["samples"][0])
    unknown.update(labels=[None, None], label_mask=[False, False])
    expected = compare(data)
    data["samples"].append(unknown)
    assert compare(data) == expected
    result = expected["items"]["manta"]
    assert result["selected_index"] == 0
    assert len(result["trials"]) == 9
    assert expected["excluded_train_single_class_items"] == ["bkb"]


def test_validation_does_not_change_fitted_parameters():
    data = fixture()
    before = compare(data)["items"]["manta"]["trials"]
    for r in data["samples"]:
        if r["split"] == "validation":
            r["labels"][0] = 1 - r["labels"][0]
    after = compare(data)["items"]["manta"]["trials"]
    for a, b in zip(before, after, strict=True):
        for key in ["coefficients", "intercept", "validation_predictions"]:
            assert a[key] == b[key]


def test_missing_validation_fails():
    data = fixture()
    data["samples"] = [r for r in data["samples"] if r["split"] == "train"]
    with pytest.raises(ValueError, match="Validation"):
        compare(data)
