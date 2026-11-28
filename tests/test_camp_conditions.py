from copy import deepcopy

import pytest

from dota_items.data.camp_conditions import SAMPLING, summarize_camp_evidence


def unit(index=1, **values):
    row = dict(
        entity_index=index,
        entity_serial=3,
        unit_name="npc_dota_neutral_test",
        team=4,
        x=16000.0,
        y=17000.0,
        health=100,
        max_health=200,
        life_state=0,
        missing_reasons=[],
    )
    row.update(values)
    row["missing_reasons"] = [f"missing_{k}" for k, v in row.items() if v is None]
    return row


def public(*units):
    return dict(
        schema="camp-evidence/1",
        source_schema="gem-camp-evidence/1",
        match_id=123,
        sampling=SAMPLING,
        frames=[
            dict(
                hero="npc_dota_hero_test",
                t=100,
                tick=3000,
                net_tick=3100,
                status="observed",
                observer={"team": 2},
                units=list(units),
                stock_complete=False,
                empty_confirmed=None,
                camp_id=None,
            )
        ],
    )


def describe(document):
    return summarize_camp_evidence(document)["frames"][0]


def test_life_and_team_are_observations_not_camp_stock():
    doc = public(
        unit(),
        unit(2, life_state=2, health=0),
        unit(3, team=2),
        unit(4, team=3),
        unit(5, life_state=1, health=0),
        unit(6, life_state=None),
        unit(7, health=0),
        unit(8, team=None),
        unit(9, life_state=9),
    )
    before = deepcopy(doc)
    frame = describe(doc)
    assert frame["facts"] == dict(
        visible_units=9,
        alive=4,
        not_alive=2,
        life_unknown=2,
        life_conflict=1,
        alive_neutral_team=1,
        alive_player_team=2,
        alive_other_or_unknown_team=1,
        alive_neutral_team_visible_health_sum=100,
    )
    assert all(c["value"] is None for c in frame["conditions"].values())
    assert frame["empty_confirmed"] is None and frame["stock_complete"] is False
    assert frame["camp_id"] is None
    assert doc == before


def test_zero_visible_is_different_from_unavailable():
    observed = describe(public())
    assert observed["facts"]["visible_units"] == 0
    assert observed["conditions"]["inventory"]["value"] is None
    for status in ("missing_frame", "missing_observer"):
        doc = public()
        doc["frames"][0].update(status=status, observer=None)
        missing = describe(doc)
        assert missing["facts"] is None
        assert all(
            "observation_unavailable" in v["missing_evidence"]
            for v in missing["conditions"].values()
        )


def test_unknown_health_is_not_zero_or_alive():
    frame = describe(public(unit(health=None)))
    assert frame["facts"]["life_unknown"] == 1
    assert frame["facts"]["alive_neutral_team"] == 0
    assert frame["units"][0]["issues"] == ["health_unavailable"]


def test_summon_name_does_not_prove_spawn_membership():
    frame = describe(public(unit(unit_name="npc_dota_dark_troll_warlord_skeleton_warrior")))
    assert frame["facts"]["alive_neutral_team"] == 1
    assert frame["conditions"]["camp_membership"]["status"] == "unconfirmed"


def test_future_frame_cannot_fill_present_missing_health():
    doc = public(unit(health=None))
    before = describe(doc)
    future = deepcopy(public(unit())["frames"][0])
    future.update(t=101, tick=3030, net_tick=3130)
    doc["frames"].append(future)
    assert summarize_camp_evidence(doc)["frames"][0] == before


def test_unit_order_is_irrelevant():
    first = unit(4)
    second = unit(5, entity_serial=5)
    assert describe(public(first, second)) == describe(public(second, first))
    with pytest.raises(ValueError, match="duplicate unit"):
        describe(public(first, first))


def test_same_frame_index_conflict_is_rejected_even_with_new_serial():
    with pytest.raises(ValueError, match="duplicate unit index"):
        describe(public(unit(4), unit(4, entity_serial=5)))


def test_index_reuse_is_allowed_across_frames():
    doc = public(unit(4))
    later = deepcopy(public(unit(4, entity_serial=5))["frames"][0])
    later.update(t=101, tick=3030, net_tick=3130)
    doc["frames"].append(later)
    result = summarize_camp_evidence(doc)["frames"]
    assert [f["units"][0]["entity_serial"] for f in result] == [3, 5]
    assert [f["facts"]["visible_units"] for f in result] == [1, 1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("team", True),
        ("health", False),
        ("life_state", False),
        ("entity_index", True),
        ("x", float("nan")),
        ("y", float("inf")),
        ("unit_name", ""),
    ],
)
def test_malformed_public_facts_are_rejected(field, value):
    with pytest.raises(ValueError):
        describe(public(unit(**{field: value})))


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", 12),
        ("visibility", {"dire": "hidden"}),
        ("future_death", True),
    ],
)
def test_nonpublic_unit_fields_are_rejected(field, value):
    with pytest.raises(ValueError, match="public unit"):
        describe(public(unit(**{field: value})))


@pytest.mark.parametrize(
    "field,value",
    [
        ("stock_complete", True),
        ("empty_confirmed", True),
        ("camp_id", 1),
        ("action", "stay_lane"),
        ("t", True),
        ("tick", False),
    ],
)
def test_fabricated_camp_claims_or_future_metadata_are_rejected(field, value):
    doc = public(unit())
    doc["frames"][0][field] = value
    with pytest.raises(ValueError):
        describe(doc)


def test_missing_reason_must_match_null_fields():
    row = unit(health=None)
    row["missing_reasons"] = []
    with pytest.raises(ValueError, match="inexact missing"):
        describe(public(row))


def test_unavailable_frame_must_not_expose_units():
    doc = public(unit())
    doc["frames"][0].update(status="missing_observer", observer=None)
    with pytest.raises(ValueError, match="unavailable frame"):
        describe(doc)


def test_missing_tick_pair_and_duplicate_opportunity():
    doc = public()
    doc["frames"][0].update(status="missing_frame", observer=None, tick=None, net_tick=None)
    assert describe(doc)["facts"] is None
    doc["frames"][0]["net_tick"] = 12
    with pytest.raises(ValueError, match="tick identity"):
        describe(doc)
    doc = public()
    doc["frames"].append(deepcopy(doc["frames"][0]))
    with pytest.raises(ValueError, match="duplicate opportunity"):
        describe(doc)
