"""Finite numeric values shared by replay contracts."""

import math
from typing import Any


def number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
