"""MK-T3 provenance, conditional attribution and known semantic regressions."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from dota_items.data import mechanics_facts as mf
from dota_items.data.mechanics_rules import text_hits

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sources():
    return {
        name: json.loads((ROOT / name).read_text())
        if name.endswith(".json")
        else {"text": (ROOT / name).read_text()}
        for name in mf.INPUTS
    }


@pytest.fixture(scope="module")
def facts(sources):
    return mf.build_facts(sources)


def rows(doc, subject, mechanism):
    return [f for f in doc["facts"] if f["subject"] == subject and f["mechanism"] == mechanism]


@pytest.mark.parametrize(
    "text",
    [
        "Move towards the enemy and forward.",
        "AbilityCharges AbilityManaCost mana charge warding.",
        "破坏性的冰爆，破坏树木。",
        "Does not stun the target.",
        "Does not break invisibility.",
    ],
)
def test_false_positive_regressions(text):
    assert list(text_hits(text)) == []


@pytest.mark.parametrize(
    ("text", "present", "absent"),
    [
        (
            "Applies a strong dispel at the end of the spin.",
            "applies_strong_dispel",
            "applies_basic_dispel",
        ),
        ("Attacks pierce through evasion.", "pierce_evasion", "evasion"),
        ("Pierces Debuff Immunity.", "pierces_debuff_immunity", "debuff_immunity"),
        ("The target cannot die.", "death_prevention", "stun"),
        ("Attacks cannot miss.", "pierce_evasion", "blind"),
        ("Disables their passive abilities.", "applies_break", "break_sensitive"),
        ("破坏会使被动失效。", "break_sensitive", "applies_break"),
    ],
)
def test_text_context_and_polarity(text, present, absent):
    found = {mid for mid, _ in text_hits(text)}
    assert present in found
    assert absent not in found


def test_real_inputs_full_inventory_and_quotes(sources, facts):
    checked = mf.load_facts(facts, sources)
    assert (
        len({s["subject"] for s in facts["subjects"] if s["subject_type"] == "hero_ability"}) == 734
    )
    assert len([s for s in facts["subjects"] if s["subject_type"] == "item"]) == 209
    assert {s["hero"] for s in facts["subjects"] if s["subject_type"] == "hero_ability"} == {
        h["npc_name"] for h in sources[mf.HEROES]["heroes"]
    }
    assert len({f["fact_id"] for f in checked}) == len(checked)
    assert all(
        f["review"] == "needs_review" for f in checked if f["evidence_kind"] == "official_text"
    )
    assert all(f["assertion"] == "field_observation" for f in checked if f["review"] == "auto")
    # Byte-correct quotations are verified for every real row, not only samples.
    for f in checked:
        value = mf.pointer(sources[f["pointer"]["file"]], f["pointer"]["path"])
        if f["quote_encoding"] == "text":
            assert f["quote"] in value
        else:
            assert f["quote"] == mf.canonical(value)


def test_known_gameplay_distinctions(facts):
    assert rows(facts, "juggernaut_blade_fury", "applies_strong_dispel")
    assert rows(facts, "largo_catchy_lick", "applies_basic_dispel")
    assert rows(facts, "largo_catchy_lick", "displace_other")
    assert not rows(facts, "largo_catchy_lick", "self_mobility")
    assert rows(facts, "largo_catchy_lick", "effect_dispellability")[0]["value"] == 0
    assert rows(facts, "ursa_enrage", "status_resistance")
    assert not rows(facts, "ursa_enrage", "debuff_immunity")
    assert not rows(facts, "clinkz_strafe", "blind")
    assert rows(facts, "lion_mana_drain", "mana_gain")
    assert rows(facts, "silver_edge", "applies_break")
    assert rows(facts, "monkey_king_bar", "pierce_evasion")
    assert not rows(facts, "monkey_king_bar", "blind")
    for name in [
        "omniknight_guardian_angel",
        "oracle_false_promise",
        "templar_assassin_refraction",
    ]:
        assert rows(facts, name, "effect_dispellability")[0]["value"] == 3
    passive = rows(facts, "tidehunter_kraken_shell", "break_sensitive")
    assert passive and all(f["evidence_kind"] == "manual" for f in passive)
    for mid, expected in [("status_resistance", "16"), ("slow_resistance", "30")]:
        attrs = rows(facts, "sange_and_yasha", mid)
        assert any(
            f["value"] == expected and f["evidence_kind"] == "item_attr:" + mid for f in attrs
        )


def test_upgrade_conditions_are_not_base_capabilities(facts, sources):
    upgrades = [f for f in facts["facts"] if "/upgrade_text/" in f["pointer"]["path"]]
    assert upgrades
    for f in upgrades:
        upgrade = "scepter" if "/scepter_loc/" in f["pointer"]["path"] else "shard"
        assert f["condition"]["requires_" + upgrade] is True
        assert f["condition"]["context"] == upgrade + "_upgrade"
    for subject in facts["subjects"]:
        if subject["subject_type"] != "hero_ability":
            continue
        ability = mf.pointer(sources[mf.HEROES], subject["pointer"])
        for kind in ["scepter", "shard"]:
            if ability["granted_by_" + kind]:
                assert all(
                    f["condition"]["requires_" + kind]
                    for f in facts["facts"]
                    if f["subject"] == subject["subject"]
                )


@pytest.mark.parametrize(
    "change",
    [
        "quote",
        "value",
        "subject",
        "mechanism",
        "review",
        "condition",
        "missing",
        "duplicate",
        "hash",
        "patch",
        "source",
        "publisher",
    ],
)
def test_tampering_fails_closed(sources, facts, change):
    doc = copy.deepcopy(facts)
    f = next(f for f in doc["facts"] if f["quote_encoding"] == "text")
    if change == "quote":
        f["quote"] = "THIS IS NOT IN THE SOURCE"
    elif change == "value":
        f["value"] = "forged"
    elif change == "subject":
        f["subject"] = "other_hero"
    elif change == "mechanism":
        f["mechanism"] = "invented"
    elif change == "review":
        f["review"] = "auto"
    elif change == "condition":
        f["condition"]["requires_scepter"] = not f["condition"]["requires_scepter"]
    elif change == "missing":
        doc["facts"].pop()
    elif change == "duplicate":
        doc["facts"].append(copy.deepcopy(f))
    elif change == "hash":
        doc["source_hashes"][mf.HEROES] = "0" * 64
    elif change == "patch":
        doc["patch_verified"] = True
    elif change == "source":
        f["pointer"]["file"] = "../../unknown.json"
    elif change == "publisher":
        f["publisher"] = "invented"
    with pytest.raises(ValueError):
        mf.load_facts(doc, sources)


def test_changed_source_and_unconfirmed_enum_rejected(sources, facts):
    changed = copy.deepcopy(sources)
    changed[mf.HEROES]["heroes"][0]["abilities"][0]["description_en"] += " changed"
    with pytest.raises(ValueError, match="hash"):
        mf.load_facts(facts, changed)
    changed = copy.deepcopy(sources)
    changed[mf.ENUMS]["fields"]["damage"]["values"]["1"]["confirmed"] = False
    with pytest.raises(ValueError, match="confirmed"):
        mf.build_facts(changed)


def test_pointer_escape_and_invalid_indices():
    assert mf.pointer({"a/b": {"~": [3]}}, "/a~1b/~0/0") == 3
    for path in ["/x", "/a/-1", "/a/01", "/a/2", "a/0"]:
        with pytest.raises(ValueError):
            mf.pointer({"a": [1]}, path)


def test_coverage_reports_unknowns_and_every_term(sources, facts):
    terms = {m["id"]: m for m in sources[mf.VOCAB]["mechanisms"]}
    report = mf.coverage(facts, terms)
    assert len(report["mechanisms"]) == 45
    assert "branches" in report["subjects_without_facts"]
    assert report["patch_verified"] is False
    assert "belt_of_strength" in report["subjects_without_text"]


def test_builder_reproducibility_review_queue_and_no_overwrite(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "build_facts_cli", ROOT / "scripts/build_mechanics_facts.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    out = tmp_path / "first"
    report = script.run(out)
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(ValueError, match="already exists"):
        script.run(out)
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}
    second = tmp_path / "second"
    script.run(second)
    assert before == {p.name: p.read_bytes() for p in second.iterdir()}
    assert report["sample_groups"] == (report["review_groups"] + 2) // 3


@pytest.mark.parametrize(
    "text",
    [
        "获得减益免疫状态，魔法抗性提升。",
        "获得魔法抗性。",
        "恢复生命并获得法力消耗降低。",
    ],
)
def test_mana_gain_does_not_confuse_resistance_or_cost_reduction(text):
    assert "mana_gain" not in {mid for mid, _ in text_hits(text)}


def test_checked_in_package_receipt_and_facts(sources):
    import hashlib

    directory = ROOT / "knowledge/mechanics/extractions/v1"
    receipt = json.loads((directory / "manifest.json").read_text())
    for section in ("input_sha256", "implementation_sha256"):
        for name, expected in receipt[section].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    for name, expected in receipt["output_sha256"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected
    mf.load_facts(json.loads((directory / "facts-v1.json").read_text()), sources)
