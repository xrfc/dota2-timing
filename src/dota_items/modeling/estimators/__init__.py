"""Explicit, lazy built-in selection; no dynamic plugin loading."""

from typing import Protocol


class Estimator(Protocol):
    def fit_parameters(self, x, y, *, c: float, solver: str) -> dict:
        """Fit one observed two-class target; return JSON-ready parameters."""
        ...


def get_estimator(family: str) -> Estimator:
    if family == "frequency":
        from .frequency import FrequencyEstimator

        return FrequencyEstimator()
    if family == "logistic":
        from .logistic import LogisticEstimator

        return LogisticEstimator()
    raise ValueError("Unsupported model family")
