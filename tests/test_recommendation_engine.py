"""Behavioral and integrity cases; not independent recommendation-quality evidence."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dota_items.recommendation.contracts import LineupRequest
from dota_items.recommendation.engine import recommend
from dota_items.recommendation.files import load_bundle
from dota_items.recommendation.knowledge import Bundle
from dota_items.recommendation.report import render_html, render_text

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "knowledge/recommendation/7.41f-v1"
CASES = ROOT / "examples/recommendation"


@pytest.fixture(scope="module")
def bundle():
    return load_bundle(PACK)


def request(name="baseline"):
    return LineupRequest.model_validate_json((CASES / f"{name}.json").read_bytes())


def candidate_map(result):
    return {c.item_key: c for c in result.recommendation.candidates}


def test_offline_pack_has_one_supported_profile_and_full_identity_catalog(bundle):
    assert [(p.hero_id, p.role) for p in bundle.policy.profiles] == [(8, 1)]
    assert len(bundle.knowledge.heroes) == 127
    assert bundle.knowledge.binding.method == "official_current_crosscheck"
    result = recommend(request(), bundle)
    assert result.recommendation.status == "supported"
    candidates = candidate_map(result)
    assert {"manta", "monkey_king_bar", "skadi", "power_treads"} <= candidates.keys()
    assert not {"black_king_bar", "butterfly"} & candidates.keys()
    assert len(result.exclusions) >= 2


def test_enemy_substitution_changes_related_need_and_candidate_only(bundle):
    baseline = recommend(request(), bundle)
    changed = recommend(request("no-evasion"), bundle)
    assert "accuracy" in {n.need_key for n in baseline.needs}
    assert "accuracy" not in {n.need_key for n in changed.needs}
    assert "monkey_king_bar" not in candidate_map(changed)
    assert candidate_map(baseline)["manta"] == candidate_map(changed)["manta"]


def test_illusions_change_farming_choice_without_prescribing_both(bundle):
    result = recommend(request("illusions"), bundle)
    candidates = candidate_map(result)
    assert "waveclear" in {n.need_key for n in result.needs}
    assert "dispel" not in {n.need_key for n in result.needs}
    assert candidates["bfury"].category == "alternative"
    assert candidates["maelstrom"].category == "situational"
    assert any("选择组而非连购清单" in text for text in candidates["bfury"].conditions)


def test_ally_control_is_potential_not_removal_of_own_needs(bundle):
    payload = request().model_dump()
    payload.update(radiant=[8, 12, 39, 5, 50], dire=[6, 44, 2, 25, 27])
    before = recommend(LineupRequest.model_validate(payload), bundle)
    payload["radiant"][1] = 26
    after = recommend(LineupRequest.model_validate(payload), bundle)
    assert "ally-setup" not in {n.need_key for n in before.needs}
    assert "ally-setup" in {n.need_key for n in after.needs}
    assert "blink" not in candidate_map(before)
    assert "blink" in candidate_map(after)
    assert candidate_map(before)["manta"] == candidate_map(after)["manta"]


def test_known_hero_with_no_mechanism_stays_unknown(bundle):
    result = recommend(request("unknown-hero-knowledge"), bundle).recommendation
    assert result.status == "partial"
    assert next(c for c in result.coverage if c.hero_id == 74).status == "unknown"
    assert any("未知" in limit for limit in result.limitations)


@pytest.mark.parametrize("case", ["unsupported-role", "unsupported-target"])
def test_valid_but_unsupported_scope_never_falls_back(case, bundle):
    result = recommend(request(case), bundle).recommendation
    assert result.status == "unsupported"
    assert not result.candidates
    assert "不会自动改成" in result.empty_reason


def test_scope_extensions_are_data_driven_and_melee_constraints_still_apply(bundle):
    # Test-only policy, not a release of support for role 5 Drow Ranger.
    payload = bundle.model_dump()
    profile = payload["policy"]["profiles"][0]
    profile.update(hero_id=6, role=5, required_fact_ids=["drow_ranger_wave_of_silence-silence"])
    next(r for r in payload["policy"]["need_rules"] if r["need_key"] == "growth")["tag"] = "silence"
    test_bundle = Bundle.model_validate(payload)
    test_request = request().model_dump()
    test_request.update(target_team="dire", target_hero_id=6, role=5)
    result = recommend(LineupRequest.model_validate(test_request), test_bundle)
    assert result.recommendation.candidates
    assert "bfury" not in candidate_map(result)
    assert any(e.item_key == "bfury" and "近战" in e.reason for e in result.exclusions)
    assert bundle.policy.profiles[0].hero_id == 8


@pytest.mark.parametrize("state", ["unknown", "conflict"])
def test_missing_or_conflicting_required_target_fact_fails_closed(bundle, state):
    payload = bundle.model_dump()
    next(
        f for f in payload["knowledge"]["facts"] if f["fact_id"] == "juggernaut_blade_dance-attack"
    )["status"] = state
    result = recommend(request(), Bundle.model_validate(payload)).recommendation
    assert result.status == "unsupported"
    assert not result.candidates


def test_conflict_blocks_enemy_claims_and_item_fact_blocks_candidate(bundle):
    payload = bundle.model_dump()
    for fact in payload["knowledge"]["facts"]:
        if fact["hero_id"] == 44 or fact["item_key"] == "manta":
            fact["status"] = "conflict"
    result = recommend(request(), Bundle.model_validate(payload))
    assert result.recommendation.status == "partial"
    assert not {"monkey_king_bar", "manta"} & candidate_map(result).keys()
    assert next(c for c in result.recommendation.coverage if c.hero_id == 44).status == "conflict"


def test_no_candidates_is_an_explained_result_not_an_exception(bundle):
    payload = bundle.model_dump()
    for item in payload["knowledge"]["items"]:
        item.update(enabled=False, held_reason="Held in test")
    result = recommend(request(), Bundle.model_validate(payload))
    assert result.recommendation.candidates == ()
    assert result.recommendation.empty_reason
    assert len(result.exclusions) == len(bundle.knowledge.items)


def test_output_is_invariant_to_lineup_and_storage_order(bundle):
    expected = recommend(request(), bundle)
    payload = request().model_dump()
    payload["radiant"] = tuple(reversed(payload["radiant"]))
    payload["dire"] = tuple(reversed(payload["dire"]))
    changed = bundle.model_dump()
    for key in ("facts", "items", "heroes", "sources"):
        changed["knowledge"][key] = tuple(reversed(changed["knowledge"][key]))
    for key in ("need_rules", "item_rules"):
        changed["policy"][key] = tuple(reversed(changed["policy"][key]))
    assert (
        recommend(LineupRequest.model_validate(payload), Bundle.model_validate(changed)) == expected
    )


@pytest.fixture
def pack_copy(tmp_path):
    return Path(shutil.copytree(PACK, tmp_path / "pack"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_source_tamper_and_unresolved_quote_are_rejected(pack_copy):
    path = pack_copy / "sources/hero-8.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_bundle(pack_copy)
    kb_path = pack_copy / "knowledge.json"
    kb = json.loads(kb_path.read_text())
    next(s for s in kb["sources"] if s["source_id"] == "hero-8")["sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    kb["facts"][0]["quote"] = "This quote never appeared in the snapshot."
    write_json(kb_path, kb)
    with pytest.raises(ValueError, match="quote mismatch"):
        load_bundle(pack_copy)


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("anchor", "anchor mismatch"),
        ("patch", "patch identity"),
        ("traversal", "Invalid relative"),
        ("catalog", "catalog identity"),
        ("owner", "identity mismatch"),
        ("unknown_reference", "unknown item or need"),
    ],
)
def test_knowledge_inconsistencies_are_not_silent_fallbacks(pack_copy, mutation, match):
    kb_path, policy_path = pack_copy / "knowledge.json", pack_copy / "policy.json"
    kb = json.loads(kb_path.read_text())
    if mutation == "anchor":
        kb["binding"]["anchors"][0]["expected"] = -99
    elif mutation == "patch":
        source = pack_copy / "sources/patch-notes.json"
        data = json.loads(source.read_text())
        data["patch_number"] = "7.41e"
        write_json(source, data)
        next(s for s in kb["sources"] if s["source_id"] == "patch-notes")["sha256"] = (
            hashlib.sha256(source.read_bytes()).hexdigest()
        )
    elif mutation == "traversal":
        kb["sources"][0]["file"] = "../outside.json"
    elif mutation == "catalog":
        kb["heroes"][0]["attack_type"] = "Ranged"
    elif mutation == "owner":
        kb["facts"][0]["hero_id"] = 6
    else:
        policy = json.loads(policy_path.read_text())
        policy["item_rules"][0]["need_key"] = "not-a-need"
        write_json(policy_path, policy)
    write_json(kb_path, kb)
    with pytest.raises(ValueError, match=match):
        load_bundle(pack_copy)


def test_rendering_escapes_markup_and_contains_trace_not_new_scores(bundle):
    result = recommend(request(), bundle)
    payload = bundle.model_dump()
    next(h for h in payload["knowledge"]["heroes"] if h["hero_id"] == 8)["name"] = (
        '<script>alert("x")</script>'
    )
    html = render_html(result, Bundle.model_validate(payload))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    text = render_text(result, bundle)
    assert result.recommendation.input_fingerprint in text
    assert "规则分 8" in text and "不是概率" in text
    assert "黑皇杖" in text and "暂不启用" in text


@pytest.mark.parametrize(
    "case,exit_code,status",
    [
        ("baseline", 0, "supported"),
        ("unknown-hero-knowledge", 0, "partial"),
        ("unsupported-role", 3, "unsupported"),
        ("unsupported-target", 3, "unsupported"),
    ],
)
def test_cli_result_and_scope_exit_codes(case, exit_code, status):
    result = subprocess.run(
        [sys.executable, str(ROOT / "recommend.py"), str(CASES / f"{case}.json")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == exit_code, result.stderr
    assert json.loads(result.stdout)["recommendation"]["status"] == status


def test_cli_invalid_input_and_output_collision(tmp_path):
    source = tmp_path / "lineup.json"
    payload = request().model_dump(mode="json")
    payload["role"] = True
    write_json(source, payload)
    cmd = [sys.executable, str(ROOT / "recommend.py"), str(source)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "invalid_input"
    write_json(source, request().model_dump(mode="json"))
    before = source.read_bytes()
    result = subprocess.run(
        [*cmd, "--output", str(source)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 2
    assert source.read_bytes() == before
    output = tmp_path / "report.html"
    result = subprocess.run(
        [*cmd, "--format", "html", "--output", str(output)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_full_path_does_not_import_replays_or_use_network():
    code = """
