"""Synthetic-only evaluation contracts; no real dataset reads or model fitting."""

import numpy as np
import pytest

from dota_items.modeling import evaluation as current
from dota_items.modeling import purchase_baseline as historical


@pytest.mark.parametrize(
    "bad", [[True], [None], ["1"], [0.5], [2], [-1], [np.nan], [np.inf], [[1]], 1]
)
def test_invalid_labels(bad):
    with pytest.raises(ValueError):
        current.metrics(bad, [0.5])


@pytest.mark.parametrize(
    "bad", [[True], [None], ["0.5"], [-0.1], [1.1], [np.nan], [np.inf], [[0.5]], 0.5]
)
def test_invalid_probabilities(bad):
    with pytest.raises(ValueError):
        current.metrics([1], bad)


@pytest.mark.parametrize("index", range(4))
def test_masked_arrays_cannot_silently_drop_unknown_status(index):
    args = [np.array([0, 1]), np.array([0.2, 0.8]), np.array([0.1, 0.9]), np.array([1, 2])]
    args[index] = np.ma.array(args[index], mask=[False, True])
    with pytest.raises(ValueError):
        current.paired_intervals(*args, repeats=2)


def test_length_mismatch():
    with pytest.raises(ValueError):
        current.metrics([0, 1], [0.5])


@pytest.mark.parametrize(
    "groups", [[None], [True], [np.nan], [1.0], [""], [" "], [1, "1"], [[1]], 1]
)
def test_invalid_groups(groups):
    with pytest.raises(ValueError):
        list(current.group_draws(groups, 3, 0))


@pytest.mark.parametrize(
    "repeats,seed", [(0, 0), (-1, 0), (True, 0), (1.5, 0), (1, -1), (1, True), (1, 0.5), (1, None)]
)
def test_invalid_bootstrap_options_even_when_empty(repeats, seed):
    with pytest.raises(ValueError):
        current.paired_intervals([], [], [], [], repeats=repeats, seed=seed)
    with pytest.raises(ValueError):
        list(current.group_draws([], repeats, seed))


@pytest.mark.parametrize("index", range(4))
def test_paired_lengths_checked_before_sampling(index):
    args = [[0, 1], [0.2, 0.8], [0.3, 0.7], [1, 2]]
    args[index] = args[index][:1]
    with pytest.raises(ValueError, match="equal lengths"):
        current.paired_intervals(*args, repeats=2)


def test_empty_contract():
    assert current.metrics([], []) == {
        "observed": 0,
        "positive": 0,
        "negative": 0,
        "positive_rate": None,
        "average_precision": None,
        "brier": None,
        "roc_auc": None,
    }
    assert list(current.group_draws([], 3, 0)) == []
    assert all(
        v == {"low": None, "high": None, "valid_replicates": 0}
        for v in current.paired_intervals([], [], [], [], repeats=3).values()
    )


@pytest.mark.parametrize("y", [[0, 0, 0, 0], [1, 1, 1, 1], [0, 1, 0, 1]])
def test_historical_numeric_parity(y):
    y = np.asarray(y)
    a = np.asarray([0.2, 0.6, 0.5, 0.8])
    b = np.asarray([0.1, 0.7, 0.4, 0.9])
    groups = np.asarray([1, 1, 2, 2])
    assert current.metrics(y, a) == historical.metrics(y, a)
    assert current.paired_intervals(
        y, a, b, groups, repeats=12, seed=4
    ) == historical.paired_intervals(y, a, b, groups, repeats=12, seed=4)


def test_lists_arrays_and_inputs_unchanged():
    args = [[0, 1, 0, 1], [0.2, 0.6, 0.5, 0.8], [0.1, 0.7, 0.4, 0.9], ["a", "a", "b", "b"]]
    arrays = [np.asarray(a) for a in args]
    copies = [a.copy() for a in arrays]
    assert current.paired_intervals(*args, repeats=10) == current.paired_intervals(
        *arrays, repeats=10
    )
    for actual, before in zip(arrays, copies, strict=True):
        np.testing.assert_array_equal(actual, before)


def test_whole_groups_repeat_all_rows_and_preserve_large_ids():
    groups = [2**100, 2**100, 2**100 + 1]
    draws = list(current.group_draws(groups, 20, 7))
    assert len(draws) == 20
    assert any(len(d) != 3 for d in draws)
    for draw in draws:
        counts = np.bincount(draw, minlength=3)
        assert counts[0] == counts[1]
        assert counts[0] + counts[2] == 2


def test_paired_rejects_unknown_and_nonfinite_before_sampling():
    with pytest.raises(ValueError):
        current.paired_intervals([0, None], [0.2, 0.4], [0.1, 0.7], [1, 2], repeats=1)
    with pytest.raises(ValueError):
        current.paired_intervals([0, 1], [0.2, np.nan], [0.1, 0.7], [1, 2], repeats=1)
