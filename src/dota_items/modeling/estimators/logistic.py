"""Existing fixed-parameter logistic fit, without selection or evaluation."""

import warnings

from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression


class LogisticEstimator:
    def fit_parameters(self, x, y, *, c, solver):
        model = LogisticRegression(C=c, solver=solver, max_iter=2000, random_state=0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(x, y)
        if model.n_iter_.max() >= model.max_iter:
            raise ValueError("Model did not converge")
        return {
            "frequency": float(y.mean()),
            "coefficients": model.coef_[0].tolist(),
            "intercept": float(model.intercept_[0]),
        }
