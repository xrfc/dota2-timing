import joblib
import numpy as np
import pytest

from scripts.lane_study_baselines import fit_behavior, fit_outcomes


def _row(i):
    return {
        "static": [i % 3, None],
        "sequence": [[None, 1], [2, 3], [None if i % 3 else i, 2]],
        "action": "farm" if i % 2 else "retreat",
        "hits": i % 5,
        "death": int(i % 4 == 0),
    }


def test_models_round_trip_without_future_fields(tmp_path):
    train = [_row(i) for i in range(60)]
    labels = [_row(7), _row(12)]
    outcomes, trees = fit_outcomes(train, labels, 17)
    behavior, refs = fit_behavior(train, labels, 17)
    # Predict as from the page: future labels unavailable, prior frames unused by both baselines.
    no_labels = [{"static": r["static"], "sequence": [[], [], r["sequence"][-1]]} for r in labels]
    for name, model in (trees | refs).items():
        path = tmp_path / f"{name}.joblib"
        joblib.dump(model, path)
        saved = joblib.load(path)
        if name in trees:
            actual_actions = [
                {**x, "action": y["action"]} for x, y in zip(no_labels, labels, strict=True)
            ]
            np.testing.assert_allclose(saved.predict(actual_actions), outcomes[name])
        else:
            np.testing.assert_allclose(saved.predict(no_labels), behavior[name])
    assert behavior["frequency"].tolist() == [0.5, 0.5]
    assert outcomes["action_mean"][1].tolist() == [0.0, 0.5]


def test_single_class_training_and_missing_support():
    train = [{**_row(3), "death": 1}, {**_row(1), "death": 1}]
    test = [_row(4)]
    predictions, _ = fit_outcomes(train, test, 0)
    assert np.isnan(predictions["action_mean"]).all()
    assert predictions["last_frame_tree"][1].tolist() == [1]
    behavior, models = fit_behavior(train, test, 0)
    assert behavior["logistic"].tolist() == [1]
    assert models["logistic"].predict([]).shape == (0,)
    with pytest.raises(ValueError, match="recognized"):
        fit_behavior([{**_row(0), "action": "unknown"}], [], 0)
