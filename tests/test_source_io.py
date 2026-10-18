"""Public reads preserve legacy source parsing, not stricter artifact semantics."""

import io
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from dota_items.data import feasibility
from dota_items.data.source_io import (
    MAX_BYTES,
    AuditInputError,
    parse_source_json,
    read_source_bytes,
)


@pytest.mark.parametrize(
    "contents",
    [
        b'{"x":1,"x":2}',
        b"[true,false,null,0,-1,1.2]",
        b'"text"',
        b"123",
        b'\xef\xbb\xbf{"x":1}',
        '{"name":"英雄"}'.encode(),
        '{"x":1}'.encode("utf-16"),
    ],
)
def test_parser_matches_historical_source_behavior(contents):
    assert parse_source_json(contents) == json.loads(contents)
    assert feasibility._parse(contents) == parse_source_json(contents)


@pytest.mark.parametrize("contents", [b"NaN", b"Infinity", b"-Infinity", b'{"x":NaN}'])
def test_named_nonfinite_constants_remain_rejected(contents):
    with pytest.raises(ValueError, match="non-finite JSON number"):
        parse_source_json(contents)


@pytest.mark.parametrize("contents", [b"", b"{", b"\xff", b"{} {}"])
def test_invalid_json_and_encoding_remain_errors(contents):
    with pytest.raises((ValueError, UnicodeError)):
        parse_source_json(contents)


def test_overflow_float_is_not_silently_hardened_in_refactor():
    assert math.isinf(parse_source_json(b"1e999"))
    from dota_items.handoff.bundle import load_handoff_json

    with pytest.raises(ValueError):
        load_handoff_json(b"1e999")


def test_size_boundary_and_missing_file(tmp_path):
    path = tmp_path / "source.json"
    path.write_bytes(b"1234")
    before = path.read_bytes()
    assert MAX_BYTES == 64 * 1024 * 1024
    assert read_source_bytes(path, max_bytes=4) == before
    with pytest.raises(AuditInputError, match="input exceeds 64 MiB limit"):
        read_source_bytes(path, max_bytes=3)
    assert path.read_bytes() == before
    with pytest.raises(FileNotFoundError):
        read_source_bytes(tmp_path / "absent")
    assert feasibility.AuditInputError is AuditInputError


def test_bounded_read_does_not_trust_stat():
    class Stream(io.BytesIO):
        requested = None

        def read(self, n=-1):
            self.requested = n
            return super().read(n)

    stream = Stream(b"123456789")

    class GrowingSource:
        def open(self, mode):
            assert mode == "rb"
            return stream

    with pytest.raises(AuditInputError):
        read_source_bytes(GrowingSource(), max_bytes=4)
    assert stream.requested == 5


@pytest.mark.parametrize("limit", [True, -1, 1.5, None])
def test_invalid_new_api_limit_is_rejected(tmp_path, limit):
    with pytest.raises(ValueError, match="max_bytes"):
        read_source_bytes(tmp_path / "unused", max_bytes=limit)


def test_reader_does_not_import_auditor_or_third_party():
    code = """
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('pydantic', 'numpy', 'dota_items.data.feasibility')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from dota_items.data.source_io import read_source_bytes, parse_source_json
assert parse_source_json(b'{}') == {}
"""
    subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], check=True
    )
