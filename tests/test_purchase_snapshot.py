import copy

import pytest

from dota_items.data.purchase_snapshot import class_support, grouped_split, verify_snapshot
from dota_items.storage import json_bytes


def test_groups_indivisible_deterministic_and_order_invariant():
    groups = [list(range(1, 520))] + [[i] for i in range(520, 953)]
    splits = grouped_split(groups)
    assert splits == grouped_split([list(reversed(g)) for g in reversed(groups)])
    assert {k: len(v) for k, v in splits.items()} == {"train": 571, "validation": 191, "test": 190}
    assert set(range(1, 520)) <= set(splits["train"])
    assert sorted(mid for ids in splits.values() for mid in ids) == list(range(1, 953))


@pytest.mark.parametrize("groups", [[[1], [1], [2]], [[1], [2]], [[1], [], [2]]])
def test_invalid_groups_rejected(groups):
    with pytest.raises(ValueError):
        grouped_split(groups)


def test_unknowns_and_single_class_support():
    samples = [
        {"split": "train", "labels": [1, 0], "label_mask": [True, True]},
        {"split": "train", "labels": [0, None], "label_mask": [True, False]},
        {"split": "test", "labels": [1, 1], "label_mask": [True, True]},
    ]
    support = class_support(samples, ["manta", "bkb"])
    assert support["train"]["manta"]["both_classes_present"]
    assert not support["train"]["bkb"]["both_classes_present"]
    assert support["train"]["bkb"]["unknown"] == 1
    assert support["validation"]["manta"]["positive"] == 0


@pytest.mark.parametrize(
    "field,value", [("labels", [0]), ("split", "test"), ("encoded_features", [99])]
)
def test_reconstruction_rejects_tampering(tmp_path, monkeypatch, field, value):
    expected = {"samples": [{"labels": [1], "split": "train", "encoded_features": [1]}]}
    modified = copy.deepcopy(expected)
    modified["samples"][0][field] = value
    path = tmp_path / "snapshot.json"
    path.write_bytes(json_bytes(modified))
    monkeypatch.setattr("dota_items.data.purchase_snapshot.build_snapshot", lambda _: expected)
    with pytest.raises(ValueError, match="reconstruction"):
        verify_snapshot(path, tmp_path / "summary.json")
