"""Public, bounded source reads with the historical feasibility JSON semantics.

This is NOT the strict handoff/model artifact decoder. Duplicate JSON keys keep
last-value behavior; NaN/Infinity tokens are rejected, while 1e999 retains the
standard decoder's float-overflow behavior. Schema checks belong to callers.
"""

import json
from pathlib import Path

MAX_BYTES = 64 * 1024 * 1024


class AuditInputError(ValueError):
    """Safe diagnostic strings, never raw payloads or credentials."""


def read_source_bytes(path: Path, *, max_bytes: int = MAX_BYTES) -> bytes:
    """Read at most limit+1 bytes, including files growing after stat()."""
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("max_bytes must be a nonnegative integer")
    with path.open("rb") as stream:
        contents = stream.read(max_bytes + 1)
    if len(contents) > max_bytes:
        raise AuditInputError("input exceeds 64 MiB limit")
    return contents


def _reject_constant(value):
    raise ValueError("non-finite JSON number")


def parse_source_json(contents: bytes):
    """Decode source JSON without silently changing historical parser policy."""
    return json.loads(contents, parse_constant=_reject_constant)
