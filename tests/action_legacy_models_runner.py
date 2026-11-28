"""Independent-process oracle driver using only hand-authored synthetic fitted states.

The legacy side imports complete hash-checked source snapshots, never new model
functions. Backend attributes below are test fixtures, not a cross-version loader.
There are no data/model artifact reads or fit calls, including fixture preparation.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import scipy.optimize
from sklearn._loss.loss import HalfBinomialLoss, HalfSquaredError
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.ensemble._hist_gradient_boosting.binning import _BinMapper
from sklearn.ensemble._hist_gradient_boosting.common import PREDICTOR_RECORD_DTYPE
from sklearn.ensemble._hist_gradient_boosting.predictor import TreePredictor
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SNAPSHOTS = {
    "baselines": "aef8c05c6c23ed4262d335808c34c15f6b61f5598a9b9976525b5fb71a976941",
    "sequence": "a36a94838a96f6a9686773d45cfd9b30c542d041718bf6d04642baae0cbdfde0",
}


def forbid_fit(*args, **kwargs):
    raise AssertionError("M1 parity must never fit or optimize, including fixture preparation")


def guard_fitting():
    for cls in (
        HistGradientBoostingClassifier,
        HistGradientBoostingRegressor,
        SimpleImputer,
        MissingIndicator,
        StandardScaler,
        LogisticRegression,
        Pipeline,
    ):
        cls.fit = forbid_fit
    scipy.optimize.minimize = forbid_fit


def load_legacy(folder):
    modules = {}
    for name, expected in SNAPSHOTS.items():
        path = folder / f"{name}.py.txt"
        contents = path.read_bytes()
        if hashlib.sha256(contents).hexdigest() != expected:
            raise ValueError("legacy model source snapshot hash mismatch")
        # Execute the complete original bytes, under a process-local test name.
        spec = importlib.util.spec_from_loader(f"frozen_test_{name}", loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        exec(compile(contents, str(path), "exec"), module.__dict__)
        modules[name] = module
    return SimpleNamespace(
        **{
            name: getattr(
                modules["sequence" if name in ("FeatureScale", "SequenceOutcome") else "baselines"],
                name,
            )
            for name in (
                "ActionMeans",
                "TreeOutcome",
                "BehaviorReference",
                "FeatureScale",
                "SequenceOutcome",
            )
        }
    )


def tree_backend(width, classifier=False, feature=0):
    """A real sklearn backend with one fixed split and two fixed leaves; no fit."""
    estimator = HistGradientBoostingClassifier() if classifier else HistGradientBoostingRegressor()
    estimator.n_features_in_ = width
    estimator.n_trees_per_iteration_ = 1
    estimator._preprocessor = None
    estimator._baseline_prediction = np.array([[-0.2 if classifier else 0.5]])
    estimator._loss = HalfBinomialLoss() if classifier else HalfSquaredError()
    if classifier:
        estimator.classes_ = np.array([0, 1])
    mapper = _BinMapper()
    mapper.is_categorical_ = np.zeros(width, dtype=np.uint8)
    mapper.bin_thresholds_ = [np.array([0.0]) for _ in range(width)]
    estimator._bin_mapper = mapper
    nodes = np.zeros(3, dtype=PREDICTOR_RECORD_DTYPE)
    nodes[0]["feature_idx"] = feature
    nodes[0]["num_threshold"] = 0.0
    nodes[0]["left"] = 1
    nodes[0]["right"] = 2
    nodes[0]["missing_go_to_left"] = 1
    nodes[1]["is_leaf"] = nodes[2]["is_leaf"] = 1
    nodes[1]["value"] = -2.0
    nodes[2]["value"] = 0.7 if classifier else 3.0
    bitsets = np.zeros((0, 8), dtype=np.uint32)
    estimator._predictors = [[TreePredictor(nodes, bitsets, bitsets.copy())]]
    return estimator


def behavior_pipeline(width):
    """The same backend family as the old producer, with explicit learned attributes."""
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    imputer.n_features_in_ = width
    imputer.statistics_ = np.linspace(-0.5, 0.5, width)
    imputer._fit_dtype = imputer._fill_dtype = np.dtype("float64")
    indicator = MissingIndicator(error_on_new=False)
    indicator.features_ = np.array([1, width - 2], dtype=np.int64)
    indicator._precomputed = True
    indicator._n_features = width
    indicator.n_features_in_ = width
    imputer.indicator_ = indicator
    output_width = width + len(indicator.features_)
    scaler = StandardScaler()
    scaler.n_features_in_ = output_width
    scaler.n_samples_seen_ = 12
    scaler.mean_ = np.linspace(-0.1, 0.2, output_width)
    scaler.scale_ = np.linspace(1.0, 2.0, output_width)
    scaler.var_ = scaler.scale_**2
    classifier = LogisticRegression()
    classifier.classes_ = np.array([0, 1])
    classifier.n_features_in_ = output_width
    classifier.n_iter_ = np.array([1])
    classifier.coef_ = np.linspace(-0.2, 0.3, output_width)[None, :]
    classifier.intercept_ = np.array([0.1])
    return Pipeline(
        [
            ("simpleimputer", imputer),
            ("standardscaler", scaler),
            ("logisticregression", classifier),
        ]
    )


def synthetic_rows(width=2):
    rows = []
    for i in range(4):
        static = [float(i - 2), None] + [0.5] * (width - 2)
        frames = [
            [float(i), None] + [1.0] * (width - 2),
            [2.0, float(i - 1)] + [0.0] * (width - 2),
            [None if i % 2 else 3.0, -1.0] + [2.0] * (width - 2),
        ]
        rows.append(
            {"static": static, "sequence": frames, "action": "farm" if i % 2 else "retreat"}
        )
    return rows


def synthetic_models(module, width=2):
    def tree(history, constant=False):
        columns = np.ones(width * (4 if history else 2) + 1, dtype=bool)
        columns[1] = False
        selected = int(columns.sum())
        feature = 2 if history else 0
        return module.TreeOutcome(
            columns,
            tree_backend(selected, feature=feature),
            None if constant else tree_backend(selected, classifier=True, feature=feature),
            0.25,
            history,
        )

    def sequence(history, constant=None):
        size = width * 4 * 8 + 8 + (8 + width * 2 + 1 + 1) * 2
        return module.SequenceOutcome(
            history,
            module.FeatureScale(np.zeros(width), np.ones(width)),
            module.FeatureScale(np.linspace(-0.2, 0.2, width), np.linspace(1.0, 2.0, width)),
            np.linspace(-0.2, 0.2, size),
            2.0,
            1.5,
            constant,
        )

    return {
        "action_mean": module.ActionMeans({"farm": np.array([2.0, 0.25]), "retreat": (0.0, 0.1)}),
        "last_frame_tree": tree(False),
        "three_frame_tree": tree(True),
        "frequency": module.BehaviorReference(0.4),
        "logistic": module.BehaviorReference(0.4, behavior_pipeline(width * 2)),
        "last_frame_nn": sequence(False),
        "temporal_nn": sequence(True),
        "constant_tree": tree(False, constant=True),
        "constant_sequence": sequence(True, constant=1.0),
        "single_action_mean": module.ActionMeans({"farm": (1.0, 0.0)}),
    }


def run_case(model, rows):
    try:
        result = model.predict(rows)
    except (ValueError, IndexError, KeyError, TypeError) as error:
        return {"error": type(error).__name__, "message": str(error)}
    values = [x.tolist() for x in result] if isinstance(result, tuple) else result.tolist()
    return {"values": values}


def collect(module):
    result = {}
    result["scales"] = {}
    for dtype in (np.float32, np.float64):
        scale = module.FeatureScale(
            np.array([2.0, 0.0], dtype=dtype), np.array([2.0, 1.0], dtype=dtype)
        )
        values = np.array([[np.inf, np.nan], [-np.inf, 1000.0], [4.0, -1000.0]])
        result["scales"][np.dtype(dtype).name] = {
            "matrix": scale.transform(values).tolist(),
            "frames": scale.transform(values[None, :, :]).tolist(),
        }
    for width in (2, 7):
        models = synthetic_models(module, width)
        rows = synthetic_rows(width)
        cases = {
            "normal": rows,
            "empty": [],
            "unknown": [{**row, "action": "unknown"} for row in rows],
            "past_empty": [{**row, "sequence": [[], [], row["sequence"][-1]]} for row in rows],
            "future_changed": [
                {**row, "hits": 99, "death": 1, "gold": 9999, "fold": -1} for row in rows
            ],
            "all_missing": [
                {**row, "static": [None] * width, "sequence": [[None] * width] * 3} for row in rows
            ],
        }
        result[str(width)] = {
            name: {case: run_case(model, data) for case, data in cases.items()}
            for name, model in models.items()
        }
        if hasattr(module.ActionMeans, "from_state"):
            for model in models.values():
                restored = type(model).from_state(model.to_state())
                for left, right in zip(
                    np.atleast_2d(model.predict(rows)),
                    np.atleast_2d(restored.predict(rows)),
                    strict=True,
                ):
                    np.testing.assert_array_equal(left, right)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("legacy", "new"))
    parser.add_argument("--snapshots", type=Path, required=True)
    args = parser.parse_args()
    guard_fitting()
    if args.mode == "legacy":
        module = load_legacy(args.snapshots)
    else:
        from dota_items.modeling.awareness import action_models as module
    print(json.dumps(collect(module)))


if __name__ == "__main__":
    main()