import builtins, socket
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('gem', 'dota_items.sources', 'dota_items.workflow',
                        'dota_items.data', 'knowledge', 'learning', 'torch', 'sklearn',
                        'httpx', 'urllib.request')):
        raise AssertionError(f'Forbidden dependency: {name}')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
def blocked(*args, **kwargs):
    raise AssertionError('Network unavailable')
socket.create_connection = blocked
from dota_items.recommendation.cli import main
assert main(['examples/recommendation/baseline.json', '--knowledge',
             'knowledge/recommendation/7.41f-v1']) == 0
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def test_required_target_reference_cannot_be_borrowed_from_another_hero(bundle):
    payload = bundle.model_dump()
    payload["policy"]["profiles"][0]["required_fact_ids"] = ["drow_ranger_wave_of_silence-silence"]
    with pytest.raises(ValueError, match="belong to target hero"):
        Bundle.model_validate(payload)


def test_two_roles_can_select_different_policies_without_cross_contamination(bundle):
    # A test-only second role demonstrates extensibility, not production support.
    payload = bundle.model_dump(mode="json")
    profile = json.loads(json.dumps(payload["policy"]["profiles"][0]))
    profile["role"] = 2
    profile["item_rule_ids"] = ["test-other-role"]
    payload["policy"]["profiles"].append(profile)
    rule = dict(payload["policy"]["item_rules"][0])
    rule.update(rule_id="test-other-role", weight=100.0)
    payload["policy"]["item_rules"].append(rule)
    extended = Bundle.model_validate(payload)
    assert candidate_map(recommend(request(), extended)) == candidate_map(
        recommend(request(), bundle)
    )
    other = recommend(request("unsupported-role"), extended)
    assert list(candidate_map(other)) == [rule["item_key"]]
    assert sum(c.value for c in other.recommendation.candidates[0].score_components) == 100
