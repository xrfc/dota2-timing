"""MK-T5 v14: rulings v13 missed are written, and the rule evaluation itself is replayed."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_profiles import confirmed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v14"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v4"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v4 as derived  # noqa: E402
import build_mechanics_facts_v14 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v14.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v14")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v14")
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


def test_shadow_walk_stun_is_the_users_call_now():
    rows = _rows(_doc(), "bounty_hunter_wind_walk", "stun")
    assert rows and all(r["basis"] == "user:U97" and r["decision"] == "accept" for r in rows)
    assert confirmed(rows[0]["basis"])


@pytest.mark.parametrize(
    "subject,ref",
    [("dawnbreaker_solar_guardian", "user:U96"), ("dawnbreaker_fire_wreath", "user:U98")],
)
def test_explicit_exclusions_are_recorded(subject, ref):
    rows = _rows(_doc(), subject, "terrain_walk")
    assert rows and all(r["decision"] == "reject" and r["basis"] == ref for r in rows)


def test_v13_is_untouched_and_v14_builds_on_it():
    v13 = ROOT / "knowledge/mechanics/extractions/v13"
    _verify_receipt(v13)
    base = _load(v13 / "facts-v13.json")
    assert len(_doc()["rows"]) == len(base["rows"]) + 2
    assert _load(PACKAGE / "manifest.json")["input_sha256"][builder.BASE]


def test_new_marks_reach_rows():
    doc = _doc()
    assert doc["schema"] == "mechanics-facts/14"
    rows = _rows(doc, "harpoon", "self_mobility")
    assert rows and rows[0]["basis"] == "user_spot_check"
    assert not [r for r in doc["rows"] if r["basis"] == "disputed_by_user"]
