"""Integration must preserve frozen model sources and explicit current review identity."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "docs/acceptance"


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_all_u191_sources_remain_at_their_original_paths():
    frozen = json.loads((ACCEPTANCE / "outcome-u191-freeze.json").read_text())
    assert len(frozen["sources"]) == 26
    assert {path: sha(path) for path in frozen["sources"]} == frozen["sources"]


def test_review_entrypoints_are_additive_and_exactly_registered():
    record = json.loads((ACCEPTANCE / "review-entrypoint-transition-20261128.json").read_text())
    frozen = json.loads((ACCEPTANCE / "outcome-u191-freeze.json").read_text())["sources"]
    assert record["mode"] == "new-output-only"
    assert record["reuse_old_receipts"] is False
    assert len({entry["new_path"] for entry in record["entries"]}) == 7
    for entry in record["entries"]:
        assert entry["old_path"] != entry["new_path"]
        assert entry["old_sha256"] == frozen[entry["old_path"]] == sha(entry["old_path"])
        assert entry["new_sha256"] == sha(entry["new_path"])
