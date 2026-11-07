"""M2b triggers (U123): spec, firing logic and validation on synthetic matches."""

import json
from pathlib import Path

import pytest

from dota_items.modeling import situational_triggers as st

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "knowledge/situational-items/triggers-v2.json").read_text("utf-8"))


def test_spec_covers_the_six_classes_and_known_items():
    from dota_items.modeling import situational_items as si

    assert sorted(i["id"] for i in SPEC["items"]) == sorted(si.CLASSES)
    registry = json.loads((ROOT / "knowledge/items/item-registry.json").read_text("utf-8"))["items"]
    assert all(x in registry for i in SPEC["items"] for x in i["ingame_items"])


def test_pregame_and_ingame_firing():
    sums = {"evasion": {1: 1, 2: 0}}
    mkb = SPEC["items"][0]
    assert st.pregame_fires(mkb, [1, 2], sums, {})
    assert not st.pregame_fires(mkb, [2], sums, {})
    basher = next(i for i in SPEC["items"] if i["id"] == "basher")
    lists = {"abilities:channel_ultimates": {33}, "abilities:self_debuff_immunity": {54}}
    assert st.pregame_fires(basher, [54], {}, lists)
    assert not st.pregame_fires(basher, [6], {}, lists)
    assert st.ingame_fires(mkb, {"butterfly"}) and not st.ingame_fires(mkb, {"blink"})


def _player(mid, slot, hero, radiant, position=None):
    return {
        "match_id": mid,
        "player_slot": slot,
        "hero_id": hero,
        "is_radiant": radiant,
        "position": position,
        "collapsed_carry": False,
    }


def test_validation_uses_items_seen_before_the_first_situational_item():
    players = [_player(1, 0, 8, True, 1), _player(1, 128, 1, False), _player(2, 0, 8, True, 1)]
    players.append(_player(2, 128, 2, False))
    purchases = [
        {"match_id": 1, "player_slot": 128, "time_s": 100, "item": "butterfly"},
        {"match_id": 1, "player_slot": 0, "time_s": 200, "item": "monkey_king_bar"},
        {"match_id": 2, "player_slot": 0, "time_s": 300, "item": "skadi"},
        {"match_id": 2, "player_slot": 128, "time_s": 400, "item": "butterfly"},
    ]
    sums = {t: {1: 1, 2: 0} for t in ("evasion", "sustain", "disables", "dispellable_save")}
    lists = {"abilities:channel_ultimates": set(), "abilities:self_debuff_immunity": set()}
    result = st.validate(SPEC, players, purchases, [1, 2], sums, lists)
    mkb = result["items"][0]
    assert result["samples"] == 2 and mkb["pregame_rate"] == 0.5
    assert mkb["ingame_rate"] == 0.5  # match 2's butterfly came after Juggernaut's Skadi
    assert mkb["pregame_first"]["with"] == 1.0 and mkb["pregame_first"]["without"] == 0.0


def test_basher_lists_name_real_abilities():
    registry = json.loads(
        (ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text("utf-8")
    )
    lists = st.rule_heroes({"rules": []}, registry["heroes"], SPEC)
    assert 33 in lists["abilities:channel_ultimates"]  # Enigma, Black Hole
    assert 54 in lists["abilities:self_debuff_immunity"]  # Lifestealer, Rage
    bad = {"items": [{"id": "x", "pregame": {"abilities_any": {"l": ["no_such_ability"]}}}]}
    with pytest.raises(ValueError, match="unknown abilities"):
        st.rule_heroes({"rules": []}, registry["heroes"], bad)
