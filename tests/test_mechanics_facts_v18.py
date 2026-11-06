"""MK-T5 v18: hero traits v3 as counts, rules v10 with more R12 exceptions (U105, U106)."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v18 import build_reviewed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v18"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v8"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v8 as derived  # noqa: E402
import build_mechanics_facts_v18 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v18.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v18")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v18")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v18.json" in profiles["sources"]["facts"]


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


NEW_EXCEPTIONS = [99, 28, 70, 12, 114, 102, 32, 10, 113, 62, 61, 18, 38, 4, 104]


def _traits():
    return _load(DERIVED / "hero-traits-v3.json")["traits"]


def _count(trait, hero_id):
    return next(c for c in _traits()[trait]["counts"] if c["hero_id"] == hero_id)


def test_every_hero_has_a_count_for_every_settled_trait():
    for trait in _traits().values():
        if trait["pending"]:
            assert not trait["counts"]
            continue
        assert len(trait["counts"]) == 127
        assert all(
            c["with_upgrades"] >= c["base"] or trait["zh"] == "法力依赖" for c in trait["counts"]
        )


def test_hard_control_follows_the_user_list():
    mapping = _load(ROOT / "knowledge/hero-traits/trait-mapping-v4.json")["traits"]
    assert set(mapping["disables"]["mechanisms"]) == {
        "stun",
        "hex",
        "taunt",
        "sleep",
        "hypnotize",
        "fear",
    }
    assert mapping["silence"]["mechanisms"] == ["silence"]
    assert set(mapping["mobility"]["mechanisms"]) == {"self_mobility", "terrain_walk"}


def test_upgrade_only_abilities_count_only_with_upgrades():
    medusa = _count("disables", 94)
    assert medusa["with_upgrades"] > medusa["base"]


def test_mana_dependence_comes_from_r12():
    for hero_id in (59, *NEW_EXCEPTIONS):
        assert _count("mana_dependent", hero_id) == {**_count("mana_dependent", hero_id), "base": 0}
    ogre = _count("mana_dependent", 84)
    assert ogre["base"] == 1 and ogre["with_upgrades"] == 0
    edges = _load(DERIVED / "counter-graph.json")["item_to_hero"]
    assert not {e["hero_id"] for e in edges if e["rule"] == "R12"} & set(NEW_EXCEPTIONS)


def test_v18_adds_no_condition_exceptions():
    with pytest.raises(ValueError):
        build_reviewed({}, {"condition_exceptions": [{"subject": "x"}]})


def test_magic_burst_is_the_user_list():
    counts = {c["hero_id"]: c["base"] for c in _traits()["magic_burst"]["counts"]}
    assert sum(counts.values()) == 33
    assert counts[25] == 1 and counts[1] == 0
