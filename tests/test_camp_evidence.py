"""Information-boundary tests for decision-time camp evidence."""

from copy import deepcopy

import pytest

from dota_items.data.camp_evidence import project_camp_evidence, project_frame


def unit(index=12, visible="visible"):
    return dict(
        entity_index=index,
        entity_serial=42,
        unit_name="npc_dota_neutral_centaur_khan",
        entity_name="npc_dota_creep_neutral",
        class_name="CDOTA_BaseNPC_Creep_Neutral",
        team=4,
        x=0.0,
        y=100.5,
        health=0,
        max_health=1100,
        life_state=0,
        visibility=dict(radiant=visible, dire="hidden"),
        ownership=dict(owner_handle=123),
        missing_reasons=["omniscient_only_reason"],
        future_death_tick=9999,
    )


def frame():
    return dict(
        hero="npc_dota_hero_sven",
        t=100,
        tick=3000,
        net_tick=4000,
        status="observed",
        observer=dict(team=2, slot=1, resource_index=6),
        units=[unit()],
        action="move_to_jungle",
        fold=4,
        future_dead=True,
    )


def capture(frames):
    return dict(
        schema="gem-camp-evidence/1",
        match_id=123,
        sampling="first_tick_start_before_entity_updates",
        frames=frames,
        compat_manifest_sha256="raw_only",
        future="not_public",
    )


def test_exact_public_whitelist_preserves_zero_and_input():
    raw = frame()
    before = deepcopy(raw)
    public = project_frame(raw)
    assert raw == before
    assert public == dict(
        hero="npc_dota_hero_sven",
        t=100,
        tick=3000,
        net_tick=4000,
        status="observed",
        observer={"team": 2},
        stock_complete=False,
        empty_confirmed=None,
        camp_id=None,
        units=[
            dict(
                entity_index=12,
                entity_serial=42,
                unit_name="npc_dota_neutral_centaur_khan",
                team=4,
                x=0.0,
                y=100.5,
                health=0,
                max_health=1100,
                life_state=0,
                missing_reasons=[],
            )
        ],
    )


def test_hidden_unknown_count_identity_and_future_are_noninterfering():
    raw = frame()
    expected = project_frame(raw)
    for visibility in ("hidden", "unknown", None, True, 1, "VISIBLE"):
        raw["units"].append(unit(index=99, visible=visibility))
    assert project_frame(raw) == expected
    for item in raw["units"][1:]:
        item.update(
            entity_index=None,
            entity_serial=-1,
            health=-99,
            x=None,
            unit_name="secret",
            ownership={"new_owner": 100},
            future_dead=True,
        )
    raw["units"] += [{}, None, "malformed but not visible"]
    raw.update(hidden_total=900, unknown_visibility_count=100, future_dead=False)
    raw["units"][0].update(
        ownership={"new_owner": 900},
        future_death_tick=1,
        missing_reasons=["secret_future"],
        birth_tick=-100,
    )
    raw["units"][0]["visibility"]["dire"] = "visible"
    assert project_frame(raw) == expected


def test_observer_team_selects_only_its_own_visibility():
    raw = frame()
    raw["observer"]["team"] = 3
    raw["units"].append(unit(13, "hidden"))
    raw["units"][1]["visibility"]["dire"] = "visible"
    public = project_frame(raw)
    assert [u["entity_index"] for u in public["units"]] == [13]
    assert public["observer"] == {"team": 3}


@pytest.mark.parametrize(
    "status,ticks",
    [
        ("missing_frame", (None, None)),
        ("missing_frame", (3000, 4000)),
        ("missing_observer", (3000, 4000)),
    ],
)
def test_missing_frames_remain_unknown_and_hide_raw_units(status, ticks):
    raw = frame()
    raw.update(status=status, observer=None, tick=ticks[0], net_tick=ticks[1])
    public = project_frame(raw)
    assert public["status"] == status
    assert public["observer"] is None
    assert public["units"] == []
    assert public["stock_complete"] is False
    assert public["empty_confirmed"] is None
    assert public["camp_id"] is None


def test_observed_zero_visible_is_not_empty_camp():
    raw = frame()
    raw["units"][0]["visibility"]["radiant"] = "hidden"
    public = project_frame(raw)
    assert public["status"] == "observed" and public["units"] == []
    assert public["empty_confirmed"] is None and public["stock_complete"] is False


@pytest.mark.parametrize("value", [None, {}, 0, ""])
def test_observed_requires_explicit_unit_list(value):
    raw = frame()
    raw["units"] = value
    with pytest.raises(ValueError, match="unit list"):
        project_frame(raw)
    raw.pop("units")
    with pytest.raises(ValueError, match="unit list"):
        project_frame(raw)


@pytest.mark.parametrize(
    "changes",
    [dict(team=True), dict(team=4), dict(slot=5), dict(slot=True), dict(resource_index=30)],
)
def test_invalid_observer_rejected(changes):
    raw = frame()
    raw["observer"].update(changes)
    with pytest.raises(ValueError, match="observer"):
        project_frame(raw)


def test_null_and_invalid_visible_fields_do_not_become_zero_or_false():
    raw = frame()
    raw["units"][0].update(
        unit_name=None,
        x=None,
        y=float("inf"),
        health=None,
        max_health=True,
        life_state=False,
        team=-1,
    )
    visible = project_frame(raw)["units"][0]
    assert visible["team"] == -1  # Preserve raw numeric values; infer no owner or life.
    assert {
        key: visible[key] for key in ("unit_name", "x", "y", "health", "max_health", "life_state")
    } == dict.fromkeys(("unit_name", "x", "y", "health", "max_health", "life_state"))
    assert visible["missing_reasons"] == [
        "missing_unit_name",
        "missing_x",
        "invalid_y",
        "missing_health",
        "invalid_max_health",
        "invalid_life_state",
    ]


def test_duplicate_visible_identity_rejected_but_hidden_duplicate_ignored():
    raw = frame()
    raw["units"].append(unit(12, "hidden"))
    assert len(project_frame(raw)["units"]) == 1
    raw["units"][1]["visibility"]["radiant"] = "visible"
    with pytest.raises(ValueError, match="duplicate visible"):
        project_frame(raw)


def test_capture_has_only_public_fields_and_stable_order():
    raw = frame()
    later = deepcopy(raw)
    later["t"] += 1
    public = project_camp_evidence(capture([later, raw]))
    assert set(public) == {"schema", "source_schema", "match_id", "sampling", "frames"}
    assert [f["t"] for f in public["frames"]] == [100, 101]
    with pytest.raises(ValueError, match="duplicate camp observation"):
        project_camp_evidence(capture([raw, raw]))


@pytest.mark.parametrize(
    "changes",
    [dict(schema="wrong"), dict(match_id=True), dict(sampling="last_tick"), dict(match_id=0)],
)
def test_invalid_capture_contract(changes):
    raw = capture([frame()])
    raw.update(changes)
    with pytest.raises(ValueError):
        project_camp_evidence(raw)


def test_inconsistent_missing_frame_ticks_fail():
    raw = frame()
    raw.update(status="missing_frame", observer=None, net_tick=None)
    with pytest.raises(ValueError, match="inconsistent tick"):
        project_frame(raw)
