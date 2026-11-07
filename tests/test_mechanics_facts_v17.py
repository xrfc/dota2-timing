"""MK-T5 v17: rule relations carry the conditions under which they hold (U104)."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_conditions import edge_holds, holds, is_conditional, label
from dota_items.data.mechanics_facts_v17 import build_reviewed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v17"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v7"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v7 as derived  # noqa: E402
import build_mechanics_facts_v17 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v17.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v17")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v17")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v17.json" in profiles["sources"]["facts"]


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


def _graph():
    return _load(DERIVED / "counter-graph.json")


def _target(rule, subject):
    return {r["id"]: r for r in _load(PACKAGE / "rules-evaluation.json")["rules"]}[rule][
        "target_conditions"
    ][subject]


def test_gush_and_sinister_gaze_are_blocked_only_without_scepter():
    for subject in ("tidehunter_gush", "lich_sinister_gaze"):
        for rule in ("R13", "R23"):
            entries = _target(rule, subject)
            assert holds(entries, set()) is True
            assert holds(entries, {"scepter"}) is False
            assert holds(entries) is None
            assert label(entries) == "有A杖时不成立"


def test_r12_conditional_heroes_are_conditions_not_only_notes():
    entries = _target("R12", "ogre_magi_ignite")
    assert holds(entries, set()) is True and holds(entries, {"scepter"}) is False
    edges = [e for e in _graph()["item_to_hero"] if e["rule"] == "R12" and e["hero_id"] == 84]
    assert edges and all(e["conditional"] for e in edges)
    assert all(edge_holds(e, {"scepter"}) is False for e in edges)


def test_upgrade_only_mechanisms_need_the_upgrade():
    entries = _target("R13", "tidehunter_dead_in_the_water")
    assert label(entries) == "需魔晶"
    assert holds(entries, set()) is False and holds(entries, {"shard"}) is True


def test_plain_edges_are_unconditional():
    edges = _graph()["item_to_hero"]
    plain = [e for e in edges if not e["conditional"]]
    assert plain and all(edge_holds(e) is True for e in plain)
    assert _graph()["schema"] == "mechanics-counter-graph/3"


def test_holds_logic():
    base = [{"when": "base", "unless": []}]
    off = [{"when": "base", "unless": ["scepter"]}]
    shard = [{"when": "shard", "unless": []}]
    assert holds(base) is True and not is_conditional(base)
    assert holds(off) is None and holds(off, set()) is True and holds(off, {"scepter"}) is False
    assert holds(shard) is None and holds(shard, {"shard"}) is True and holds(shard, set()) is False
    assert holds([*shard, *base]) is True


def test_condition_exception_needs_an_accepted_fact():
    base = {"rows": [], "counts": {}}
    bad = {"condition_exceptions": [{"subject": "x", "mechanism": "m", "unless": "scepter"}]}
    with pytest.raises(ValueError):
        build_reviewed(base, bad)


def test_profiles_carry_conditions_and_pages_show_them():
    profiles = _load(DERIVED / "hero-profiles.json")
    tide = next(p for p in profiles["profiles"] if p["hero_id"] == 29)
    r13 = next(e for e in tide["candidate_relations"]["targeted_by"] if e["rule"] == "R13")
    assert label(r13["own_conditions"]["tidehunter_gush"]) == "有A杖时不成立"
    page = (DERIVED / "heroes/hero-29.md").read_text(encoding="utf-8")
    assert "巨浪（有A杖时不成立）" in page and "重如铁锚（需魔晶）" in page
