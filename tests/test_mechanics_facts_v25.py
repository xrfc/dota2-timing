"""v25 and derived v16: the haste mechanism and escape haste as a weak-dispellable save."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v25 import build_reviewed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v25"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v16"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v16 as derived  # noqa: E402
import build_mechanics_facts_v25 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v25.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v25")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v25")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v25.json" in profiles["sources"]["facts"]


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


from dota_items.data.mechanics_traits_v4 import _check  # noqa: E402

ESCAPE = 16


def _traits():
    return _load(DERIVED / "hero-traits-v3.json")["traits"]


def _count(trait, hero_id):
    return next(c for c in _traits()[trait]["counts"] if c["hero_id"] == hero_id)


def test_haste_rows_and_vocabulary():
    rows = [r for r in _doc()["rows"] if r["mechanism"] == "haste"]
    assert len(rows) == 116 and all(r["basis"] == "two_ai" for r in rows)
    assert _doc()["vocabulary"].endswith("vocabulary-v14.json")
    subjects = {r["subject"] for r in rows}
    assert {
        "dark_seer_surge",
        "slardar_sprint",
        "ogre_magi_bloodlust",
        "lycan_shapeshift",
    } <= subjects


def test_only_listed_haste_counts_as_a_save():
    listed = _traits()["dispellable_save"]["only_subjects"]
    assert len(listed["haste"]) == ESCAPE and listed["evasion"] == ["windrunner_windrun"]
    assert _count("dispellable_save", 55)["with_upgrades"] == 1  # Dark Seer, Surge
    assert _count("dispellable_save", 28)["with_upgrades"] == 1  # Slardar, Guardian Sprint
    assert _count("dispellable_save", 21)["with_upgrades"] == 2  # Windrunner, Windrun and Tailwind
    ogre = next(h for h in _traits()["dispellable_save"]["heroes"] if h["hero_id"] == 84)
    assert "ogre_magi_bloodlust" not in {a["subject"] for a in ogre["abilities"]}


def test_listed_subjects_need_a_matching_row():
    doc = {"rows": [{"subject": "a", "mechanism": "haste", "decision": "accept"}]}
    _check("t", {"haste": ["a"]}, doc)
    with pytest.raises(ValueError, match="no accepted haste row"):
        _check("t", {"haste": ["b"]}, doc)


def test_bad_haste_rows_raise():
    spec = {
        "review_id": "r1",
        "subject": "x",
        "subject_zh": "x",
        "mechanism": "haste",
        "decision": "accept",
        "basis": "two_ai",
        "condition": {"context": "base", "requires_scepter": False, "requires_shard": False},
        "notes_zh": [],
        "quotes": [],
    }
    base = {"rows": [], "counts": {}}
    assert build_reviewed(base, {"added_rows": [spec]}, {"haste": {}}, {"x"})["counts"]["rows"] == 1
    with pytest.raises(ValueError, match="Unknown subject"):
        build_reviewed(base, {"added_rows": [spec]}, {"haste": {}}, set())
    with pytest.raises(ValueError, match="only adds haste"):
        build_reviewed(base, {"added_rows": [{**spec, "mechanism": "slow"}]}, {"haste": {}}, {"x"})
    with pytest.raises(ValueError, match="Duplicate"):
        build_reviewed(
            base, {"added_rows": [spec, {**spec, "review_id": "r2"}]}, {"haste": {}}, {"x"}
        )
