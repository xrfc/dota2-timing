"""MK-T6c v20: every numeric upgrade carries the ruling behind it (U113)."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v20 import build_reviewed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v20"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v11"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v11 as derived  # noqa: E402
import build_mechanics_facts_v20 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v20.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v20")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v20")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v20.json" in profiles["sources"]["facts"]


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


def _base(*entries):
    return {"numeric_upgrades": list(entries)}


def _entry(subject, kind, context="scepter_upgrade"):
    return {"subject": subject, "kind": kind, "condition": {"context": context}}


RULING = {
    "review_id": "r1",
    "subject": "a",
    "mechanism": "healing",
    "numeric_upgrade": True,
    "decision_ref": "U66",
    "note_zh": "x",
    "date": "2026-11-05",
}


def test_every_numeric_upgrade_has_a_ruling():
    upgrades = _doc()["numeric_upgrades"]
    assert len(upgrades) == 69
    counts = {}
    for entry in upgrades:
        key = (entry["ruling"]["how"], entry["ruling"]["decision"])
        counts[key] = counts.get(key, 0) + 1
    assert counts == {
        ("rule", "U65"): 29,
        ("user_ruling", "U65"): 3,
        ("user_ruling", "U66"): 18,
        ("user_ruling", "U72"): 19,
    }
    assert all(e["kind"] == "cooldown_reduction" for e in upgrades if e["ruling"]["how"] == "rule")


def test_rows_are_unchanged_from_v19():
    old = _load(ROOT / "knowledge/mechanics/extractions/v19/facts-v19.json")
    assert _doc()["rows"] == old["rows"]
    assert [{k: v for k, v in e.items() if k != "ruling"} for e in _doc()["numeric_upgrades"]] == (
        old["numeric_upgrades"]
    )


def test_unmatched_entries_and_unused_rulings_raise():
    doc = build_reviewed(_base(_entry("a", "healing")), [RULING])
    assert doc["numeric_upgrades"][0]["ruling"]["decision"] == "U66"
    cooldown = build_reviewed(_base(_entry("b", "cooldown_reduction", "shard_upgrade")), [])
    assert cooldown["numeric_upgrades"][0]["ruling"]["how"] == "rule"
    with pytest.raises(ValueError, match="No ruling"):
        build_reviewed(_base(_entry("c", "healing")), [])
    with pytest.raises(ValueError, match="No ruling"):
        build_reviewed(_base(_entry("d", "cooldown_reduction", "base")), [])
    with pytest.raises(ValueError, match="without an upgrade"):
        build_reviewed(_base(), [RULING])
