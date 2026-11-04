"""MK-T4 rules v1 on frozen v7 are validated and connect the expected subjects."""

import hashlib
import json
from pathlib import Path

import pytest

from dota_items.data.mechanics import load_enums, load_vocabulary
from dota_items.data.mechanics_interactions import evaluate_rule, load_rules

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v7"


def _json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def terms():
    registry = _json("knowledge/hero-capabilities/hero-registry.json")
    enums = load_enums(_json("knowledge/mechanics/enums-v1.json"), registry["heroes"])
    return load_vocabulary(_json("knowledge/mechanics/vocabulary-v7.json"), enums)


@pytest.fixture(scope="module")
def evaluation():
    data = json.loads((PACKAGE / "rules-evaluation.json").read_text(encoding="utf-8"))
    return {rule["id"]: rule for rule in data["rules"]}


def test_package_matches_manifest():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected


def test_rules_load_and_reject_bad_input(terms):
    rules = load_rules(_json("knowledge/mechanics/rules-v1.json"), terms)
    assert len(rules) == 20
    bad = {"schema": "mechanics-rules/1", "rules": [{**rules[0], "source_mechanisms": ["nope"]}]}
    with pytest.raises(ValueError, match="unknown mechanism"):
        load_rules(bad, terms)
    with pytest.raises(ValueError, match="unknown relation"):
        load_rules({"schema": "mechanics-rules/1", "rules": [{**rules[0], "relation": "x"}]}, terms)


def test_dispel_rules_follow_the_enum(evaluation):
    assert "windrunner_windrun" in evaluation["R01"]["targets"]
    assert "dazzle_shallow_grave" not in evaluation["R01"]["targets"]
    assert "dazzle_shallow_grave" not in evaluation["R02"]["targets"]
    assert set(evaluation["R01"]["targets"]) <= set(evaluation["R02"]["targets"])


def test_user_rules_compute_expected_examples(evaluation):
    assert "monkey_king_bar" in evaluation["R07"]["sources"]
    assert "butterfly" in evaluation["R07"]["targets"]
    assert "smoke_of_deceit" not in evaluation["R06"]["targets"]
    assert "black_king_bar" in evaluation["R10"]["targets"]
    assert "doom_bringer_doom" in evaluation["R14"]["sources"]
    assert "essence_ring" not in evaluation["R14"]["targets"]
    assert "blink" in evaluation["R18"]["targets"]
    assert "force_staff" not in evaluation["R18"]["targets"]
    assert "earthshaker_echo_slam" in evaluation["R20"]["sources"]
    assert "arcane_boots" not in evaluation["R20"]["sources"]


def test_pending_rules_have_no_targets_yet(evaluation):
    assert evaluation["R12"]["targets"] == []
    assert evaluation["R15"]["targets"] == []


def test_evaluate_ignores_rejected_rows():
    doc = {
        "rows": [
            {"subject": "a", "mechanism": "stun", "decision": "reject"},
            {"subject": "b", "mechanism": "stun", "decision": "accept"},
        ],
        "skill_notes": [],
        "field_observations": [],
    }
    assert evaluate_rule({"source_mechanisms": ["stun"]}, doc)["sources"] == ["b"]
