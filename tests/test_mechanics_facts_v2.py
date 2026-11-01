"""MK-T3 v2 extractor: round-1 false positives/negatives and frozen v2 package."""

import hashlib
import json
from pathlib import Path

import pytest

from dota_items.data import mechanics_facts_v2 as mf2
from dota_items.data.mechanics_rules_v2 import text_hits

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v2"


@pytest.fixture(scope="module")
def sources():
    return {
        name: json.loads((ROOT / name).read_text())
        if name.endswith(".json")
        else {"text": (ROOT / name).read_text()}
        for name in mf2.INPUTS
    }


@pytest.fixture(scope="module")
def facts(sources):
    return mf2.build_facts(sources)


def hits(text, names=()):
    return {mid for mid, _ in text_hits(text, names)}


@pytest.mark.parametrize(
    ("text", "names", "present", "absent"),
    [
        ("Attacks lower enemy movement by -25%.", (), {"slow"}, set()),
        (
            "Attacks also lower enemy attack speed by -25% and Health Restoration by 50%.",
            (),
            {"heal_reduction"},
            set(),
        ),
        ("Prevents a target from attacking for 3.5 seconds.", (), {"disarm"}, set()),
        ("Morphling can shift attributes while stunned.", (), set(), {"stun"}),
        (
            "Skewer is interrupted if Magnus is stunned, hexed or banished.",
            (),
            set(),
            {"stun", "hex", "cyclone_banish"},
        ),
        (
            "Has a transformation time, which can be used to dodge projectiles and stuns.",
            (),
            set(),
            {"stun"},
        ),
        ("Passively grants Lifestealer Attack Speed.", ("Lifestealer",), set(), {"lifesteal"}),
        (
            "召唤一群小精灵治疗魅惑魔女以及身边的友方单位。",
            ("魅惑魔女",),
            {"healing"},
            {"forced_action"},
        ),
        ("Grants bonus damage and slow resistance.", (), {"slow_resistance"}, {"slow"}),
        (
            "After a successful channel, summons a meteor that strikes a 400 AoE.",
            (),
            set(),
            {"summons"},
        ),
        ("Marci whistles to instantly summon her courier to her.", (), set(), {"summons"}),
        ("Chen takes control of an enemy or neutral creep.", (), {"summons"}, set()),
        (
            "Axe will perform a helix counter attack, dealing pure damage.",
            (),
            {"damage_return"},
            set(),
        ),
        (
            "Damage done by this ability is considered reflected damage.",
            (),
            set(),
            {"damage_return"},
        ),
        (
            "Delaying any healing or damage taken until False Promise ends.",
            (),
            {"damage_block"},
            set(),
        ),
        ("Laguna Blade has a delay before the damage is applied.", (), set(), {"damage_block"}),
        ("Meat Hook hits invisible units.", (), set(), {"invisibility"}),
        (
            "Hurls a bolt of lightning that leaps through nearby enemy units.",
            (),
            set(),
            {"self_mobility"},
        ),
        (
            "You can interrupt channeling spells and items with this ability.",
            (),
            set(),
            {"channeled"},
        ),
        (
            "Prevents the target from regenerating or gaining mana for a short duration.",
            (),
            set(),
            {"heal_reduction"},
        ),
        ("Stuns a target enemy unit for 1.6 seconds.", (), {"stun"}, set()),
    ],
)
def test_round1_regressions(text, names, present, absent):
    found = hits(text, names)
    assert present <= found
    assert not found & absent


def rows(doc, subject, mechanism):
    return [f for f in doc["facts"] if f["subject"] == subject and f["mechanism"] == mechanism]


def test_missed_counter_items_and_user_exclusions(facts):
    assert rows(facts, "skadi", "slow") and rows(facts, "skadi", "heal_reduction")
    assert rows(facts, "heavens_halberd", "disarm")
    assert any(
        f["evidence_kind"] == "item_attr:evasion" for f in rows(facts, "radiance", "evasion")
    )
    assert rows(facts, "axe_counter_helix", "damage_return")
    assert rows(facts, "chen_holy_persuasion", "summons")
    for passive in mf2.NOT_BREAKABLE:
        assert not rows(facts, passive, "break_sensitive")
    assert not rows(facts, "life_stealer_ghoul_frenzy", "lifesteal")


def test_v2_replays_and_rejects_tampering(sources, facts):
    assert mf2.load_facts(facts, sources)
    changed = json.loads(json.dumps(facts))
    changed["facts"][0]["quote"] = "invented"
    with pytest.raises(ValueError):
        mf2.load_facts(changed, sources)


def test_checked_in_v2_package(sources):
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    doc = json.loads((PACKAGE / "facts-v2.json").read_text())
    mf2.load_facts(doc, sources)
    delta = json.loads((PACKAGE / "delta-vs-v1.json").read_text())
    assert delta["dropped_from_v1_by_round1_decision"] == {"reject": 94}
