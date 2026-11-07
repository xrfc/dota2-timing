"""MK-T5 v13: conditions survive, feedback means what it said, edges say what they are."""

import ast
import builtins
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_facts_v13 import (
    BASIS_DISPUTED,
    apply_feedback,
    attach_condition_notes,
)
from dota_items.data.mechanics_graph_v2 import (
    STATUS_PENDING,
    annotate_evaluation,
    annotate_graph,
    display_doc,
    display_evaluation,
    hero_relations,
    usable_edges,
)
from dota_items.data.mechanics_profiles import confirmed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v13"
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v3"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v3 as derived  # noqa: E402
import build_mechanics_facts_v13 as builder  # noqa: E402


def _doc():
    return json.loads((PACKAGE / "facts-v13.json").read_text(encoding="utf-8"))


def _graph():
    return json.loads((DERIVED / "counter-graph.json").read_text(encoding="utf-8"))


def _rows(doc, subject, mechanism):
    return [r for r in doc["rows"] if r["subject"] == subject and r["mechanism"] == mechanism]


def _verify_receipt(package):
    manifest = json.loads((package / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected


def _traced_reads(monkeypatch, tmp_path, build):
    seen = set()
    real_open = builtins.open
    real_io_open = __import__("io").open

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
    build(tmp_path / "out")
    monkeypatch.setattr(builtins, "open", real_open)
    monkeypatch.setattr("io.open", real_io_open)
    return {name for name in seen if not name.endswith(".py")}


def test_package_matches_manifest_and_replays(tmp_path):
    _verify_receipt(PACKAGE)
    fresh, _ = builder.run(tmp_path / "v13")
    assert json.dumps(fresh, sort_keys=True) == json.dumps(_doc(), sort_keys=True)


def test_derived_replays_every_output_file(tmp_path):
    _verify_receipt(DERIVED)
    derived.run(tmp_path / "derived")
    fresh = json.loads((tmp_path / "derived/manifest.json").read_text())["output_sha256"]
    stored = json.loads((DERIVED / "manifest.json").read_text())["output_sha256"]
    assert fresh == stored


def _repo_imports(path, seen):
    """Repository files a Python file imports, followed all the way down."""
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


@pytest.mark.parametrize("module", [builder, derived])
def test_every_imported_repo_file_is_recorded(module):
    used = _repo_imports(Path(module.__file__), set())
    recorded = {ROOT / name for name in module.IMPLEMENTATION}
    assert used <= recorded, sorted(str(path) for path in used - recorded)


def test_deleted_input_counts_as_changed():
    assert builder._changed({"a": "1", "b": "2"}, {"a": "1"}) == ["b"]
    assert builder._changed({"a": "1"}, {"a": "1", "c": "3"}) == ["c"]
    assert builder._changed({"a": "1"}, {"a": "1"}) == []


def test_changing_implementation_during_the_build_stops_it(monkeypatch, tmp_path):
    name = builder.IMPLEMENTATION[0]
    monkeypatch.setitem(builder.IMPLEMENTATION_AT_IMPORT, name, "older")
    with pytest.raises(ValueError, match="Inputs changed"):
        builder.run(tmp_path / "v13")


def test_every_file_the_facts_build_reads_is_declared(monkeypatch, tmp_path):
    read = _traced_reads(monkeypatch, tmp_path, builder.run)
    assert read
    assert read <= set(builder.declared_inputs())
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    assert set(builder.declared_inputs()) == set(manifest["input_sha256"])


def test_every_file_the_derived_build_reads_is_declared(monkeypatch, tmp_path):
    read = _traced_reads(monkeypatch, tmp_path, derived.run)
    assert read
    assert read <= set(derived.INPUTS)


def test_changing_an_input_during_the_build_stops_it(monkeypatch, tmp_path):
    real = builder.digest_inputs
    calls = {"count": 0}

    def drifting(repo=builder.ROOT):
        result = dict(real(repo))
        calls["count"] += 1
        if calls["count"] > 1:
            result[builder.REGISTRY] = "changed"
        return result

    monkeypatch.setattr(builder, "digest_inputs", drifting)
    with pytest.raises(ValueError, match="hero-registry"):
        builder.run(tmp_path / "v13")


def test_condition_notes_survive_and_absence_is_not_unconditional():
    doc = _doc()
    rows = _rows(doc, "night_stalker_void", "stun")
    assert any("夜" in note["text"] for row in rows for note in row["condition_notes"])
    assert all(row["condition_review"] in {"ai_note", "none"} for row in doc["rows"])
    assert any(row["condition_review"] == "none" for row in doc["rows"])
    assert "不能用于自动推理" in doc["condition_policy"]


def test_condition_note_reaches_the_hero_page():
    page = (DERIVED / "heroes/hero-60.md").read_text(encoding="utf-8")
    line = next(text for text in page.splitlines() if text.startswith("- 眩晕"))
    assert "夜" in line


def _row(review_id, basis="two_ai", decision="accept"):
    return {"review_id": review_id, "basis": basis, "decision": decision, "notes_zh": []}


def test_wrong_feedback_disputes_a_row_and_does_not_confirm_it():
    rows = [_row("a"), _row("b", "user_spot_check"), _row("c", "user:U1"), _row("d", "field:x")]
    feedback = [{"review_id": key, "verdict": "wrong", "note": "n"} for key in "abcd"]
    assert apply_feedback(rows, feedback, []) == []
    assert [row["basis"] for row in rows] == [BASIS_DISPUTED] * 4
    assert not confirmed(rows[0]["basis"])
    assert rows[0]["decision"] == "accept"
    assert rows[0]["user_feedback"][0]["note"] == "n"


def test_ok_confirms_unsure_does_not_and_lost_rows_are_returned():
    rows = [_row("a"), _row("b")]
    feedback = [
        {"review_id": "a", "verdict": "ok", "note": ""},
        {"review_id": "b", "verdict": "unsure", "note": "n"},
        {"review_id": "gone", "verdict": "wrong", "note": "n"},
    ]
    assert apply_feedback(rows, feedback, []) == [feedback[2]]
    assert rows[0]["basis"] == "user_spot_check"
    assert rows[1]["basis"] == "two_ai"


def test_correction_resolves_a_dispute():
    rows = [_row("a")]
    feedback = [{"review_id": "a", "verdict": "wrong", "note": "n"}]
    corrections = [{"review_id": "a", "basis": "user_corrected:U5", "note_zh": "改了"}]
    apply_feedback(rows, feedback, corrections)
    assert rows[0]["basis"] == "user_corrected:U5"
    assert confirmed(rows[0]["basis"])


def test_old_wrong_feedback_kept_on_rows_or_in_the_unattached_list():
    doc = _doc()
    lever = _rows(doc, "tidehunter_leviathans_catch", "damage_block")[0]
    assert lever["basis"] == "user_corrected:U5"
    assert lever["user_feedback"][0]["note"] == "吃鱼会获得伤害格挡"
    holy = {r["condition"]["item_ability_type"]: r for r in _rows(doc, "holy_locket", "healing")}
    assert holy["active"]["basis"] == "user_corrected:U5"
    assert holy["passive"]["basis"] == "two_ai"
    assert holy["passive"]["user_feedback"][0]["verdict"] == "wrong"
    notes = [entry["note"] for entry in doc["unattached_feedback"]]
    assert "这个东西是在哪读出来的？？是7.41f吗" in notes
    disputed = {(r["subject"], r["mechanism"]) for r in doc["rows"] if r["basis"] == BASIS_DISPUTED}
    assert disputed == set()


def test_attach_condition_notes_keeps_each_reviewer():
    rows = [_row("a"), _row("b")]
    reviews = [
        {"review_id": "a", "condition_zh": "仅夜晚", "round": 7, "reviewer": "codex"},
        {"review_id": "a", "conditions_zh": "夜晚", "round": 2, "reviewer": "codex"},
    ]
    attach_condition_notes(rows, reviews)
    assert [note["round"] for note in rows[0]["condition_notes"]] == [7, 2]
    assert rows[0]["condition_review"] == "ai_note"
    assert rows[1]["condition_review"] == "none"


def test_edges_carry_relation_and_status():
    graph = _graph()
    assert graph["schema"] == "mechanics-counter-graph/2"
    assert "候选" in graph["semantics"]
    rules = json.loads((ROOT / "knowledge/mechanics/rules-v7.json").read_text(encoding="utf-8"))
    by_id = {rule["id"]: rule for rule in rules["rules"]}
    for edge in graph["item_to_hero"]:
        assert edge["relation"] == by_id[edge["rule"]]["relation"]
        assert (edge["status"] == STATUS_PENDING) == bool(by_id[edge["rule"]].get("pending"))
    assert any(edge["status"] == STATUS_PENDING for edge in graph["item_to_hero"])


def test_pending_edges_need_an_explicit_request():
    graph = _graph()
    assert not any(edge["status"] == STATUS_PENDING for edge in usable_edges(graph))
    assert any(
        edge["status"] == STATUS_PENDING for edge in usable_edges(graph, include_pending=True)
    )
    assert all(edge["confirmed"] for edge in usable_edges(graph, confirmed_only=True))
    with pytest.raises(ValueError):
        usable_edges({"schema": "mechanics-counter-graph/1", "item_to_hero": []})


def test_pending_rules_are_labelled_on_pages():
    page = (DERIVED / "heroes/hero-1.md").read_text(encoding="utf-8")
    assert "【待定】R13" not in page
    assert "R13 【待定】" in page


def test_unevaluated_rule_fields_are_reported():
    evaluation = json.loads((PACKAGE / "rules-evaluation.json").read_text(encoding="utf-8"))
    by_id = {rule["id"]: rule for rule in evaluation["rules"]}
    assert by_id["R19"]["not_evaluated"] == ["pairs"]
    assert by_id["R09"]["not_evaluated"] == ["target_exempt_mechanisms"]
    graph = annotate_graph({"rules": [], "item_to_hero": []}, [], {"rows": []})
    assert graph["item_to_hero"] == []


def test_bear_skills_sit_under_lone_druid():
    doc = _doc()
    assert all(r["decision"] == "reject" for r in _rows(doc, "lone_druid_spirit_bear", "root"))
    entangle = _rows(doc, "lone_druid_spirit_bear_entangle", "root")
    assert entangle[0]["decision"] == "accept"
    assert entangle[0]["basis"] == "user:U90"
    page = (DERIVED / "heroes/hero-80.md").read_text(encoding="utf-8")
    assert "熊灵·缠绕之爪" in page
    assert "熊灵·回归" in page


def test_v12_package_is_untouched_by_this_version():
    v12 = ROOT / "knowledge/mechanics/extractions/v12"
    _verify_receipt(v12)


def test_condition_notes_stay_with_their_own_row():
    graph = _graph()
    rule = next(r for r in graph["rules"] if r["id"] == "R20")
    entry = next(s for s in rule["sources"] if s["subject"] == "dazzle_shadow_wave")
    by_condition = {item["condition"]: item["condition_notes"] for item in entry["evidence"]}
    assert all("A杖" not in text for text in by_condition[""])
    assert all("A杖" in text for text in by_condition["A杖"])


def test_hero_relations_hide_pending_rules_unless_asked():
    graph = _graph()
    hidden = hero_relations(graph, 1, 1)
    shown = hero_relations(graph, 1, 1, include_pending=True)
    assert not any(item["rule"] == "R13" for item in hidden)
    pending = [item for item in shown if item["rule"] == "R13"]
    assert pending and pending[0]["status"] == STATUS_PENDING and pending[0]["relation"] == "blocks"
    with pytest.raises(ValueError):
        hero_relations({"schema": "mechanics-counter-graph/1", "rules": []}, 1, 1)


def test_display_functions_add_what_pages_show():
    rule = {"id": "R1", "relation": "blocks", "pending": "x"}
    evaluation = annotate_evaluation(
        {"rules": [{"id": "R1", "zh": "规则", "sources": [], "targets": []}]}, [rule]
    )
    assert display_evaluation(evaluation)["rules"][0]["zh"] == "【待定】规则"
    row = {
        "notes_zh": ["旧"],
        "condition_notes": [{"text": "仅夜晚生效", "round": 7, "reviewer": "codex"}],
    }
    shown = display_doc({"rows": [row]})["rows"][0]["notes_zh"]
    assert shown == ["AI说明条件：仅夜晚生效", "旧"]


def _accepted(doc, subject, mechanism):
    return any(r["decision"] == "accept" for r in _rows(doc, subject, mechanism))


def test_slow_means_move_speed_and_attack_slow_is_separate():
    doc = _doc()
    assert not _accepted(doc, "viper_corrosive_skin", "slow")
    rows = _rows(doc, "viper_corrosive_skin", "attack_slow")
    assert any(r["basis"] == "user:U93" and r.get("renamed_from") == "slow" for r in rows)
    assert _accepted(doc, "phoenix_fire_spirits", "attack_slow")
    assert not _accepted(doc, "phoenix_fire_spirits", "slow")
    both = [
        r for r in doc["rows"] if r["mechanism"] == "attack_slow" and r["origin"] == "control_audit"
    ]
    assert len(both) == 20
    assert all(_accepted(doc, r["subject"], "slow") for r in both)
    assert all(r["basis"] == "two_ai" for r in both)


def test_resistance_rules_are_split():
    rules = json.loads((ROOT / "knowledge/mechanics/rules-v7.json").read_text(encoding="utf-8"))
    by_id = {rule["id"]: rule for rule in rules["rules"]}
    assert by_id["R11"]["source_mechanisms"] == ["status_resistance"]
    assert "attack_slow" in by_id["R11"]["target_mechanisms"]
    assert by_id["R21"]["source_mechanisms"] == ["slow_resistance"]
    assert by_id["R21"]["target_mechanisms"] == ["slow"]


def test_hypnotize_rulings():
    doc = _doc()
    assert not _accepted(doc, "keeper_of_the_light_will_o_wisp", "displace_other")
    assert not _accepted(doc, "void_spirit_aether_remnant", "displace_other")
    assert _accepted(doc, "ringmaster_wheel", "displace_other")


def test_marked_wrong_rows_follow_the_user_ruling():
    doc = _doc()
    rows = _rows(doc, "treant_overgrowth", "aoe_damage")
    assert any(r["decision"] == "reject" and r["basis"] == "user:U93" for r in rows)
    assert any(r["decision"] == "accept" and r["basis"] == "user_spot_check" for r in rows)
    assert _accepted(doc, "treant_overgrowth", "cleave")
    for mechanism in ("silence", "mute", "disarm"):
        assert not _accepted(doc, "ringmaster_the_box", mechanism)
    assert not _accepted(doc, "doom_bringer_devour", "spell_amp")


def test_spot_check_page_uses_current_definitions():
    page = (ROOT / "knowledge/mechanics/reviews/u5-spot-check-002/page.html").read_text(
        encoding="utf-8"
    )
    data = json.loads(page.split("const DATA = ", 1)[1].split(";\nconst WHY_ORDER", 1)[0])
    vocabulary = json.loads(
        (ROOT / "knowledge/mechanics/vocabulary-v13.json").read_text(encoding="utf-8")
    )
    terms = {term["id"]: term for term in vocabulary["mechanisms"]}
    for row in data["rows"]:
        assert data["defs"][row["m"]] == terms[row["m"]]["definition"]
        assert row["mz"] == terms[row["m"]]["zh"]
    assert "flying" not in data["defs"]
    assert not any(row["n"] == "冥界亚龙·腐蚀皮肤" and row["m"] == "slow" for row in data["rows"])


def test_flying_became_terrain_walk_and_left_the_vocabulary():
    doc = _doc()
    vocabulary = json.loads((ROOT / doc["vocabulary"]).read_text(encoding="utf-8"))
    terms = {m["id"] for m in vocabulary["mechanisms"]}
    assert "flying" not in terms
    assert {r["mechanism"] for r in doc["rows"]} <= terms
    assert any(r["mechanism"] == "flying" for r in doc["retired_term_rows"])
    assert not any(r["mechanism"] == "flying" for r in doc["rows"])


@pytest.mark.parametrize(
    "subject",
    [
        "night_stalker_darkness",
        "spectre_spectral_dagger",
        "broodmother_spin_web",
        "mirana_leap",
        "magnataur_skewer",
        "dawnbreaker_celestial_hammer",
        "sniper_concussive_grenade",
        "wind_waker",
        "spectre_haunt",
    ],
)
def test_terrain_walk_rows(subject):
    assert _accepted(_doc(), subject, "terrain_walk")


@pytest.mark.parametrize(
    "subject", ["dawnbreaker_solar_guardian", "antimage_blink", "pangolier_gyroshell", "tiny_toss"]
)
def test_not_terrain_walk(subject):
    assert not _accepted(_doc(), subject, "terrain_walk")


def test_high_ground_vision_rulings():
    doc = _doc()
    for subject in ("night_stalker_darkness", "zuus_lightning_bolt", "puck_illusory_orb"):
        assert _accepted(doc, subject, "high_ground_vision")
    for subject in ("storm_spirit_static_remnant", "drow_ranger_glacier"):
        rows = _rows(doc, subject, "high_ground_vision")
        assert rows and all(r["decision"] == "reject" for r in rows)


def test_cooldown_reduction_means_other_abilities():
    doc = _doc()
    for subject in ("invoker_invoke", "nevermore_shadowraze1", "tusk_walrus_kick"):
        assert not _accepted(doc, subject, "cooldown_reduction")
    assert _accepted(doc, "octarine_core", "cooldown_reduction")


def test_force_fields_are_zones_and_terrain_rule_exists():
    doc = _doc()
    for subject in ("disruptor_kinetic_field", "disruptor_kinetic_fence", "mars_arena_of_blood"):
        assert not _accepted(doc, subject, "terrain")
        assert _accepted(doc, subject, "ground_zone")
    assert _accepted(doc, "disruptor_kinetic_field", "slow")
    assert _accepted(doc, "mars_arena_of_blood", "slow")
    assert _accepted(doc, "earthshaker_fissure", "terrain")
    evaluation = json.loads((PACKAGE / "rules-evaluation.json").read_text(encoding="utf-8"))
    rule = next(r for r in evaluation["rules"] if r["id"] == "R22")
    assert "earthshaker_fissure" in rule["targets"]
    assert "disruptor_kinetic_field" not in rule["targets"]
