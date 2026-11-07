"""v22: rows the user added after the trait spot check, and rule R24 (U117)."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v22 import build_reviewed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v22"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v13"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v13 as derived  # noqa: E402
import build_mechanics_facts_v22 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v22.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v22")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v22")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v22.json" in profiles["sources"]["facts"]


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


from dota_items.data.mechanics_graph_v2 import hero_relations  # noqa: E402


def test_false_promise_now_counts_as_death_prevention():
    rows = _rows(_doc(), "oracle_false_promise", "death_prevention")
    assert len(rows) == 1 and rows[0]["basis"] == "user:U117"
    assert rows[0]["decision"] == "accept" and rows[0]["origin"] == "user_added"
    assert _rows(_doc(), "oracle_false_promise", "damage_block")


def test_culling_blade_counters_every_death_prevention():
    evaluation = {r["id"]: r for r in _load(PACKAGE / "rules-evaluation.json")["rules"]}
    r24 = evaluation["R24"]
    assert r24["sources"] == ["axe_culling_blade"]
    accepted = {
        r["subject"]
        for r in _doc()["rows"]
        if r["mechanism"] == "death_prevention" and r["decision"] == "accept"
    }
    assert set(r24["targets"]) == accepted and "oracle_false_promise" in accepted
    graph = _load(DERIVED / "counter-graph.json")
    assert "R24" in {f["rule"] for f in hero_relations(graph, 2, 111)}  # Axe on Oracle


def test_added_rows_are_checked():
    base = {
        "rows": [
            {
                "review_id": "r1",
                "subject": "x",
                "mechanism": "stun",
                "condition": {"context": "base"},
                "decision": "accept",
                "basis": "two_ai",
            }
        ],
        "counts": {},
    }
    spec = {
        "review_id": "r2",
        "subject": "x",
        "subject_zh": "x",
        "mechanism": "silence",
        "decision": "accept",
        "basis": "user:U0",
        "notes_zh": [],
        "quotes": [],
    }
    terms = {"stun": {}, "silence": {}}
    assert build_reviewed(base, {"added_rows": [spec]}, terms)["counts"]["rows"] == 2
    for bad, match in (
        ({**spec, "mechanism": "nope"}, "Unknown mechanism"),
        ({**spec, "subject": "y"}, "Unknown subject"),
        ({**spec, "basis": "two_ai"}, "user basis"),
        ({**spec, "mechanism": "stun"}, "already exists"),
    ):
        with pytest.raises(ValueError, match=match):
            build_reviewed(base, {"added_rows": [bad]}, terms)
