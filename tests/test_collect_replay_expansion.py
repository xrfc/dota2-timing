"""Network-free guards for bounded replay acquisition."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "collect_replay_expansion",
    Path(__file__).resolve().parents[1] / "scripts/collect_replay_expansion.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.example/a",
        "http://valve.net.evil.example/a",
        "file:///tmp/a",
        "http://user:pass@replay1.valve.net/a",
        "http://replay1.valve.net:444/a",
    ],
)
def test_reject_non_replay_hosts(url):
    with pytest.raises(ValueError):
        mod.validate_url(url)


def test_advertised_replay_host():
    mod.validate_url("http://replay413.dota2.com.cn/570/123.dem.bz2")


class Response:
    def __init__(self, blocks):
        self.blocks = blocks

    def iter_bytes(self, size):
        return iter(self.blocks)


def test_download_budget_counts_failed_bytes(tmp_path):
    budget = {"bytes_received": 7, "limit": 10}
    with pytest.raises(ValueError, match="budget"):
        mod.copy_download(Response([b"BZh12345"]), tmp_path / "archive", budget, 100)
    assert budget["bytes_received"] == 15
    assert (tmp_path / "archive").read_bytes() == b""


def test_file_limit_and_unknown_compression(tmp_path):
    with pytest.raises(ValueError, match="budget"):
        mod.copy_download(
            Response([b"BZh12345"]), tmp_path / "large", {"bytes_received": 0, "limit": 100}, 4
        )
    with pytest.raises(ValueError, match="compression"):
        mod.copy_download(
            Response([b"html"]), tmp_path / "html", {"bytes_received": 0, "limit": 100}, 100
        )


def test_no_overwrite(tmp_path):
    target = tmp_path / "receipt.json"
    mod.save(target, {"original": True})
    with pytest.raises(FileExistsError):
        mod.save(target, {"original": False})
    assert mod.read(target) == {"original": True}


def test_duplicate_candidates_rejected():
    with pytest.raises(ValueError, match="unique"):
        mod.validate({"candidates": [{"match_id": 1}, {"match_id": 1}]})


def test_metadata_drift_before_network(tmp_path):
    target = tmp_path / "metadata.json"
    target.write_text("{}")
    with pytest.raises(ValueError, match="Metadata changed"):
        mod.validate(
            {
                "candidates": [
                    {"match_id": 1, "metadata_path": str(target), "metadata_sha256": "bad"}
                ]
            }
        )


def test_download_success(tmp_path):
    budget = {"bytes_received": 0, "limit": 100}
    target = tmp_path / "archive"
    assert (
        mod.copy_download(Response([bytes.fromhex("28b52ffd"), b"abc"]), target, budget, 100) == 7
    )
    assert budget["bytes_received"] == 7
