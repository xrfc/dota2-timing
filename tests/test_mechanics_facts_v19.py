"""MK-T6b v19: rules v11 declare every field they do not compute (U92, U113)."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v19 import add_not_computed, build_reviewed
from dota_items.data.mechanics_rules_v11 import check_rule_fields, load_rules_v11

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v19"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v9"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v9 as derived  # noqa: E402
import build_mechanics_facts_v19 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v19.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v19")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v19")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v19.json" in profiles["sources"]["facts"]


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


RULES = ROOT / "knowledge/mechanics/rules-v11.json"


def _rule(**fields):
    return {"id": "RX", "zh": "x", "relation": "counters", "decision": "U0", **fields}


def test_rules_v11_declare_exactly_the_three_recorded_only_rules():
    rules = _load(RULES)["rules"]
    declared = {r["id"]: r["not_computed"]["fields"] for r in rules if "not_computed" in r}
    assert declared == {
        "R08": ["parameters"],
        "R09": ["target_exempt_mechanisms"],
        "R19": ["pairs"],
    }
    for rule in rules:
        check_rule_fields(rule)


def test_unknown_or_undeclared_fields_raise():
    with pytest.raises(ValueError, match="does not know"):
        check_rule_fields(_rule(source_mechanisms=["stun"], weight=2))
    with pytest.raises(ValueError, match="declare them in not_computed"):
        check_rule_fields(_rule(pairs=[["a", "b"]]))
    with pytest.raises(ValueError, match="must equal"):
        check_rule_fields(
            _rule(
                pairs=[["a", "b"]],
                parameters={},
                not_computed={"fields": ["pairs"], "reason_zh": "x", "decision": "U0"},
            )
        )
    with pytest.raises(ValueError, match="reason_zh and decision"):
        check_rule_fields(_rule(pairs=[], not_computed={"fields": ["pairs"]}))
    check_rule_fields(
        _rule(pairs=[], not_computed={"fields": ["pairs"], "reason_zh": "x", "decision": "U0"})
    )


def test_old_rule_schema_is_refused():
    with pytest.raises(ValueError, match="mechanics-rules/2"):
        load_rules_v11({"schema": "mechanics-rules/1", "rules": []}, {})


def test_evaluation_carries_the_reason_and_matches_the_skipped_fields():
    entries = {r["id"]: r for r in _load(PACKAGE / "rules-evaluation.json")["rules"]}
    assert entries["R19"]["not_computed"]["decision"] == "U69"
    assert "not_computed" not in entries["R01"]
    rule = _rule(not_computed={"fields": ["pairs"], "reason_zh": "x", "decision": "U0"})
    with pytest.raises(ValueError, match="differ"):
        add_not_computed({"rules": [{"id": "RX", "not_evaluated": []}]}, [rule])


def test_v19_keeps_v18_edges_and_adds_no_condition_exceptions():
    old = _load(ROOT / "knowledge/mechanics/profiles/derived-v8/counter-graph.json")
    assert _load(DERIVED / "counter-graph.json")["item_to_hero"] == old["item_to_hero"]
    with pytest.raises(ValueError):
        build_reviewed({}, {"condition_exceptions": [{"subject": "x"}]})
