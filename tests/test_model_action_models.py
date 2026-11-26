"""M1 numerical parity and rejection tests; synthetic states only, no fitting."""

import ast
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from dota_items.contracts.action_outcomes import DecisionInput, DecisionKey
from dota_items.modeling.awareness import action_models
from dota_items.modeling.awareness.action_features import FeatureScale, encode_decision
from dota_items.modeling.awareness.action_models import (
    ActionMeans,
    BehaviorReference,
    SequenceOutcome,
    TreeOutcome,
    predict_behavior,
    predict_outcomes,
)

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests/action_legacy_models_runner.py"
FIXTURES = ROOT / "tests/fixtures/action_legacy"


@pytest.fixture(scope="module")
def oracle():
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1",
    }
    outputs = {}
    for mode in ("legacy", "new"):
        process = subprocess.run(
            [sys.executable, str(RUNNER), mode, "--snapshots", str(FIXTURES)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
        )
        outputs[mode] = json.loads(process.stdout)
    return outputs


@pytest.fixture(scope="module")
def synthetic():
    # Import test-only constructors, not either implementation's numerical functions.
    spec = importlib.util.spec_from_file_location("action_synthetic_states", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("width", ["2", "7"])
@pytest.mark.parametrize(
    "name",
    [
        "action_mean",
        "last_frame_tree",
        "three_frame_tree",
        "frequency",
        "logistic",
        "last_frame_nn",
        "temporal_nn",
        "constant_tree",
        "constant_sequence",
        "single_action_mean",
    ],
)
def test_independent_frozen_predictions_match_exactly(oracle, width, name):
    old = oracle["legacy"][width][name]
    new = oracle["new"][width][name]
    assert old.keys() == new.keys()
    for case, expected in old.items():
        actual = new[case]
        if "error" in expected:
            assert actual == expected
        else:
            np.testing.assert_array_equal(actual["values"], expected["values"])
    np.testing.assert_array_equal(new["normal"]["values"], new["future_changed"]["values"])


def test_independent_scale_clipping_and_nonfinite_missing_values_match_exactly(oracle):
    for dtype in ("float32", "float64"):
        for shape in ("matrix", "frames"):
            np.testing.assert_array_equal(
                oracle["new"]["scales"][dtype][shape],
                oracle["legacy"]["scales"][dtype][shape],
            )


def test_temporal_and_last_frame_arms_keep_different_history_semantics(synthetic):
    models = synthetic.synthetic_models(action_models)
    first, second = copy.deepcopy(synthetic.synthetic_rows()[:2])
    second["static"], second["sequence"][-1], second["action"] = (
        first["static"],
        first["sequence"][-1],
        first["action"],
    )
    for values in models["last_frame_nn"].predict([first, second]):
        assert values[0] == values[1]
    assert any(values[0] != values[1] for values in models["temporal_nn"].predict([first, second]))


def _decision(row, *, domain="wave", match=1):
    return DecisionInput(DecisionKey(match, "hero", 20, domain), row["static"], row["sequence"])


def test_public_prediction_uses_only_explicit_candidates_and_decisions(synthetic):
    models = synthetic.synthetic_models(action_models, width=7)
    rows = synthetic.synthetic_rows(width=7)
    decisions = [_decision(row) for row in rows]
    actions = [row["action"] for row in rows]
    for state in models.values():
        if isinstance(state, BehaviorReference):
            actual = predict_behavior(state, decisions)
        else:
            actual = predict_outcomes(state, decisions, actions)
        np.testing.assert_array_equal(actual, state.predict(rows))
    alternate_identity = [_decision(row, match=9) for row in rows]
    np.testing.assert_array_equal(encode_decision(decisions), encode_decision(alternate_identity))
    assert set(decisions[0].to_features()) == {"static", "sequence"}
    assert not hasattr(decisions[0], "action")
    assert not hasattr(decisions[0], "gold")


@pytest.mark.parametrize("kind", ["outcomes", "behavior"])
def test_public_prediction_rejects_wrong_domain_dimensions_and_types(kind):
    state = ActionMeans({"farm": (1.0, 0.1)}) if kind == "outcomes" else BehaviorReference(0.5)

    def predict(rows):
        return (
            predict_outcomes(state, rows, ["farm"] * len(rows))
            if kind == "outcomes"
            else predict_behavior(state, rows)
        )

    bad = [
        {"static": [0.0] * 7, "sequence": [[0.0] * 7] * 3},
        DecisionInput(DecisionKey(1, "hero", 20, "wave"), (0.0,), ((0.0,),) * 3),
        DecisionInput(DecisionKey(1, "hero", 20, "jungle"), (0.0,) * 10, ((0.0,) * 7,) * 3),
    ]
    for value in bad:
        with pytest.raises(ValueError):
            predict([value])


def test_public_reference_family_and_action_count_are_checked():
    state = ActionMeans({"farm": (1.0, 0.1)})
    decision = DecisionInput(DecisionKey(1, "hero", 20, "wave"), (0.0,) * 7, ((0.0,) * 7,) * 3)
    with pytest.raises(ValueError, match="count"):
        predict_outcomes(state, [decision], [])
    with pytest.raises(ValueError, match="count"):
        predict_outcomes(state, [], ["farm"])
    with pytest.raises(ValueError, match="outcome state"):
        predict_outcomes(BehaviorReference(0.5), [], [])
    with pytest.raises(ValueError, match="behavior reference"):
        predict_behavior(state, [])
    assert np.isnan(predict_outcomes(state, [decision], ["unknown"])).all()


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_feature_scale_roundtrip_preserves_dtype_shape_and_missing_semantics(dtype):
    scale = FeatureScale(np.array([2.0, 0.0], dtype=dtype), np.array([2.0, 1.0], dtype=dtype))
    state = scale.to_state()
    restored = FeatureScale.from_state(state)
    assert restored.median.dtype == restored.scale.dtype == np.dtype(dtype)
    assert restored.median.shape == restored.scale.shape == (2,)
    values = np.array([[np.inf, np.nan], [-np.inf, 1000], [4.0, -1000.0]])
    np.testing.assert_array_equal(
        restored.transform(values), [[0, 0, 1, 1], [0, 10, 1, 0], [1, -10, 0, 0]]
    )
    state["median"][0] = 99
    assert restored.median[0] == scale.median[0] == 2


def test_feature_scale_rejects_implicit_width_broadcasting():
    scale = FeatureScale(np.zeros(2), np.ones(2))
    with pytest.raises(ValueError, match="width"):
        scale.transform(np.ones((3, 1)))
    with pytest.raises(ValueError, match="width"):
        scale.transform(np.array(1.0))


@pytest.mark.parametrize("damage", ["steps", "names", "width"])
def test_behavior_pipeline_rejects_unregistered_layout_and_inconsistent_widths(synthetic, damage):
    pipeline = synthetic.behavior_pipeline(4)
    if damage == "steps":
        pipeline.steps = pipeline.steps[1:]
    elif damage == "names":
        pipeline.steps[0] = ("custom", pipeline.steps[0][1])
    else:
        pipeline.steps[-1][1].n_features_in_ += 1
    with pytest.raises(ValueError, match="pipeline"):
        BehaviorReference.from_state({"farm_frequency": 0.4, "pipeline": pipeline})


def test_sequence_state_roundtrip_is_explicit_and_detached(synthetic):
    model = synthetic.synthetic_models(action_models)["temporal_nn"]
    state = model.to_state()
    assert type(state["static_scale"]) is dict
    assert type(state["sequence_scale"]) is dict
    restored = SequenceOutcome.from_state(state)
    rows = synthetic.synthetic_rows()
    np.testing.assert_array_equal(model.predict(rows), restored.predict(rows))
    assert restored.parameters.dtype == state["parameters"].dtype
    state["parameters"][0] = 999
    state["static_scale"]["median"][0] = 999
    np.testing.assert_array_equal(model.predict(rows), restored.predict(rows))


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"median": np.zeros(2), "scale": np.ones(3)},
        {"median": np.zeros(2), "scale": np.array([1.0, 0.0])},
        {"median": np.array([np.nan]), "scale": np.ones(1)},
        {"median": np.array([[0.0]]), "scale": np.ones(1)},
        {"median": np.array([0]), "scale": np.ones(1)},
        {"median": np.zeros(1), "scale": np.ones(1), "extra": 1},
    ],
)
def test_malformed_scale_states_are_rejected(state):
    with pytest.raises(ValueError):
        FeatureScale.from_state(state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("history", 1),
        ("parameters", np.zeros(1)),
        ("parameters", np.array([np.nan])),
        ("hits_std", -1),
        ("constant_death", 2),
        ("hits_mean", np.inf),
        ("extra", 1),
    ],
)
def test_malformed_sequence_states_are_rejected(synthetic, field, value):
    state = synthetic.synthetic_models(action_models)["temporal_nn"].to_state()
    state[field] = value
    with pytest.raises(ValueError):
        SequenceOutcome.from_state(state)


