from dota_items.data import smoke_breaks as s
from dota_items.data import teleports as tp


def entry(t, kind, source=None, target=None, name=None):
    payload = {"log_type": kind, "attacker_name": source, "target_name": target}
    return {"time": t, "payload": {**payload, "inflictor_name": name}}


def test_teleports_find_the_landing_second_and_keep_cancelled_casts():
    base = {t: (1000, 1000) for t in range(0, 30)}
    moved = {**base, **{t: (9000, 9000) for t in range(15, 30)}}
    tracks = {"a": {"team": 2, "pos": moved}, "b": {"team": 3, "pos": base}}
    combat = [
        entry(10, "ITEM", "a", None, "item_tpscroll"),
        entry(20, "ITEM", "b", None, "item_tpscroll"),  # never moves: cancelled
        entry(21, "ITEM", "b", None, "item_blink"),
    ]
    result = tp.teleports(tracks, combat)
    assert [(r["hero"], r["landed"], r["end"]) for r in result] == [
        ("a", 15, (9000, 9000)),
        ("b", None, None),
    ]
    assert tp.arrived_near(result, "a", (9100, 9100), 0, 20, 500) == [result[0]]
    assert tp.arrived_near(result, "a", (1000, 1000), 0, 20, 500) == []


def test_smoke_breaks_measure_the_nearest_enemy_when_smoke_ends():
    tracks = {
        "a": {"team": 2, "pos": {t: (1000, 1000) for t in range(0, 60)}},
        "e": {"team": 3, "pos": {t: (1900, 1000) for t in range(0, 60)}},
    }
    combat = [
        entry(5, "MODIFIER_ADD", "a", "a", s.SMOKE_MODIFIER),
        entry(20, "MODIFIER_REMOVE", "a", "a", s.SMOKE_MODIFIER),
        entry(5, "MODIFIER_ADD", "e", "e", s.SMOKE_MODIFIER),
        entry(50, "MODIFIER_REMOVE", "e", "e", s.SMOKE_MODIFIER),
    ]
    spans = s.smoke_spans(combat)
    towers = [{"team": 3, "x": 1000, "y": 5000, "name": "tower"}]
    s.describe_breaks(spans, tracks, lambda second: towers)
    first, second = sorted(spans, key=lambda x: x["hero"])
    assert first["lasted"] == 15 and first["nearest_enemy_hero"] == {"hero": "e", "distance": 900}
    assert first["nearest_enemy_building"] == {"name": "tower", "distance": 4000}
    assert s.broke_near_enemy(first) and not s.broke_near_enemy(second)  # second ran out
