"""Train-only orchestration: masks, support, fixed estimator and provenance."""

import copy
import platform
from importlib.metadata import version
from pathlib import Path

import numpy as np

from dota_items.storage import digest, file_hash

from ._validation import _sha256, _text
from .artifacts import validate_model
from .estimators import get_estimator
from .provenance import IMPLEMENTATION_FILES, SCHEMA, TASK_SCHEMA
from .specs import C_GRID, TASK, check_preprocessing, check_task, task_items


def fit_model(
    batch, *, family="frequency", c=1.0, solver="liblinear", source_sha256, code_revision
):
    """Fixed parameters only. No validation selection or real-data CLI."""
    if batch.split != "train":
        raise ValueError("Fit accepts train only")
    if family not in ("frequency", "logistic") or solver not in ("liblinear", "lbfgs"):
        raise ValueError("Unsupported model family or solver")
    if type(c) not in (int, float) or c not in C_GRID:
        raise ValueError("C must use existing grid")
    check_preprocessing(batch.preprocessing)
    check_task(batch.task)
    items = task_items(batch.task)
    if type(batch.synthetic) is not bool:
        raise ValueError("Invalid synthetic marker")
    if any(
        not isinstance(array, np.ndarray) or array.ndim != 2
        for array in (batch.x, batch.y, batch.mask)
    ):
        raise ValueError("Training arrays must be two-dimensional NumPy arrays")
    n = len(batch.x)
    if (
        batch.x.shape != (n, len(batch.preprocessing["columns"]))
        or batch.y.shape != (n, len(items))
        or batch.mask.shape != batch.y.shape
        or batch.mask.dtype != bool
        or batch.x.dtype.kind not in "fiu"
        or batch.y.dtype.kind not in "fiu"
        or not n
        or not np.isfinite(batch.x).all()
        or not np.isin(batch.y[batch.mask], [0, 1]).all()
        or not np.isnan(batch.y[~batch.mask]).all()
    ):
        raise ValueError("Invalid training arrays or mask/null contract")
    width = len(batch.preprocessing["vocabulary"])
    ally, enemy = batch.x[:, :width], batch.x[:, width + 1 : -1]
    counts = batch.x[:, [width, -1]]
    if (
        not np.isin(ally, [0, 1]).all()
        or not np.isin(enemy, [0, 1]).all()
        or not np.isin(counts, range(6)).all()
        or not np.all(ally.sum(axis=1) + counts[:, 0] == 5)
        or not np.all(enemy.sum(axis=1) + counts[:, 1] == 5)
        or np.any(ally + enemy > 1)
        or np.any(counts)
        or not np.all((ally + enemy).any(axis=0))
        or not np.all(ally[:, batch.preprocessing["vocabulary"].index(TASK.target_hero_id)] == 1)
        or not np.all(enemy[:, batch.preprocessing["vocabulary"].index(TASK.target_hero_id)] == 0)
    ):
        raise ValueError("Invalid lineup feature values")
    if not _sha256(source_sha256) or not _text(code_revision):
        raise ValueError("Source hash and code revision required")
    estimator = get_estimator(family)
    models = []
    for j, item in enumerate(items):
        keep = batch.mask[:, j]
        labels = batch.y[keep, j]
        support = {
            "observed": len(labels),
            "positive": int(labels.sum()),
            "unknown": int((~keep).sum()),
        }
        if len(np.unique(labels)) != 2:
            models.append(
                {
                    "item": item,
                    "status": "untrained",
                    "support": support,
                    "reason": "no_observations" if not len(labels) else "single_class",
                }
            )
            continue
        entry = {
            "item": item,
            "status": "trained",
            "support": support,
            "frequency": float(labels.mean()),
        }
        entry.update(estimator.fit_parameters(batch.x[keep], labels, c=c, solver=solver))
        models.append(entry)
    package = Path(__file__).resolve().parents[1]
    implementation_files = {
        name: file_hash(package / name.removeprefix("src/dota_items/"))
        for name in IMPLEMENTATION_FILES
    }
    artifact = {
        "schema_version": TASK_SCHEMA if "contract" in batch.task else SCHEMA,
        "synthetic": batch.synthetic,
        "task": copy.deepcopy(batch.task),
        "preprocessing": copy.deepcopy(batch.preprocessing),
        "family": family,
        "parameters": {
            "C": c if family == "logistic" else None,
            "solver": solver if family == "logistic" else None,
            "max_iter": 2000,
            "random_state": 0,
            "class_weight": None,
        },
        "models": models,
        "provenance": {
            "source_sha256": source_sha256,
            "code_revision": code_revision,
            "implementation_sha256": implementation_files[IMPLEMENTATION_FILES[0]],
            "implementation_files_sha256": implementation_files,
            "implementation_bundle_sha256": digest(implementation_files),
            "python": platform.python_version(),
            "dependencies": {p: version(p) for p in ("numpy", "scikit-learn")},
        },
        "meaning": "Source log presence only; not optimal equipment or complete purchases.",
    }
    validate_model(artifact)
    return artifact
