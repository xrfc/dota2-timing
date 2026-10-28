"""Small model-local scalar guards; no I/O or training dependencies."""

import math
import re


def _mapping(value, keys, name):
    if not isinstance(value, dict) or not set(keys) <= value.keys():
        raise ValueError(f"Missing or malformed {name}")


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _text(value):
    return isinstance(value, str) and bool(value.strip())
