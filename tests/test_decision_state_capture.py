"""Live probe preserves missingness, native field metadata and resolved handles."""

from types import SimpleNamespace

from dota_items.sources.decision_state_capture import capture, scalar


def test_probe_keeps_zero_missing_cd_and_backpack_separate():
    class Entity:
        cls = SimpleNamespace(serializer=None)

        def __init__(self, values, index=1):
            self.values, self.index = values, index

        def get(self, name):
            return self.values.get(name)

        get_int32 = get
        get_uint32 = get

        def get_index(self):
            return self.index

        def get_serial(self):
            return 3

        def get_class_name(self):
            return "synthetic"

    hero = Entity({"m_iHealth": 0, "m_hItems.0006": 123, "m_hItems.0000": 0xFFFFFF})
    item = Entity(
        {"m_pEntity.m_nameStringTableIndex": 0, "m_fCooldown": 0.0, "m_iCurrentCharges": 0}, 2
    )
    parser = SimpleNamespace(
        entity_manager=SimpleNamespace(find_by_handle=lambda h: item if h == 123 else None),
        string_tables=SimpleNamespace(
            get_by_name=lambda name: SimpleNamespace(items={0: ("item_blink", b"")})
        ),
        game_time_s=100,
        game_clock=SimpleNamespace(game_start_time_s=300.0),
    )
    ext = SimpleNamespace(_canonical_hero_entity=lambda pid: hero, _parser=parser)
    row = capture(ext, SimpleNamespace(player_id=0, tick=3000, level=1))
    assert row["hero"]["values"]["m_iHealth"] == 0
    assert row["hero"]["values"]["m_flMana"] is None
    assert row["items"][0]["status"] == "empty"
    assert row["items"][1]["status"] == "unknown"
    assert row["items"][6]["entity"]["values"]["m_fCooldown"] == 0
    assert row["items"][6]["entity"]["values"]["m_flCooldownLength"] is None
    assert row["items"][6]["name"] == "item_blink"
    assert scalar(float("nan")) is None and scalar(False) is False
