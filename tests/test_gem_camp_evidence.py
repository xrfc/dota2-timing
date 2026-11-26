"""Decision-boundary evidence, independent of any post-replay feature projection."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from dota_items.sources import gem_camp_evidence as source
from dota_items.storage import file_hash

HERO = "npc_dota_hero_sven"
OTHER_HERO = "npc_dota_hero_chen"
UNIT = "npc_dota_dark_troll_warlord_skeleton_warrior"
GENERIC = "npc_dota_creep_neutral"


class Entity:
    def __init__(self, index, serial, class_name, fields=None, active=True):
        self.index, self.serial, self.class_name = index, serial, class_name
        self.fields, self.active = fields or {}, active

    def get(self, field):
        return self.fields.get(field)

    def get_index(self):
        return self.index

    def get_serial(self):
        return self.serial

    def get_class_name(self):
        return self.class_name

    @property
    def handle(self):
        return (self.serial << 14) | self.index


class Manager:
    def __init__(self, entities):
        self.entities = entities

    def all_active(self):
        return [e for e in self.entities if e.active]

    def find_by_handle(self, handle):
        return next((e for e in self.entities if e.handle == handle), None)


class Tables:
    def __init__(self):
        self.tables = {
            "EntityNames": SimpleNamespace(
                items={1: (HERO, b""), 2: (GENERIC, b""), 3: (OTHER_HERO, b"")}
            ),
            # Index 2 intentionally means something different in EntityNames.
            "UnitNames": SimpleNamespace(items={2: (UNIT, b"")}),
        }

    def get_by_name(self, name):
        return self.tables.get(name)


def roster_fields(hero, *, index=6, team=3, slot=1):
    return {
        f"m_vecPlayerData.{index:04d}.m_iPlayerTeam": team,
        f"m_vecPlayerTeamData.{index:04d}.m_iTeamSlot": slot,
        f"m_vecPlayerTeamData.{index:04d}.m_hSelectedHero": hero.handle,
    }


def world():
    hero = Entity(
        303,
        439,
        "CDOTA_Unit_Hero_Sven",
        {
            source.ENTITY_NAME_FIELDS[0]: 1,
            "m_iTeamNum": 3,
        },
    )
    resource = Entity(9, 1, "CDOTA_PlayerResource", roster_fields(hero))
    neutral = Entity(
        63,
        525,
        source.NEUTRAL_CLASS,
        {
            source.ENTITY_NAME_FIELDS[0]: 2,
            "m_iUnitNameStringTableIndex": 2,
            "m_iTeamNum": 3,
            "m_iHealth": 100,
            "m_iMaxHealth": 250,
            "m_lifeState": 0,
            "CBodyComponent.m_cellX": 128,
            "CBodyComponent.m_cellY": 130,
            "CBodyComponent.m_vecX": 12.5,
            "CBodyComponent.m_vecY": 0.0,
            "m_hOwnerNPC": hero.handle,
            "m_bIsSummoned": True,
            "m_iIsControllableByPlayer64": 64,
            "m_nPlayerOwnerID": 6,
        },
    )
    radiant = Entity(10, 1, "CDOTADataRadiant", {"m_bNPCVisibleState.0000": 1 << 63})
    dire = Entity(11, 2, "CDOTA_DataDire", {"m_bNPCVisibleState.0000": 0})
    em = Manager([hero, resource, neutral, radiant, dire])
    return SimpleNamespace(
        em=em,
        tables=Tables(),
        hero=hero,
        resource=resource,
        unit=neutral,
        radiant=radiant,
        dire=dire,
    )


def replay(monkeypatch, scene, steps, *, clock=None, parse_error=None, match_id=123):
    """Each step mutates live objects immediately before a tick-start callback."""
    checks = []

    class Parser:
        def __init__(self, path):
            self.entity_manager, self.string_tables = scene.em, scene.tables
            self.game_time_s = self.tick = None
            self.match_id, self.parse_error = match_id, parse_error
            self.truncated_at_tick = 20 if parse_error else None
            self.final_times = {}
            self.game_clock = SimpleNamespace(
                game_seconds_at=lambda tick: clock(tick) if clock else self.final_times[tick]
            )

        def on_tick_start(self, callback):
            self.callback = callback

        def parse(self):
            for second, tick, mutation in steps:
                if mutation:
                    mutation(self)
                self.game_time_s, self.tick = second, tick
                self.final_times[tick] = second
                self.callback(tick + 1000)

    monkeypatch.setattr(source, "_runtime", lambda: (Parser, "test-gem-root"))

    def verify(root):
        checks.append(root)
        return source.COMPAT_SHA256

    monkeypatch.setattr(source, "verify_compatibility", verify)
    return checks


def capture(cases=None):
    return source.capture_camp_evidence("unpacked.dem", cases or [(HERO, 10)])


def test_raw_snapshot_has_actual_names_coordinates_ownership_and_mask(monkeypatch):
    scene = world()
    checks = replay(monkeypatch, scene, [(10, 20, None)])
    result = capture()
    assert result["schema"] == "gem-camp-evidence/1"
    assert result["sampling"] == "first_tick_start_before_entity_updates"
    assert result["omniscient"] is True
    assert result["match_id"] == 123
    assert checks == ["test-gem-root", "test-gem-root"]
    frame = result["frames"][0]
    assert frame["observer"] == dict(team=3, slot=1, resource_index=6)
    assert frame["observer_evidence"]["entity_serial"] == 439
    assert (frame["tick"], frame["net_tick"], frame["status"]) == (20, 1020, "observed")
    unit = frame["units"][0]
    assert unit["entity_name"] == GENERIC and unit["unit_name"] == UNIT
    assert (unit["x"], unit["y"]) == (16396.5, 16640.0)
    assert unit["team"] == 3 and unit["health"] == 100
    assert unit["ownership"]["m_hOwnerNPC"] == scene.hero.handle
    assert unit["ownership"]["m_bIsSummoned"] is True
    assert unit["ownership"]["m_bIsControllable"] is None
    assert unit["visibility"] == dict(radiant="visible", dire="hidden")
    assert unit["visibility_source"]["radiant"] == dict(
        field="m_bNPCVisibleState.0000",
        bit=63,
        word=1 << 63,
        team_entity_index=10,
        team_entity_serial=1,
    )


def test_first_callback_copies_values_and_same_tick_future_cannot_backfill(monkeypatch):
    scene = world()

    def later(parser):
        scene.unit.fields.update(m_iHealth=0, m_lifeState=2)
        scene.unit.fields["CBodyComponent.m_vecX"] = 100
        scene.unit.serial += 1
        scene.radiant.fields["m_bNPCVisibleState.0000"] = 0
        scene.tables.tables["UnitNames"].items[2] = ("future_unit_name", b"")

    replay(monkeypatch, scene, [(10, 20, None), (10, 20, later), (11, 21, None)])
    first, next_frame = capture([(HERO, 11), (HERO, 10)])["frames"]
    early, late = first["units"][0], next_frame["units"][0]
    assert (early["health"], early["life_state"], early["entity_serial"]) == (100, 0, 525)
    assert early["x"] == 16396.5 and early["unit_name"] == UNIT
    assert early["visibility"]["radiant"] == "visible"
    assert (late["health"], late["life_state"], late["entity_serial"]) == (0, 2, 526)
    assert late["unit_name"] == "future_unit_name"
    assert late["visibility"]["radiant"] == "hidden"


@pytest.mark.parametrize("missing", ["manager", "resource", "names", "selected_hero"])
def test_missing_first_callback_is_not_replaced_same_second(monkeypatch, missing):
    scene = world()

    def remove(parser):
        if missing == "manager":
            parser.entity_manager = None
        elif missing == "resource":
            scene.resource.active = False
        elif missing == "names":
            scene.tables.tables.pop("EntityNames")
        else:
            scene.hero.active = False

    def restore(parser):
        parser.entity_manager = scene.em
        scene.resource.active = scene.hero.active = True
        scene.tables.tables["EntityNames"] = Tables().tables["EntityNames"]

    replay(monkeypatch, scene, [(10, 20, remove), (10, 20, restore), (11, 21, None)])
    first, second = capture([(HERO, 10), (HERO, 11)])["frames"]
    assert first["observer"] is None
    assert first["status"] == ("missing_frame" if missing == "manager" else "missing_observer")
    assert second["status"] == "observed"
    if missing == "manager":
        assert first["units"] is None


def test_future_name_table_does_not_fill_missing_unit_name(monkeypatch):
    scene = world()
    scene.tables.tables.pop("UnitNames")

    def fill(parser):
        scene.tables.tables["UnitNames"] = Tables().tables["UnitNames"]

    replay(monkeypatch, scene, [(10, 20, None), (10, 21, fill)])
    unit = capture()["frames"][0]["units"][0]
    assert unit["unit_name"] is None
    assert unit["entity_name"] == GENERIC
    assert unit["naming"]["unit_name"]["missing_reason"] == "missing_table"


def test_source_to_public_missing_manager_keeps_first_tick_without_backfill(monkeypatch):
    from dota_items.data.camp_evidence import project_camp_evidence

    scene = world()
    scene.dire.fields["m_bNPCVisibleState.0000"] = 1 << 63

    def missing(parser):
        parser.entity_manager = None

    def recover(parser):
        parser.entity_manager = scene.em

    replay(monkeypatch, scene, [(10, 20, missing), (10, 20, recover), (11, 21, None)])
    raw = capture([(HERO, 10), (HERO, 11)])
    first, second = project_camp_evidence(raw)["frames"]
    assert (first["tick"], first["net_tick"], first["status"]) == (20, 1020, "missing_frame")
    assert first["observer"] is None and first["units"] == []
    assert second["status"] == "observed" and len(second["units"]) == 1
    assert second["units"][0]["unit_name"] == UNIT
    assert second["stock_complete"] is False and second["empty_confirmed"] is None


def test_source_to_public_hidden_units_have_no_effect(monkeypatch):
    from dota_items.data.camp_evidence import project_camp_evidence

    scene = world()
    replay(monkeypatch, scene, [(10, 20, None)])
    before = project_camp_evidence(capture())
    scene.unit.fields.update(m_iHealth=900, m_iTeamNum=4, m_hOwnerNPC=999)
    scene.unit.serial += 1
    extra = deepcopy(scene.unit)
    extra.index = 64  # Own-team word missing: unknown, also excluded.
    scene.em.entities.append(extra)
    replay(monkeypatch, scene, [(10, 20, None)])
    after = project_camp_evidence(capture())
    assert before == after
    assert before["frames"][0]["units"] == []


@pytest.mark.parametrize("team_missing", [False, True])
def test_absent_visibility_word_or_team_is_unknown_not_hidden(monkeypatch, team_missing):
    scene = world()
    if team_missing:
        scene.dire.active = False
    else:
        scene.dire.fields.clear()
    replay(monkeypatch, scene, [(10, 20, None)])
    frame = capture()["frames"][0]
    assert frame["status"] == "observed"
    assert frame["units"][0]["visibility"]["dire"] == "unknown"
    assert frame["units"][0]["visibility_source"]["dire"]["word"] is None


def test_visibility_word_boundary_is_not_off_by_one(monkeypatch):
    scene = world()
    next_unit = deepcopy(scene.unit)
    next_unit.index = 64
    scene.em.entities.append(next_unit)
    scene.radiant.fields["m_bNPCVisibleState.0001"] = 0
    scene.dire.fields["m_bNPCVisibleState.0001"] = 1
    replay(monkeypatch, scene, [(10, 20, None)])
    units = capture()["frames"][0]["units"]
    assert units[1]["visibility"] == dict(radiant="hidden", dire="visible")
    assert units[1]["visibility_source"]["dire"]["bit"] == 0


def test_active_dead_and_controlled_units_retained_inactive_and_other_class_excluded(monkeypatch):
    scene = world()
    scene.unit.fields.update(m_lifeState=2, m_iHealth=0)
    inactive, other = deepcopy(scene.unit), deepcopy(scene.unit)
    inactive.index, inactive.active = 64, False
    other.index, other.class_name = 65, "CDOTA_BaseNPC_Creep"
    scene.em.entities.extend([inactive, other])
    replay(monkeypatch, scene, [(10, 20, None)])
    units = capture()["frames"][0]["units"]
    assert len(units) == 1
    assert units[0]["life_state"] == 2 and units[0]["health"] == 0
    assert units[0]["team"] == 3


def test_deletion_and_index_reuse_do_not_infer_death_or_retain_old_unit(monkeypatch):
    scene = world()

    def delete(parser):
        scene.unit.active = False

    def reuse(parser):
        replacement = deepcopy(scene.unit)
        replacement.active, replacement.serial = True, 526
        replacement.fields["m_iHealth"] = 40
        scene.em.entities.append(replacement)

    replay(monkeypatch, scene, [(10, 20, None), (11, 21, delete), (12, 22, reuse)])
    frames = capture([(HERO, t) for t in (10, 11, 12)])["frames"]
    assert frames[0]["units"][0]["health"] == 100
    assert frames[1]["units"] == [] and frames[1]["status"] == "observed"
    assert frames[2]["units"][0]["entity_serial"] == 526


@pytest.mark.parametrize("alias_only", [False, True])
def test_entity_name_aliases_are_resolved_independently_of_unit_names(monkeypatch, alias_only):
    scene = world()
    scene.unit.fields[source.ENTITY_NAME_FIELDS[1]] = 2
    if alias_only:
        scene.unit.fields.pop(source.ENTITY_NAME_FIELDS[0])
    replay(monkeypatch, scene, [(10, 20, None)])
    unit = capture()["frames"][0]["units"][0]
    assert unit["entity_name"] == GENERIC and unit["unit_name"] == UNIT


def test_conflicting_entity_aliases_keep_raw_evidence_and_no_chosen_name(monkeypatch):
    scene = world()
    scene.unit.fields[source.ENTITY_NAME_FIELDS[1]] = 3
    replay(monkeypatch, scene, [(10, 20, None)])
    unit = capture()["frames"][0]["units"][0]
    assert unit["entity_name"] is None and unit["unit_name"] == UNIT
    assert "conflicting_entity_names" in unit["missing_reasons"]
    assert [x["value"] for x in unit["naming"]["entity_names"]] == [GENERIC, OTHER_HERO]


def test_missing_numeric_fields_are_null_with_reasons_not_zero(monkeypatch):
    scene = world()
    scene.unit.fields.pop("m_iHealth")
    scene.unit.fields.pop("CBodyComponent.m_cellX")
    replay(monkeypatch, scene, [(10, 20, None)])
    unit = capture()["frames"][0]["units"][0]
    assert unit["health"] is None and unit["x"] is None
    assert "missing_health" in unit["missing_reasons"] and "missing_x" in unit["missing_reasons"]


def test_absent_seconds_are_explicit_and_output_order_is_stable(monkeypatch):
    scene = world()
    replay(monkeypatch, scene, [(10, 20, None)])
    result = capture([(HERO, 20), (HERO, 9), (HERO, 10), (OTHER_HERO, 10)])
    assert [(x["hero"], x["t"]) for x in result["frames"]] == [
        (OTHER_HERO, 10),
        (HERO, 9),
        (HERO, 10),
        (HERO, 20),
    ]
    assert result["frames"][0]["status"] == "missing_observer"
    for frame in (result["frames"][1], result["frames"][3]):
        assert frame["status"] == "missing_frame" and frame["tick"] is None
        assert frame["units"] is None and frame["observer"] is None


@pytest.mark.parametrize(
    "problem, match",
    [
        ("duplicate_slot", "duplicate.*team-slot"),
        ("wrong_team", "disagrees.*team"),
        ("non_hero", "not a hero"),
        ("name_conflict", "ambiguous.*name"),
        ("wrong_serial", "identity mismatch"),
        ("invalid_slot", "invalid.*team-slot"),
    ],
)
def test_observer_conflicts_are_rejected(monkeypatch, problem, match):
    scene = world()
    if problem == "duplicate_slot":
        scene.resource.fields.update(roster_fields(scene.hero, index=7))
    elif problem == "wrong_team":
        scene.hero.fields["m_iTeamNum"] = 2
    elif problem == "non_hero":
        scene.hero.class_name = source.NEUTRAL_CLASS
    elif problem == "name_conflict":
        scene.hero.fields[source.ENTITY_NAME_FIELDS[1]] = 3
    elif problem == "wrong_serial":
        # Even an erroneous manager response must not defeat the explicit check.
        scene.em.find_by_handle = lambda handle: scene.hero
        scene.hero.serial += 1
    else:
        scene.resource.fields["m_vecPlayerTeamData.0006.m_iTeamSlot"] = 5
    replay(monkeypatch, scene, [(10, 20, None)])
    with pytest.raises(ValueError, match=match):
        capture()


def test_stale_selection_and_controller_do_not_supply_observer(monkeypatch):
    scene = world()
    scene.resource.fields["m_vecPlayerTeamData.0006.m_hSelectedHero"] += 1 << 14
    scene.em.entities.append(
        Entity(
            100,
            1,
            "CDOTAPlayerController",
            {
                "m_hAssignedHero": scene.hero.handle,
                "m_iPlayerID": 6,
            },
        )
    )
    replay(monkeypatch, scene, [(10, 20, None)])
    frame = capture()["frames"][0]
    assert frame["status"] == "missing_observer" and frame["observer"] is None


def test_unassigned_resource_row_does_not_conflict(monkeypatch):
    scene = world()
    scene.resource.fields.update(roster_fields(scene.hero, index=7, slot=-1))
    replay(monkeypatch, scene, [(10, 20, None)])
    assert capture()["frames"][0]["observer"]["resource_index"] == 6


@pytest.mark.parametrize("word", [-1, 1 << 64, True, 1.5])
def test_invalid_visibility_words_are_rejected(monkeypatch, word):
    scene = world()
    scene.radiant.fields["m_bNPCVisibleState.0000"] = word
    replay(monkeypatch, scene, [(10, 20, None)])
    with pytest.raises(ValueError, match="invalid team visibility word"):
        capture()


@pytest.mark.parametrize(
    "cases", [[], [(HERO, -1)], [(HERO, True)], [(HERO, 1.0)], [("", 1)], [(HERO, 1), (HERO, 1)]]
)
def test_invalid_cases_rejected_before_loading_gem(cases, monkeypatch):
    monkeypatch.setattr(source, "_runtime", lambda: pytest.fail("should not load Gem"))
    with pytest.raises(ValueError):
        source.capture_camp_evidence("x.dem", cases)


def test_parse_failure_never_returns_partial_frames(monkeypatch):
    scene = world()
    replay(monkeypatch, scene, [(10, 20, None)], parse_error=RuntimeError("truncated"))
    with pytest.raises(ValueError, match="Incomplete Gem parse"):
        capture()


@pytest.mark.parametrize("clock", [lambda tick: 9, lambda tick: None])
def test_final_clock_must_agree_with_live_endpoint(monkeypatch, clock):
    scene = world()
    replay(monkeypatch, scene, [(10, 20, None)], clock=clock)
    with pytest.raises(ValueError, match="final clock disagrees"):
        capture()


@pytest.mark.parametrize("steps", [[(10, 20, None), (9, 21, None)], [(10.5, 20, None)]])
def test_clock_backwards_or_noninteger_rejected(monkeypatch, steps):
    replay(monkeypatch, world(), steps)
    with pytest.raises(ValueError, match="clock moved backwards|integer game second"):
        capture()


@pytest.mark.parametrize("match_id", [None, 0, True, "123"])
def test_replay_identity_required(monkeypatch, match_id):
    replay(monkeypatch, world(), [(10, 20, None)], match_id=match_id)
    with pytest.raises(ValueError, match="replay identity"):
        capture()


def test_compatibility_manifest_binds_every_source_and_rejects_extra_files(tmp_path, monkeypatch):
    root = tmp_path / "gem"
    root.mkdir()
    package = root / "__init__.py"
    package.write_text("# source\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"patched": {"__init__.py": file_hash(package)}}))
    expected = file_hash(manifest)
    monkeypatch.setattr(source, "COMPAT_SHA256", expected)
    assert source.verify_compatibility(root) == expected
    package.write_text("# drift\n")
    with pytest.raises(ValueError, match="source fingerprint mismatch"):
        source.verify_compatibility(root)
    package.write_text("# source\n")
    extra = root / "extra.py"
    extra.write_text("# extra\n")
    with pytest.raises(ValueError, match="source set mismatch"):
        source.verify_compatibility(root)
    extra.unlink()
    manifest.write_text("{}")
    with pytest.raises(ValueError, match="registered Gem compatibility manifest"):
        source.verify_compatibility(root)


def test_runtime_compatibility_drift_after_parse_prevents_return(monkeypatch):
    replay(monkeypatch, world(), [(10, 20, None)])
    count = 0

    def verify(root):
        nonlocal count
        count += 1
        if count == 2:
            raise ValueError("source fingerprint mismatch")
        return source.COMPAT_SHA256

    monkeypatch.setattr(source, "verify_compatibility", verify)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        capture()
