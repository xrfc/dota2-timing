"""MK-T5 v16: relation status as data, feedback resolved by identity, U101 rulings."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

from dota_items.data.mechanics_feedback import DISPUTED, SPOT_CHECK, feedback_id, resolve
from dota_items.data.mechanics_graph import build_graph
from dota_items.data.mechanics_graph_v2 import annotate_evaluation, annotate_graph, usable_edges
from dota_items.data.mechanics_interactions import evaluate_rule
from dota_items.data.mechanics_profiles_v2 import (
    hero_relations,
    item_relations,
    render_hero_relations,
    render_item_relations,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v16"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v6"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v6 as derived  # noqa: E402
import build_mechanics_facts_v16 as builder  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _doc():
    return _load(PACKAGE / "facts-v16.json")


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = _load(package / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def test_package_replays_facts_and_rule_evaluation(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, evaluation = builder.run(tmp_path / "v16")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_evaluation_replay_notices_a_broken_rule_engine(monkeypatch, tmp_path):
    def empty(rule, doc, fields=None):
        return {"sources": [], "targets": []}

    monkeypatch.setattr(builder, "evaluate_rule", empty)
    _, evaluation = builder.run(tmp_path / "v16")
    stored = _load(PACKAGE / "rules-evaluation.json")
    assert json.dumps(evaluation, sort_keys=True) != json.dumps(stored, sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = _load(tmp_path / "derived/manifest.json")["output_sha256"]
    assert fresh == _load(DERIVED / "manifest.json")["output_sha256"]
    profiles = _load(tmp_path / "derived/hero-profiles.json")
    assert profiles["relations"] == "candidate" and profiles["relation_verified"] is False
    assert "facts-v16.json" in profiles["sources"]["facts"]


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


# Feedback resolution -------------------------------------------------------


def _fb(verdict, at, note="n", claim=None):
    entry = {"review_id": "r", "verdict": verdict, "note": note, "at": at}
    return {**entry, "feedback_id": feedback_id(entry), "claim": claim}


ROW = {"review_id": "r", "mechanism": "stun", "decision": "accept", "basis": "two_ai"}
CLAIM = {"mechanism": "stun", "decision": "accept"}


def _fix(*wrongs, basis="user:U1"):
    return {"review_id": "r", "basis": basis, "resolves": [w["feedback_id"] for w in wrongs]}


def test_one_wrong_resolved_by_its_correction():
    wrong = _fb("wrong", "1")
    assert resolve(ROW, [wrong], [_fix(wrong)])[0] == "user:U1"


def test_old_correction_does_not_close_a_new_wrong():
    old, new = _fb("wrong", "1"), _fb("wrong", "2", note="again")
    basis, open_wrongs, _ = resolve(ROW, [old, new], [_fix(old)])
    assert basis == DISPUTED and open_wrongs == [new["feedback_id"]]


def test_partly_resolved_wrongs_stay_disputed():
    a, b, c = _fb("wrong", "1", "a"), _fb("wrong", "2", "b"), _fb("wrong", "3", "c")
    basis, open_wrongs, _ = resolve(ROW, [a, b, c], [_fix(a, b)])
    assert basis == DISPUTED and open_wrongs == [c["feedback_id"]]


def test_duplicate_import_changes_nothing():
    ok = _fb("ok", "1", claim=CLAIM)
    assert resolve(ROW, [ok], []) == resolve(ROW, [ok, dict(ok), dict(ok)], [])
    wrong = _fb("wrong", "2")
    assert resolve(ROW, [wrong, dict(wrong)], [_fix(wrong)])[0] == "user:U1"


def test_order_of_feedback_does_not_matter():
    old, new, ok = _fb("wrong", "1"), _fb("wrong", "3", "x"), _fb("ok", "2", claim=CLAIM)
    first = resolve(ROW, [old, ok, new], [_fix(old)])
    assert first == resolve(ROW, [new, old, ok], [_fix(old)])
    assert first[0] == DISPUTED


def test_ok_does_not_confirm_a_changed_fact():
    ok = _fb("ok", "1", claim={"mechanism": "stun", "decision": "reject"})
    assert resolve(ROW, [ok], [])[0] == "two_ai"
    assert resolve(ROW, [_fb("ok", "1", claim=CLAIM)], [])[0] == SPOT_CHECK
    assert resolve(ROW, [_fb("ok", "1")], [])[0] == "two_ai"


def test_user_ruling_kept_until_a_new_wrong():
    ruled = {**ROW, "basis": "user:U9"}
    assert resolve(ruled, [_fb("ok", "1", claim=CLAIM)], [])[0] == "user:U9"
    assert resolve(ruled, [_fb("wrong", "2")], [])[0] == DISPUTED


def test_real_feedback_resolution_matches_v15_and_keeps_history():
    doc = _doc()
    assert doc["feedback_changes"] == []
    assert not [r for r in doc["rows"] if r["basis"] == DISPUTED]
    rows = [r for r in doc["rows"] if r.get("feedback_status")]
    assert rows and all("basis_v15" in r["feedback_status"] for r in rows)
    resolutions = _load(ROOT / "knowledge/mechanics/reviews/feedback-resolutions-001.json")
    for correction in resolutions["corrections"]:
        assert len(correction["resolves"]) <= 1


# Relation status end to end --------------------------------------------------


def _toy():
    base = {"context": "base", "requires_scepter": False, "requires_shard": False}
    item = {"context": "item", "requires_scepter": False, "requires_shard": False}
    rows = [
        {
            "review_id": "1",
            "subject": "item_a",
            "mechanism": "m1",
            "condition": item,
            "decision": "accept",
            "basis": "user:U1",
            "quotes": ["q"],
            "condition_notes": [],
        },
        {
            "review_id": "2",
            "subject": "skill_a",
            "mechanism": "m2",
            "condition": base,
            "decision": "accept",
            "basis": "user:U1",
            "quotes": ["q"],
            "condition_notes": [],
        },
    ]
    doc = {"rows": rows, "skill_notes": [], "field_observations": []}
    rules = [
        {
            "id": "RX",
            "zh": "名称一",
            "relation": "counters",
            "source_mechanisms": ["m1"],
            "target_mechanisms": ["m2"],
            "decision": "U1",
            "pending": "等用户",
        }
    ]
    heroes = [
        {"hero_id": 1, "name_zh": "英雄", "abilities": [{"name": "skill_a", "name_zh": "技能"}]}
    ]
    nodes = {
        "skill_a": {"kind": "ability", "hero_id": 1, "hero_zh": "英雄", "name_zh": "技能"},
        "item_a": {"kind": "item", "name_zh": "装备"},
    }
    return doc, rules, heroes, nodes


def _chain(rules):
    doc, _, heroes, nodes = _toy()
    evaluation = annotate_evaluation(
        {"rules": [{"id": r["id"], "zh": r["zh"], **evaluate_rule(r, doc)} for r in rules]}, rules
    )
    graph = annotate_graph(build_graph(rules, evaluation, doc, nodes), rules, doc)
    hero = hero_relations(heroes[0], graph, {"item_a": "装备"})
    item = item_relations("item_a", graph)
    return evaluation, graph, hero, item


def test_one_pending_rule_has_the_same_status_everywhere():
    _, rules, _, _ = _toy()
    evaluation, graph, hero, item = _chain(rules)
    assert evaluation["rules"][0]["status"] == "pending"
    assert graph["rules"][0]["status"] == "pending"
    assert graph["item_to_hero"][0]["status"] == "pending"
    assert hero["targeted_by"][0]["status"] == "pending"
    assert hero["targeted_by"][0]["pending"] == "等用户"
    assert item["targeting"][0]["status"] == "pending"
    assert hero["targeted_by"][0]["relation_verified"] is False
    assert hero["targeted_by"][0]["own_facts_confirmed"] is True
    assert not usable_edges(graph)
    page = render_hero_relations(["# 英雄", "## 会被什么克制"], hero)
    assert "【待定】" in page and "候选机制关联" in page and "会被什么克制" not in page
    assert "【待定】" in render_item_relations(["# 装备", "## 能克制什么"], item)


def test_renaming_a_rule_does_not_change_its_status():
    _, rules, _, _ = _toy()
    renamed = [{**rules[0], "zh": "【已确认】完全不同的名字"}]
    _, graph, hero, item = _chain(renamed)
    assert hero["targeted_by"][0]["status"] == "pending"
    assert item["targeting"][0]["status"] == "pending"
    assert not usable_edges(graph)
    settled = [{k: v for k, v in rules[0].items() if k != "pending"}]
    _, graph, hero, _ = _chain(settled)
    assert hero["targeted_by"][0]["status"] == "candidate"
    assert usable_edges(graph)


def test_real_profiles_keep_status_fields():
    profiles = _load(DERIVED / "hero-profiles.json")
    entries = [e for p in profiles["profiles"] for e in p["candidate_relations"]["targeted_by"]]
    assert entries and all(
        {"rule", "relation", "status", "not_evaluated"} <= set(e) for e in entries
    )
    assert all(e["relation_verified"] is False for e in entries)
    marked = [e for e in entries if e.get("exception")]
    assert marked and {e["exception"]["condition"] for e in marked} == {"A杖"}
    page = (DERIVED / "heroes/hero-84.md").read_text(encoding="utf-8")
    assert "候选机制关联" in page and "会被什么克制" not in page and "A杖时例外" in page


# U101 -----------------------------------------------------------------------


def test_u101_rulings():
    doc = _doc()
    evaluation = {r["id"]: r for r in _load(PACKAGE / "rules-evaluation.json")["rules"]}
    assert "spectre_spectral_dagger" in evaluation["R13"]["targets"]
    assert "spectre_spectral_dagger" not in evaluation["R23"]["targets"]
    assert "necrolyte_death_seeker" in evaluation["R13"]["targets"]
    assert "necrolyte_death_seeker" not in evaluation["R23"]["targets"]
    for mechanism in ("ground_zone", "terrain_walk"):
        rows = _rows(doc, "spectre_spectral_dagger", mechanism)
        assert any(r["basis"] == "user:U101" and r["decision"] == "accept" for r in rows)
    rows = _rows(doc, "ember_spirit_sleight_of_fist", "invulnerable_untargetable")
    assert rows and rows[0]["basis"] == "user:U101"