@pytest.mark.parametrize(
    "factory,state",
    [
        (ActionMeans, {"means": {"unknown": (1.0, 0.0)}}),
        (ActionMeans, {"means": {"farm": (1.0,)}}),
        (ActionMeans, {"means": {"farm": (1.0, 2.0)}}),
        (BehaviorReference, {"farm_frequency": 2.0, "pipeline": None}),
        (BehaviorReference, {"farm_frequency": 0.5}),
        (BehaviorReference, {"farm_frequency": 0.5, "pipeline": object()}),
    ],
)
def test_malformed_baseline_states_are_rejected(factory, state):
    with pytest.raises(ValueError):
        factory.from_state(state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("columns", np.ones(5)),
        ("columns", np.zeros(5, dtype=bool)),
        ("history", 1),
        ("death_rate", -1.0),
        ("hits", object()),
        ("extra", True),
    ],
)
def test_malformed_tree_states_are_rejected(synthetic, field, value):
    state = synthetic.synthetic_models(action_models)["last_frame_tree"].to_state()
    state[field] = value
    with pytest.raises(ValueError):
        TreeOutcome.from_state(state)


def test_prediction_imports_do_not_load_training_or_backend_optimization():
    script = """
import importlib.abc
import sys
blocked = ('scipy.optimize', 'sklearn', 'scripts', 'dota_items.data', 'dota_items.sources',
           'dota_items.modeling.awareness.action_training', 'dota_items.experiments')
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p + '.') for p in blocked):
            raise AssertionError('unexpected inference import: ' + fullname)
sys.meta_path.insert(0, Reject())
import numpy as np
from dota_items.modeling.awareness.action_features import FeatureScale
from dota_items.modeling.awareness.action_models import SequenceOutcome
scale = FeatureScale(np.zeros(2), np.ones(2))
state = SequenceOutcome(True, scale, scale, np.zeros(100), 2.0, 0.0, 1.0)
row = {'static': [None, 1.0], 'sequence': [[0.0, None]] * 3, 'action': 'farm'}
hits, deaths = state.predict([row])
assert hits.tolist() == [2.0] and deaths.tolist() == [1.0]
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in blocked)
"""
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True)


def test_model_files_have_no_fit_io_or_old_script_dependencies():
    for filename in ("action_features.py", "action_models.py"):
        tree = ast.parse((ROOT / "src/dota_items/modeling/awareness" / filename).read_text())
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "fit"
            for node in ast.walk(tree)
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", "")
                )
                assert name not in {
                    "fit",
                    "fit_transform",
                    "minimize",
                    "open",
                    "read_bytes",
                    "read_text",
                    "write_bytes",
                    "write_text",
                }
