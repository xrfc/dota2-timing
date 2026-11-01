"""Current mechanics decisions: rounds combined, every Claude/Codex difference settled."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "knowledge/mechanics/reviews/resolution-001"
sys.path.insert(0, str(ROOT / "scripts"))

import resolve_mechanics_reviews as resolver  # noqa: E402


def test_checked_in_resolution_replays():
    rows, additions, summary = resolver.resolve()
    lines = (OUT / "resolved.jsonl").read_text().splitlines()
    assert [json.loads(x) for x in lines] == rows
    assert json.loads((OUT / "summary.json").read_text()) == summary
    assert json.loads((OUT / "additions.json").read_text()) == additions
    manifest = json.loads((OUT / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == expected


def test_user_u37_rulings_apply():
    rows = {r["review_id"]: r for r in resolver.resolve()[0]}
    assert rows["9a4820fac7d975b94fe6"]["decision"] == "accept"  # Arena of Blood
    assert rows["59688a0a24c1ed1186b5"]["decision"] == "accept"  # Will-O-Wisp
    assert rows["51e1396eee3671eb9765"]["decision"] == "reject"  # Poison Sting
    assert rows["b9194c489349772ab74e"]["decided_by"] == "U37"
    for row in rows.values():
        if row["codex"] not in (None, row["claude"]):
            assert row["decided_by"] == "U37"


def test_unsettled_difference_fails(tmp_path):
    for name in resolver.INPUTS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    user = tmp_path / resolver.USER[0]
    doc = json.loads(user.read_text())
    doc["decisions"] = [d for d in doc["decisions"] if d["review_id"] != "9a4820fac7d975b94fe6"]
    user.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="Unsettled"):
        resolver.resolve(tmp_path)
