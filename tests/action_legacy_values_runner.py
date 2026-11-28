"""Independent synthetic oracle: verbatim pure functions from SHA-bound old sources.

The full source snapshots are retained. Only the named AST source segments are executed;
CLI, data-reading, deserialization and fit imports/functions are never executed. No new
project implementation is imported. Input and output are JSON on stdin/stdout.
"""

import ast
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

FIXTURES = Path(__file__).parent / "fixtures" / "action_legacy"
HASHES = {
    "baselines.py.txt": "aef8c05c6c23ed4262d335808c34c15f6b61f5598a9b9976525b5fb71a976941",
    "outcome_values.py.txt": "a29e5abbedf8a27eb5065b5ebd11e0ef477d6f05ae6b9e884b1005ecc240f1c9",
    "lane_study.py.txt": "a62d53584e1188f4709c167b29ec03fab8986cdb09a15e7d0a1dda3234a8711d",
}


class SyntheticPropensity:
    """Hand-written backend state, not a trained or deserialized model."""

    def predict_proba(self, features):
        p = features[:, 1]
        return np.column_stack((1 - p, p))


def propensity_pipeline(width):
    """Real sklearn operators with manually specified fitted state; no fitting."""
    from sklearn.impute import MissingIndicator, SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

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
    classifier.coef_ = np.linspace(-0.02, 0.03, output_width)[None, :]
    classifier.coef_[0, 0] = 0.0
    classifier.intercept_ = np.array([0.1])
    return Pipeline(
        [("simpleimputer", imputer), ("standardscaler", scaler), ("logisticregression", classifier)]
    )


def guard_fitting():
    import scipy.optimize
    from sklearn.impute import MissingIndicator, SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy parity must never fit or optimize")

    for backend in (MissingIndicator, SimpleImputer, LogisticRegression, Pipeline, StandardScaler):
        backend.fit = forbidden
    scipy.optimize.minimize = forbidden


def extract(filename, functions, namespace):
    raw = (FIXTURES / filename).read_bytes()
    if hashlib.sha256(raw).hexdigest() != HASHES[filename]:
        raise ValueError("legacy source fixture hash mismatch")
    source = raw.decode()
    nodes = {
        node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
    }
    for name in functions:
        # Source text is executed verbatim, not transformed or imported from new code.
        exec(compile(ast.get_source_segment(source, nodes[name]), filename, "exec"), namespace)


def main():
    payload = json.load(sys.stdin)
    namespace = {"np": np, "Counter": Counter, "defaultdict": defaultdict}
    operation = payload["operation"]
    if operation == "values":
        # The old whitelist is tiny and independently loaded from the full frozen source.
        baseline = (FIXTURES / "baselines.py.txt").read_bytes()
        if hashlib.sha256(baseline).hexdigest() != HASHES["baselines.py.txt"]:
            raise ValueError("legacy feature fixture hash mismatch")
        source = baseline.decode()
        node = next(n for n in ast.parse(source).body if getattr(n, "name", None) == "_features")
        exec(compile(ast.get_source_segment(source, node), "legacy_features", "exec"), namespace)
        namespace.update(TRIM=0.05, BINS=5)
        extract(
            "outcome_values.py.txt",
            ("pareto", "estimate", "score", "summary", "population_summary"),
            namespace,
        )
        state = payload["state"]
        state["arms"] = tuple(state["arms"])
        state["targets"] = tuple(state["targets"])
        state["strata"] = {int(key): value for key, value in state["strata"].items()}
        rows = payload["rows"]
        if state["propensity"] == "pipeline":
            guard_fitting()
            width = len(rows[0]["static"]) + len(rows[0]["sequence"][-1])
            state["propensity"] = propensity_pipeline(width)
        elif state["propensity"] is not None:
            state["propensity"] = SyntheticPropensity()
        result = {"predictions": namespace["estimate"](state, rows)}
        if payload.get("evaluate"):
            records = namespace["score"](state, rows)
            result.update(
                records=records,
                summary=namespace["population_summary"](records, state["arms"], state["targets"]),
            )
    elif operation == "reference":
        from sklearn.metrics import average_precision_score, log_loss

        namespace.update(average_precision_score=average_precision_score, log_loss=log_loss)
        namespace["SEED"] = 20261122
        extract("lane_study.py.txt", ("summarize", "paired"), namespace)
        result = namespace["summarize"](payload["rows"], payload.get("behavior", False))
        if "second" in payload:
            result = {
                "summary": result,
                "paired": namespace["paired"](payload["rows"], payload["second"]),
            }
    else:
        raise ValueError("unknown oracle operation")
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
