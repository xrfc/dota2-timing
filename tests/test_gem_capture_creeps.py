from dota_items.sources import gem_capture_creeps_review_v2 as c


class Entity:
    def __init__(self, cls, team, life, pos):
        self.cls, self.values, self.pos = cls, {"m_iTeamNum": team, "m_lifeState": life}, pos

    def get_class_name(self):
        return self.cls

    def get(self, key):
        return self.values.get(key)


class Manager:
    def __init__(self, entities):
        self.entities = entities

    def all_active(self):
        return self.entities


def test_creep_rows_keep_living_lane_and_siege_creeps_only():
    manager = Manager(
        [
            Entity("CDOTA_BaseNPC_Creep_Lane", 3, 0, (200.6, 10.2)),
            Entity("CDOTA_BaseNPC_Creep_Siege", 2, 0, (100.4, 50.5)),
            Entity("CDOTA_BaseNPC_Creep_Lane", 2, 1, (1, 1)),  # dead
            Entity("CDOTA_BaseNPC_Creep_Neutral", 4, 0, (5, 5)),
            Entity("CDOTA_BaseNPC_Creep_Lane", 2, 0, None),  # no position yet
        ]
    )
    assert c.creep_rows(manager, lambda e: e.pos) == [[2, 100, 50], [3, 201, 10]]


def test_extras_row_reads_watcher_holders_outposts_and_scan():
    from dota_items.sources import gem_capture_extras_review_v2 as x

    class Rules:
        def get(self, field):
            return {
                "m_pGameRules.m_fGoodRadarCooldown": 353.44,
                "m_pGameRules.m_iBadRadarCharges": 2,
            }.get(field)

    class World(Manager):
        def find_by_class_name(self, name):
            return Rules() if name == "CDOTAGamerulesProxy" else None

    watcher = Entity(x.WATCHER, 5, 0, (8576.2, 17440.0))
    watcher.values["m_nFoWTeam"] = 3
    free = Entity(x.WATCHER, 5, 0, (100, 200))
    outpost = Entity(x.OUTPOST, 2, 0, (12288, 15936))
    row = x.extras_row(
        World([watcher, free, outpost, Entity("CDOTA_Unit_Roshan", 4, 0, (1, 1))]), lambda e: e.pos
    )
    assert row["watchers"] == [[100, 200, 0], [8576, 17440, 3]]
    assert row["outposts"] == [[12288, 15936, 2]]
    assert row["scan"] == {
        "radiant_cooldown": 353.4,
        "dire_cooldown": None,
        "radiant_charges": None,
        "dire_charges": 2,
    }
