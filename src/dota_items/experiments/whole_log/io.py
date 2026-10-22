"""Experiment I/O primitives; schemas and completion ordering stay with each workflow."""

import math
from pathlib import Path

from dota_items.storage import file_hash, json_bytes


def load(path):
    import json

    from dota_items.data.source_io import read_source_bytes

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError(f"Non-finite JSON: {value}")

    return json.loads(read_source_bytes(path), object_pairs_hook=pairs, parse_constant=reject)


def assert_equal(actual, expected, context):
    """Strict structure/types, with only finite float arithmetic tolerance."""
    if type(actual) is not type(expected):
        raise ValueError(f"Mismatch: {context}")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"Mismatch: {context}")
        for key in expected:
            assert_equal(actual[key], expected[key], context + "/" + str(key))
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"Mismatch: {context}")
        for a, b in zip(actual, expected, strict=True):
            assert_equal(a, b, context)
    elif isinstance(expected, float):
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"Mismatch: {context}")
    elif actual != expected:
        raise ValueError(f"Mismatch: {context}")


def check_unchanged(files, *, message="Handoff input changed"):
    for name, sha in files.items():
        if file_hash(Path(name)) != sha:
            raise ValueError(f"{message}: {name}")


def write_exclusive(path, value):
    with Path(path).open("xb") as stream:
        stream.write(json_bytes(value))
