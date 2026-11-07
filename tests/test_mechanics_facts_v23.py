"""v23 and derived v14: adjustments from the hero trait spot check (U118)."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v23 import build_reviewed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v23"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v14"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v14 as derived  # noqa: E402
import build_mechanics_facts_v23 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v23.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v23")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v23")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v23.json" in profiles["sources"]["facts"]


def _repo_imports(path, seen):
    if path in seen or not path.exists():
        return seen
    seen.add(path)
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        for name in names:
            if name.startswith("dota_items."):
                _repo_imports(ROOT / "src" / (name.replace(".", "/") + ".py"), seen)
            elif name.startswith("build_mechanics"):
                _repo_imports(ROOT / "scripts" / f"{name}.py", seen)
    return seen


def test_every_imported_repo_file_is_recorded():
    used = _repo_imports(Path(builder.__file__), set())
    recorded = {ROOT / name for name in builder.IMPLEMENTATION}
    assert used <= recorded, sorted(str(path) for path in used - recorded)


def test_every_file_the_build_reads_is_declared(monkeypatch, tmp_path):
    seen = set()
    real_open = builtins.open

    def spy(file, *args, **kwargs):
        try:
            path = os.path.abspath(os.fspath(file))
        except TypeError:
            return real_open(file, *args, **kwargs)
        if path.startswith(str(ROOT)) and os.path.isfile(path):
            seen.add(os.path.relpath(path, ROOT))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr("io.open", spy)
    builder.run(tmp_path / "out")
    monkeypatch.undo()
    read = {name for name in seen if not name.endswith(".py")}
    assert read
    assert read <= set(builder.declared_inputs())
    assert set(builder.declared_inputs()) == set(_load(PACKAGE / "manifest.json")["input_sha256"])


def _count(trait, hero_id):
    traits = _load(DERIVED / "hero-traits-v3.json")["traits"]
    return next(c for c in traits[trait]["counts"] if c["hero_id"] == hero_id)


def test_oracle_joins_the_magic_burst_list():
    assert _count("magic_burst", 111)["base"] == 1
    traits = _load(DERIVED / "hero-traits-v3.json")["traits"]
    assert sum(c["base"] for c in traits["magic_burst"]["counts"]) == 34


def test_wolf_evasion_is_not_lycan_self_evasion():
    rows = _rows(_doc(), "lycan_summon_wolves", "evasion")
    assert [(r["decision"], r["basis"]) for r in rows] == [("reject", "user:U118")]
    assert _count("evasion", 77) == {**_count("evasion", 77), "base": 0, "with_upgrades": 0}


def test_decision_changes_are_checked():
    row = {
        "review_id": "r1",
        "subject": "x",
        "mechanism": "evasion",
        "decision": "accept",
        "basis": "two_ai",
        "notes_zh": [],
    }
    change = {
        "review_id": "r1",
        "subject": "x",
        "mechanism": "evasion",
        "from": "accept",
        "to": "reject",
        "basis": "user:U0",
        "note_zh": "n",
    }
    base = {"rows": [row], "counts": {}}
    assert build_reviewed(base, {"decision_changes": [change]})["rows"][0]["decision"] == "reject"
    for bad, match in (
        ({**change, "from": "reject"}, "does not match"),
        ({**change, "basis": "two_ai"}, "user basis"),
        ({**change, "review_id": "r9"}, "without a matching row"),
    ):
        with pytest.raises(ValueError, match=match):
            build_reviewed(base, {"decision_changes": [bad]})
