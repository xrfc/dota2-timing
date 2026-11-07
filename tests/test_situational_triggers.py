"""M2b triggers (U123): spec, firing logic and validation on synthetic matches."""

import json
from pathlib import Path

from dota_items.modeling import situational_triggers as st

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "knowledge/situational-items/triggers-v2.json").read_text("utf-8"))


def test_spec_covers_the_six_classes_and_known_items():
    from dota_items.modeling import situational_items as si

    assert sorted(i["id"] for i in SPEC["items"]) == sorted(si.CLASSES)
    registry = json.loads((ROOT / "knowledge/items/item-registry.json").read_text("utf-8"))["items"]
    assert all(x in registry for i in SPEC["items"] for x in i["ingame_items"])


class FakeKnowledge:
    """The three API methods triggers use, with fixed small answers."""

    def __init__(self, sums=None, owners=None, rules=None):
        self.sums, self.owners, self.rules = sums or {}, owners or {}, rules or {}

    def team_trait_sum(self, heroes, trait, upgrades="base"):
        return sum(self.sums.get(trait, {}).get(h, 0) for h in heroes)

    def heroes_owning(self, abilities):
        return {self.owners[a] for a in abilities if a in self.owners}

    def rule_target_heroes(self, rule_id):
        return self.rules.get(rule_id, set())


def test_pregame_and_ingame_firing():
    kb = FakeKnowledge(sums={"evasion": {1: 1, 2: 0}}, owners={"life_stealer_rage": 54})
    mkb = SPEC["items"][0]
    assert st.pregame_fires(mkb, [1, 2], kb)
    assert not st.pregame_fires(mkb, [2], kb)
    basher = next(i for i in SPEC["items"] if i["id"] == "basher")
    assert st.pregame_fires(basher, [54], kb)
    assert not st.pregame_fires(basher, [6], kb)
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
    result = st.validate(SPEC, players, purchases, [1, 2], FakeKnowledge(sums=sums))
    mkb = result["items"][0]
    assert result["samples"] == 2 and mkb["pregame_rate"] == 0.5
    assert mkb["ingame_rate"] == 0.5  # match 2's butterfly came after Juggernaut's Skadi
    assert mkb["pregame_first"]["with"] == 1.0 and mkb["pregame_first"]["without"] == 0.0


def test_basher_lists_name_real_abilities():
    from dota_items.data.mechanics_api import Knowledge

    kb = Knowledge(ROOT)
    lists = next(i for i in SPEC["items"] if i["id"] == "basher")["pregame"]["abilities_any"]
    assert 33 in kb.heroes_owning(lists["channel_ultimates"])  # Enigma, Black Hole
    assert 54 in kb.heroes_owning(lists["self_debuff_immunity"])  # Lifestealer, Rage
