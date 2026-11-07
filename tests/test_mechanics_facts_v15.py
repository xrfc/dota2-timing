"""MK-T5 v15: R12 by hero exceptions, R13 split into block and reflect, U99-U100 rulings."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_rules_v8 import expand_rules

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v15"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v5"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v5 as derived  # noqa: E402
import build_mechanics_facts_v15 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v15.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v15")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v15")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]


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


EXCEPT = {59, 2, 71, 6, 95, 44, 1, 80, 26, 76}


def _graph():
    return _load(DERIVED / "counter-graph.json")


def _evaluation():
    return {rule["id"]: rule for rule in _load(PACKAGE / "rules-evaluation.json")["rules"]}


def test_r12_targets_every_hero_but_the_exceptions():
    edges = [edge for edge in _graph()["item_to_hero"] if edge["rule"] == "R12"]
    heroes = {edge["hero_id"] for edge in edges}
    assert edges and not heroes & EXCEPT
    assert {84, 42} <= heroes
    marked = {edge["hero_id"] for edge in edges if edge.get("exception")}
    assert marked == {84, 42}
    assert all(edge["exception"]["condition"] == "A杖" for edge in edges if edge.get("exception"))
    assert _evaluation()["R12"]["status"] == "candidate"


def test_block_and_reflect_are_separate():
    evaluation = _evaluation()
    for subject in ("morphling_replicate", "life_stealer_infest", "rubick_spell_steal"):
        assert subject in evaluation["R13"]["targets"]
        assert subject not in evaluation["R23"]["targets"]
    assert all(
        rule["status"] == "candidate"
        for rule in evaluation.values()
        if rule["id"] in ("R13", "R23")
    )


@pytest.mark.parametrize(
    "subject",
    ["lina_dragon_slave", "lion_impale", "jakiro_dual_breath", "dragon_knight_breathe_fire"],
)
def test_directional_spells_are_not_unit_target(subject):
    doc = _doc()
    rows = _rows(doc, subject, "unit_target_spell")
    assert rows and all(r["decision"] == "reject" and r["basis"] == "user:U100" for r in rows)
    evaluation = _evaluation()
    assert subject not in evaluation["R13"]["targets"]
    assert subject not in evaluation["R23"]["targets"]


def test_black_grimoire_left_the_active_items():
    doc = _doc()
    assert not [r for r in doc["rows"] if r["subject"] == "black_grimoire"]
    assert [r for r in doc["retired_rows"] if r["subject"] == "black_grimoire"]
    assert not (DERIVED / "items/black_grimoire.md").exists()


def test_expand_rules_rejects_unknown_heroes_and_abilities():
    heroes = [{"hero_id": 1, "abilities": [{"name": "a"}]}]
    doc = {
        "field_observations": [{"subject": "a", "evidence_kind": "field:mana_costs", "value": [50]}]
    }
    rule = {"id": "R", "target_heroes": {"abilities": "with_mana_cost", "except": [9]}}
    with pytest.raises(ValueError):
        expand_rules([rule], heroes, doc)
    rule["target_heroes"] = {"abilities": "everything", "except": []}
    with pytest.raises(ValueError):
        expand_rules([rule], heroes, doc)
    rule["target_heroes"] = {"abilities": "with_mana_cost", "except": []}
    assert expand_rules([rule], heroes, doc)[0]["target_subjects"] == ["a"]
