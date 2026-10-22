"""Compatibility import facade; implementation lives in experiments.whole_log.regularization."""

from dota_items.experiments.whole_log import regularization as _implementation
from dota_items.experiments.whole_log.regularization import *  # noqa: F403


def __getattr__(name):
    return getattr(_implementation, name)
