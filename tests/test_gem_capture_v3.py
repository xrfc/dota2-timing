"""Parser v3 helpers (U130): lanes, lane fronts, charges, summon owners, cooldown check."""

from dota_items.sources import gem_capture_v3 as v3

C = v3.MAP_CENTER


def test_lane_of_splits_by_the_map_diagonal():
    assert v3.lane_of(C - 6000, C + 2000) == "top"
    assert v3.lane_of(C + 6000, C - 2000) == "bot"
    assert v3.lane_of(C + 500, C + 800) == "mid"


def test_lane_fronts_take_the_creep_furthest_toward_the_enemy():
    creeps = [
        (2, C - 1000, C - 900),
        (2, C + 200, C + 300),
        (3, C + 900, C + 1000),
        (3, C - 100, C),
    ]
    fronts = v3.lane_fronts(creeps)
    assert fronts["radiant_mid"] == {"count": 2, "front": [round(C + 200), round(C + 300)]}
    assert fronts["dire_mid"] == {"count": 2, "front": [round(C - 100), round(C)]}


def test_no_charge_sentinel_becomes_null():
    assert v3._charges(-1000000.0) is None and v3._charges(None) is None
    assert v3._charges(3.25) == 3.25


class Fake:
    def __init__(self, index, **fields):
        self.index, self.fields = index, fields

    def get(self, name):
        return self.fields.get(name)

    def get_index(self):
        return self.index


class FakeManager:
    def __init__(self, entities):
        self.by_handle = entities

    def find_by_handle(self, handle):
        return self.by_handle.get(handle)


def test_summon_owner_follows_owner_handles_to_a_hero():
    hero = Fake(5)
    bear_owner = Fake(9, m_hOwnerNPC=100)  # e.g. a summon owned by another summon
    em = FakeManager({100: hero, 200: bear_owner})
    heroes = {5: 3}  # entity index 5 is player 3's hero
    assert v3.owner_player(Fake(1, m_hOwnerNPC=100), em, heroes) == 3
    assert v3.owner_player(Fake(2, m_hOwnerEntity=200), em, heroes) == 3
    assert v3.owner_player(Fake(3, m_hOwnerNPC=v3.NULL_HANDLE), em, heroes) is None


def _row(t, cd, name="lion_impale", hero="npc_dota_hero_lion"):
    return {
        "t": t,
        "heroes": [
            {"hero": hero, "abilities": [{"name": name, "cd": cd, "cd_len": 12.0}], "items": {}}
        ],
    }


def _cast(time, name="lion_impale", hero="npc_dota_hero_lion"):
    payload = {
        "log_type": "ABILITY",
        "attacker_is_hero": True,
        "attacker_is_illusion": False,
        "inflictor_name": name,
        "attacker_name": hero,
    }
    return {"time": time, "payload": payload}


def test_cooldown_check_counts_casts_that_start_a_cooldown():
    rows = [_row(100, 0.0), _row(101, 11.5), _row(200, 0.0), _row(201, 0.0), _row(202, 0.0)]
    result = v3.check_cooldowns(rows, [_cast(100.4), _cast(200.2)])
    assert result["checked"] == 2 and result["cooldown_seen"] == 1
    assert result["missed_examples"] == [
        {"time": 200.2, "hero": "npc_dota_hero_lion", "name": "lion_impale"}
    ]


def test_cooldown_check_skips_slots_without_cooldown_and_other_events():
    rows = [
        {
            "t": 5,
            "heroes": [
                {"hero": "h", "abilities": [{"name": "p", "cd": 0, "cd_len": 0}], "items": {}}
            ],
        }
    ]
    damage = {"time": 5, "payload": {"log_type": "DAMAGE"}}
    assert v3.check_cooldowns(rows, [_cast(5, "p", "h"), damage])["checked"] == 0
