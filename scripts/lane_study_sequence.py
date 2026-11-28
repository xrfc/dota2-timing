"""Three-frame outcome challengers using shared, causal two-frame convolution filters."""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


@dataclass
class FeatureScale:
    median: np.ndarray
    scale: np.ndarray

    @classmethod
    def fit(cls, values):
        # Completely missing training columns have no learned offset or dispersion.
        median = np.zeros(values.shape[1])
        scale = np.ones(values.shape[1])
        for i, column in enumerate(values.T):
            known = column[np.isfinite(column)]
            if known.size:
                median[i] = np.median(known)
                scale[i] = known.std() or 1.0
        return cls(median, scale)

    def transform(self, values):
        missing = ~np.isfinite(values)
        standardized = (np.where(missing, self.median, values) - self.median) / self.scale
        return np.concatenate((np.clip(standardized, -10, 10), missing), axis=-1)


def _inputs(rows, history):
    sequence = np.asarray([row["sequence"] for row in rows], dtype=float)
    if sequence.ndim != 3 or sequence.shape[1] != 3:
        raise ValueError("expected exactly three equal-width sequence frames per case")
    static = np.asarray([row["static"] for row in rows], dtype=float)
    actions = [row["action"] for row in rows]
    if not all(action in ("farm", "retreat") for action in actions):
        raise ValueError("unknown observed action")
    return static, sequence if history else sequence[:, -1:], np.equal(actions, "farm")[:, None]


def _design(static, sequence, action, static_scale, sequence_scale):
    static = np.concatenate((static_scale.transform(static), action), axis=1)
    frames = sequence_scale.transform(sequence)
    # Left padding provides a causal first window for both the one- and three-frame arms.
    previous = np.concatenate((np.zeros_like(frames[:, :1]), frames[:, :-1]), axis=1)
    return static, np.concatenate((previous, frames), axis=2)


def _unpack(parameters, window_width, static_width):
    """One bank of 8 filters feeds both heads along with decision-time static inputs."""
    filters = 8
    split = window_width * filters
    kernels = parameters[:split].reshape(window_width, filters)
    bias = parameters[split : split + filters]
    head = parameters[split + filters :].reshape(filters + static_width + 1, 2)
    return kernels, bias, head


def _forward(parameters, static, windows):
    kernels, bias, head = _unpack(parameters, windows.shape[-1], static.shape[-1])
    activations = np.tanh(windows @ kernels + bias)
    pooled = activations.mean(axis=1)
    features = np.column_stack((pooled, static, np.ones(len(static))))
    return features @ head, activations, features


def _objective(parameters, static, windows, target_hits, deaths):
    output, activations, features = _forward(parameters, static, windows)
    kernels, _, head = _unpack(parameters, windows.shape[-1], static.shape[-1])
    residual = output[:, 0] - target_hits
    logits = output[:, 1]
    loss = np.mean(0.5 * residual**2 + np.logaddexp(0, logits) - deaths * logits)
    delta = np.column_stack((residual, expit(logits) - deaths)) / len(static)
    # Gradient of mean pooling shares the signal over the observed windows.
    pooled_delta = delta @ head[: activations.shape[-1]].T
    hidden_delta = pooled_delta[:, None, :] * (1 - activations**2) / windows.shape[1]
    kernel_gradient = windows.reshape(-1, windows.shape[-1]).T @ hidden_delta.reshape(
        -1, activations.shape[-1]
    )
    penalty = 0.01
    head_gradient = features.T @ delta
    head_gradient[:-1] += penalty * head[:-1]
    gradient = np.concatenate(
        (
            (kernel_gradient + penalty * kernels).ravel(),
            hidden_delta.sum(axis=(0, 1)),
            head_gradient.ravel(),
        )
    )
    loss += 0.5 * penalty * (np.sum(kernels**2) + np.sum(head[:-1] ** 2))
    return loss, gradient


@dataclass
class SequenceOutcome:
    history: bool
    static_scale: FeatureScale
    sequence_scale: FeatureScale
    parameters: np.ndarray
    hits_mean: float
    hits_std: float
    constant_death: float | None

    @classmethod
    def fit(cls, rows, seed, *, history):
        static, sequence, actions = _inputs(rows, history)
        static_scale = FeatureScale.fit(static)
        sequence_scale = FeatureScale.fit(sequence.reshape(-1, sequence.shape[-1]))
        static, windows = _design(static, sequence, actions, static_scale, sequence_scale)
        hits = np.asarray([row["hits"] for row in rows], dtype=float)
        deaths = np.asarray([row["death"] for row in rows], dtype=float)
        mean, std = float(hits.mean()), float(hits.std())
        constant = float(deaths[0]) if (deaths == deaths[0]).all() else None
        n_params = windows.shape[-1] * 8 + 8 + (8 + static.shape[-1] + 1) * 2
        initial = np.random.default_rng(seed).normal(0, 0.1, n_params)
        result = minimize(
            _objective,
            initial,
            args=(static, windows, (hits - mean) / (std or 1.0), deaths),
            method="L-BFGS-B",
            jac=True,
            options={"maxiter": 100, "ftol": 1e-8},
        )
        if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            raise ValueError("non-finite sequence model fit")
        return cls(history, static_scale, sequence_scale, result.x, mean, std, constant)

    def predict(self, rows):
        static, sequence, actions = _inputs(rows, self.history)
        static, windows = _design(static, sequence, actions, self.static_scale, self.sequence_scale)
        output, _, _ = _forward(self.parameters, static, windows)
        hits = np.maximum(0, self.hits_mean + self.hits_std * output[:, 0])
        death = (
            expit(output[:, 1])
            if self.constant_death is None
            else np.full(len(rows), self.constant_death)
        )
        return hits, death


def fit_predict(train, test, seed):
    """Fit same-fold comparators and return predictions plus portable fitted estimators."""
    from scripts.lane_study_baselines import TreeOutcome

    models = {
        "three_frame_tree": TreeOutcome.fit(train, seed, history=True),
        "last_frame_nn": SequenceOutcome.fit(train, seed, history=False),
        "temporal_nn": SequenceOutcome.fit(train, seed, history=True),
    }
    return {name: model.predict(test) for name, model in models.items()}, models
