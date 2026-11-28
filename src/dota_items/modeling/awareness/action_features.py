"""Decision-only encoders and already learned scaling; no fitting or source reads.

Public encoding validates the registered task. Private row helpers preserve the
original numerical boundary for controlled migration/parity tests, including the
baseline's use of only the last frame. Artifact admission is a separate boundary.
"""

from dataclasses import dataclass
from numbers import Real

import numpy as np

from dota_items.contracts.action_outcomes import validate_decision


def _state_fields(state, names):
    if type(state) is not dict or set(state) != set(names):
        raise ValueError("state fields differ from the model family")


def _state_array(value, name, *, kind="f"):
    if not isinstance(value, np.ndarray) or value.ndim != 1 or value.dtype.kind not in kind:
        raise ValueError(f"{name} requires a one-dimensional {kind} array")
    if not np.isfinite(value).all():
        raise ValueError(f"{name} must be finite")
    return value.copy()


def _state_number(value, name, *, low=None, high=None):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} must be finite numeric state")
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f"{name} outside its state range")
    return value


@dataclass
class FeatureScale:
    """Learned offsets and dispersion; construction never estimates statistics."""

    median: np.ndarray
    scale: np.ndarray

    def __post_init__(self):
        self.median = _state_array(self.median, "median")
        self.scale = _state_array(self.scale, "scale")
        if self.median.shape != self.scale.shape or np.any(self.scale <= 0):
            raise ValueError("scale must match median and be positive")

    @classmethod
    def from_state(cls, state):
        _state_fields(state, ("median", "scale"))
        return cls(state["median"], state["scale"])

    def to_state(self):
        return {"median": self.median.copy(), "scale": self.scale.copy()}

    def transform(self, values):
        if np.ndim(values) == 0 or np.shape(values)[-1] != self.median.size:
            raise ValueError("input width differs from the learned feature scale")
        missing = ~np.isfinite(values)
        standardized = (np.where(missing, self.median, values) - self.median) / self.scale
        return np.concatenate((np.clip(standardized, -10, 10), missing), axis=-1)


def _is_farm(row):
    if row["action"] not in ("farm", "retreat"):
        raise ValueError("training and outcome prediction require a recognized wave action")
    return int(row["action"] == "farm")


def _row_features(rows, *, history=False, action=False):
    values = []
    for row in rows:
        frames = row["sequence"] if history else row["sequence"][-1:]
        vector = [*row["static"], *(value for frame in frames for value in frame)]
        if action:
            vector.append(_is_farm(row))
        values.append(vector)
    return np.asarray(values, dtype=float)


def encode_decision(decisions, *, history=False):
    """Encode the task's validated decision fields, never outcomes or identity keys."""
    rows = [validate_decision(decision).to_features() for decision in decisions]
    return _row_features(rows, history=history)


def _sequence_inputs(rows, history):
    sequence = np.asarray([row["sequence"] for row in rows], dtype=float)
    if sequence.ndim != 3 or sequence.shape[1] != 3:
        raise ValueError("expected exactly three equal-width sequence frames per case")
    static = np.asarray([row["static"] for row in rows], dtype=float)
    actions = [row["action"] for row in rows]
    if not all(action in ("farm", "retreat") for action in actions):
        raise ValueError("unknown observed action")
    return static, sequence if history else sequence[:, -1:], np.equal(actions, "farm")[:, None]


def _sequence_design(static, sequence, action, static_scale, sequence_scale):
    static = np.concatenate((static_scale.transform(static), action), axis=1)
    frames = sequence_scale.transform(sequence)
    previous = np.concatenate((np.zeros_like(frames[:, :1]), frames[:, :-1]), axis=1)
    return static, np.concatenate((previous, frames), axis=2)
