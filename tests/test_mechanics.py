"""U26 layer 1: the enum decoding table must agree with the hero registry."""

import json
from pathlib import Path

import pytest

from dota_items.data import mechanics as mx

ROOT = Path(__file__).resolve().parents[1]

HEROES = [
    {
        "abilities": [
            {"name": "a_blink", "raw_mechanics": {"dispellable": 0}},
            {"name": "a_shield", "raw_mechanics": {"dispellable": "2"}},
        ]
    }
]


def doc(values):
    return {"schema": "mechanics-enums/1", "fields": {"dispellable": {"values": values}}}


def entry(*examples, confirmed=False):
    return {"zh": "x", "examples": list(examples), "confirmed": confirmed}


def test_valid_table_decodes_and_lists_unconfirmed():
    enums = mx.load_enums(
        doc({"0": entry("a_blink"), "2": entry("a_shield", confirmed=True)}), HEROES
    )
    assert mx.decode(enums, "dispellable", "2") == "x"
    assert mx.unconfirmed(enums) == [("dispellable", 0)]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"0": entry("a_blink"), "2": entry("a_blink")}, "has 0"),
        ({"0": entry("a_blink"), "2": entry("missing")}, "unknown example"),
        ({"0": entry("a_blink"), "2": entry()}, "at least one example"),
        ({"0": entry("a_blink")}, "without meaning: \\[2\\]"),
        ({"0": entry("a_blink"), "2": {"zh": "x", "examples": ["a_shield"]}}, "confirmed"),
    ],
)
def test_wrong_examples_and_unexplained_values_fail(values, message):
    with pytest.raises(ValueError, match=message):
        mx.load_enums(doc(values), HEROES)


def test_real_table_matches_registry():
    registry = json.loads((ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text())
    table = json.loads((ROOT / "knowledge/mechanics/enums-v1.json").read_text())
    enums = mx.load_enums(table, registry["heroes"])
    assert set(enums) == {"dispellable", "target_team", "damage", "type"}
    assert mx.decode(enums, "dispellable", 3) == "不可驱散"
