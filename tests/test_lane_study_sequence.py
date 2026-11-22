import copy

import joblib
import numpy as np
import pytest
from scipy.optimize import check_grad

from scripts.lane_study_sequence import SequenceOutcome, _objective


def row(value):
    return dict(
        static=[None, 1.0],
        sequence=[[value, None], [value, 2.0], [0.0, 2.0]],
        action="retreat",
        hits=2 * value,
        death=value,
    )


def test_temporal_gradient_through_shared_filters_and_pooling():
    rng = np.random.default_rng(9)
    static, windows = rng.normal(size=(3, 2)), rng.normal(size=(3, 3, 4))
    targets = (static, windows, np.array([-1, 0, 1]), np.array([1, 0, 1]))
    parameters = rng.normal(0, 0.1, size=4 * 8 + 8 + (8 + 2 + 1) * 2)
    error = check_grad(
        lambda p: _objective(p, *targets)[0],
        lambda p: _objective(p, *targets)[1],
        parameters,
    )
    assert error < 1e-5


def test_temporal_model_uses_earlier_frames_and_serializes(tmp_path):
    rows = [row(0), row(1)] * 8
    train = SequenceOutcome.fit(rows, 17, history=True)
    ablated = SequenceOutcome.fit(rows, 17, history=False)
    assert train.parameters.size == ablated.parameters.size
    hits, death = train.predict(rows[:2])
    assert hits[1] > hits[0] + 1
    assert death[1] > death[0] + 0.5
    for prediction in ablated.predict(rows[:2]):
        assert prediction[0] == prediction[1]
    file = tmp_path / "sequence.joblib"
    joblib.dump(train, file)
    restored = joblib.load(file)
    for actual, expected in zip(restored.predict(rows[:2]), (hits, death), strict=True):
        np.testing.assert_array_equal(actual, expected)
    changed = copy.deepcopy(rows[0])
    changed.update(hits=100, death=1)
    for prediction in train.predict([rows[0], changed]):
        assert prediction[0] == prediction[1]


def test_sparse_fold_and_invalid_frames():
    fitted = SequenceOutcome.fit([row(1)], seed=0, history=True)
    unseen = row(0)
    unseen["static"] = [10_000, None]
    hits, death = fitted.predict([unseen])
    assert hits.tolist() == [2.0]
    assert death.tolist() == [1.0]
    unseen["sequence"].pop()
    with pytest.raises(ValueError, match="three"):
        fitted.predict([unseen])
