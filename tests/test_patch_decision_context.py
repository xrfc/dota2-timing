from copy import deepcopy

import pytest

from dota_items.data.patch_decision_context import DecisionContextIndex


class View:
    def __init__(self, visible=()):
        self.visible = list(visible)

    def at(self, **kwargs):
        return {
            "schema": "patch-decision-view/1",
            "exact_patch": "7.42",
            "training_allowed": False,
            "action_review_allowed": False,
            "known_view": {**kwargs, "visible_entities": deepcopy(self.visible)},
            "provenance": {},
            "limits": [],
        }


def camp_assets():
    return {
        "schema": "patch-camp-assets/1",
        "exact_patch": "7.42",
        "action_review_allowed": False,
        "training_allowed": False,
        "camps": [
            {
                "camp_id": "camp",
                "rectangle": {"min_x": 0, "min_y": 0, "max_x": 100, "max_y": 100},
                "type": "medium",
                "activation_batches": [{"game_time": 900}],
            }
        ],
    }


def query(view, assets=None):
    return DecisionContextIndex(
        view,
        camp_assets() if assets is None else assets,
        exact_patch="7.42",
        map_source_ref={"path": "/map", "sha256": "a" * 64},
    ).at(game_time=100, replay_tick=3000, observer_team=2, max_age_seconds=1)


def test_no_visible_entities_never_means_empty_camp_or_dead_objective():
    known = query(View())["known_view"]
    camp = known["camp_observations"][0]
    assert camp["observed_neutral_entities_in_trigger"] == []
    assert all(
        camp[k] is None
        for k in ("current_stock", "current_phase", "blocked", "control_team", "strategic_region")
    )
    assert known["objectives"]["roshan"]["status"] == "current_state_unknown"


def test_visible_neutral_geometry_does_not_establish_membership_or_stock():
    entity = {
        "identity": {"entity_index": 3, "entity_serial": 4},
        "class_name": "CDOTA_BaseNPC_Creep_Neutral",
        "npc_name": "npc_dota_neutral_test",
        "position": {"x": 50, "y": 50},
    }
    known = query(View([entity]))["known_view"]
    camp = known["camp_observations"][0]
    assert camp["observed_neutral_entities_in_trigger"] == [entity]
    assert camp["membership_inferred"] is False
    assert camp["current_stock"] is None
    outside = deepcopy(entity)
    outside["position"]["x"] = 101
    assert (
        query(View([outside]))["known_view"]["camp_observations"][0][
            "observed_neutral_entities_in_trigger"
        ]
        == []
    )


def test_future_camp_types_and_activation_batches_cannot_change_known_view():
    assets = camp_assets()
    original = query(View(), assets)["known_view"]
    assets["camps"][0].update(
        type="ancient", activation_batches=[{"game_time": 6000, "units": [1, 2]}], control_team=3
    )
    assert query(View(), assets)["known_view"] == original


def test_observed_live_objective_has_no_invented_respawn_deadline():
    entity = {
        "identity": {"entity_index": 7, "entity_serial": 3},
        "class_name": "CDOTA_Unit_Roshan",
        "npc_name": "npc_dota_roshan",
        "position": {"x": -100, "y": -100},
    }
    obj = query(View([entity]))["known_view"]["objectives"]["roshan"]
    assert obj["status"] == "observed_live_at_sample"
    assert obj["observed_live_entities"] == [entity]
    assert obj["respawn_deadline"] is None


@pytest.mark.parametrize(
    "changed",
    ["exact_patch", "training_allowed", "action_review_allowed", "rectangle", "duplicate"],
)
def test_wrong_version_purpose_and_geometry_rejected(changed):
    assets = camp_assets()
    if changed == "rectangle":
        assets["camps"][0]["rectangle"]["max_x"] = float("nan")
    elif changed == "duplicate":
        assets["camps"].append(deepcopy(assets["camps"][0]))
    else:
        assets[changed] = "7.42a" if changed == "exact_patch" else True
    with pytest.raises(ValueError):
        query(View(), assets)


def test_map_reference_cannot_be_changed_through_constructor_or_result_alias():
    ref = {"path": "/map.json", "sha256": "a" * 64}
    index = DecisionContextIndex(View(), camp_assets(), exact_patch="7.42", map_source_ref=ref)
    kwargs = dict(game_time=100, replay_tick=3000, observer_team=2, max_age_seconds=1)
    ref["sha256"] = "b" * 64
    first = index.at(**kwargs)
    first["provenance"]["map_geometry"]["sha256"] = "c" * 64
    assert index.at(**kwargs)["provenance"]["map_geometry"]["sha256"] == "a" * 64


@pytest.mark.parametrize(
    "ref", [{"path": "relative", "sha256": "a" * 64}, {"path": "/absolute", "sha256": "invalid"}]
)
def test_invalid_map_reference_rejected(ref):
    with pytest.raises(ValueError, match="absolute map source"):
        DecisionContextIndex(View(), camp_assets(), exact_patch="7.42", map_source_ref=ref)


def test_composition_rejects_a_view_that_grants_training_permission():
    class BadView(View):
        def at(self, **kwargs):
            value = super().at(**kwargs)
            value["training_allowed"] = True
            return value

    with pytest.raises(ValueError, match="version mismatch"):
        query(BadView())
