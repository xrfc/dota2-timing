"""Compatibility import facade; implementation lives in experiments.whole_log.baseline."""

from dota_items.experiments.whole_log import baseline as _implementation
from dota_items.experiments.whole_log.baseline import *  # noqa: F403


def __getattr__(name):
    return getattr(_implementation, name)
