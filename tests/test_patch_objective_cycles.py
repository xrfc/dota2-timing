import copy
from types import SimpleNamespace

import pytest
from test_patch_objectives import REFS, capture, record, row

from dota_items.data.patch_objective_cycles import analyze_objective_evidence
from dota_items.sources.map_objective_evidence import ObjectiveEvents


def fixture(replacement=False):
    cap = capture()
    cap.update(
        schema="map-objective-evidence/1",
        combat_deaths=[],
        chat_events=[],
        message_coverage={"combat_entries": 12},
    )
    first = [row(tick=0), row(tick=300, life=1)]
    if replacement:
        cap["objectives"] = [record(first, "roshan"), record([row(tick=600, serial=2)], "roshan")]
    else:
        cap["objectives"] = [record(first + [row(tick=600)], "roshan")]
    cap["objective_frames"] = [
        {"tick": 270, "game_time": 9.0, "roshan": [row(tick=270)], "tormentor": []},
        {"tick": 330, "game_time": 11.0, "roshan": [], "tormentor": []},
        {"tick": 570, "game_time": 19.0, "roshan": [], "tormentor": []},
    ]
    return cap


def analyze(cap, count=1):
    return analyze_objective_evidence(
        [cap],
        map_documents={"mapdata.json": {"data": {"npc_dota_roshan_spawner": [{}] * count}}},
        exact_patch="7.42",
        source_refs=REFS,
    )["matches"][0]["objectives"]["roshan"]


def test_same_identity_cycle_retains_bounded_elapsed_time():
    result = analyze(fixture())
    cycle = result["observed_cycles"][0]
    assert cycle["association"] == "same_entity_identity"
    assert cycle["duration_interval"]["upper_seconds"] == 11
    assert not cycle["timer_rule_validated"]
    assert result["death_channel_status"] == "channel_disagreement_requires_review"


def test_new_serial_can_pair_only_with_singleton_map_and_inactive_gap():
    cap = fixture(True)
    result = analyze(cap)
    assert (
        result["observed_cycles"][0]["association"]
        == "single_map_spawner_and_observed_inactive_gap"
    )
    assert not analyze(cap, count=2)["observed_cycles"]
    cap["objective_frames"] = cap["objective_frames"][:1]
    assert not analyze(cap)["observed_cycles"]


@pytest.mark.parametrize("variant", ["live_gap", "unknown_gap", "overlap"])
def test_inconclusive_or_simultaneous_objects_do_not_pair(variant):
    cap = fixture(True)
    frame = cap["objective_frames"][1]
    if variant == "live_gap":
        frame["roshan"] = [row(tick=330)]
    elif variant == "unknown_gap":
        sample = row(tick=330)
        sample["raw_fields"]["m_lifeState"] = None
        frame["roshan"] = [sample]
    else:
        frame["roshan"] = [row(tick=330), row(tick=330, serial=2)]
    assert not analyze(cap)["observed_cycles"]


def test_no_future_activation_is_censored_not_a_failed_rule():
    cap = fixture()
    cap["objectives"][0]["observations"].pop()
    result = analyze(cap)
    assert result["respawn_status"] == "no_positive_sample"
    assert result["unresolved_deaths"][0]["reason"] == "right_censored_no_later_activation"
    assert not result["timer_rule_validated"]


def test_combat_pickup_and_delivery_time_cannot_invent_a_cycle():
    cap = fixture()
    cap["objectives"] = []
    cap["chat_events"] = [{"type": 8, "delivery_tick": 300}]
    cap["combat_deaths"] = [
        {
            "kind": "roshan",
            "target_name": "npc_dota_roshan",
            "delivery_tick": 300,
            "timestamp_s": 100.0,
            "combat_game_time_s": 10,
            "delivery_game_time": 12.0,
            "will_reincarnate": False,
        }
    ]
    result = analyze(cap)
    assert not result["observed_cycles"]
    assert result["death_channel_status"] == "channel_disagreement_requires_review"


def test_collector_keeps_bulk_event_and_delivery_times_separate():
    parser = SimpleNamespace(
        tick=390, post_game_tick=400, game_clock=SimpleNamespace(game_time_at=lambda t: t / 30)
    )
    collector = ObjectiveEvents(parser)
    entry = SimpleNamespace(
        log_type="DEATH",
        target_name="npc_dota_roshan",
        tick=390,
        timestamp_s=100.2,
        game_time_s=10,
        source="s2_bulk",
        will_reincarnate=False,
    )
    collector.on_combat(entry)
    parser.tick = 450
    collector.on_combat(entry)
    collector.on_chat(SimpleNamespace(type=8), 390)
    result = collector.result()
    assert len(result["combat_deaths"]) == 1
    assert result["combat_deaths"][0]["combat_game_time_s"] == 10
    assert result["combat_deaths"][0]["delivery_game_time"] == 13


def test_wrong_patch_and_invalid_combat_event_rejected():
    cap = fixture()
    bad = copy.deepcopy(cap)
    bad["patch"] = "7.42a"
    with pytest.raises(ValueError):
        analyze(bad)
    cap["combat_deaths"] = [
        {"kind": "roshan", "target_name": "npc_dota_miniboss", "delivery_tick": 300}
    ]
    with pytest.raises(ValueError):
        analyze(cap)


@pytest.mark.parametrize("start,end", [(600, 610), (590, 610)])
def test_between_frame_lifecycle_overlap_does_not_make_a_respawn(start, end):
    cap = fixture(True)
    cap["objectives"].append(
        record([row(tick=start, serial=3), row(tick=end, serial=3, life=1)], "roshan")
    )
    cap["objective_frames"].append(
        {"tick": 630, "game_time": 21.0, "roshan": [row(tick=630, serial=2)], "tormentor": []}
    )
    result = analyze(cap)
    assert not any(c["death"]["upper_tick"] == 300 for c in result["observed_cycles"])


def test_same_identity_live_frame_cannot_be_ignored_between_transition_bounds():
    cap = fixture()
    cap["objective_frames"][1]["roshan"] = [row(tick=330)]
    assert not analyze(cap)["observed_cycles"]


def test_short_cycle_between_frames_is_paired_before_later_activation():
    cap = fixture(True)
    cap["objectives"].append(
        record([row(tick=400, serial=3), row(tick=410, serial=3, life=1)], "roshan")
    )
    result = analyze(cap)
    first = next(c for c in result["observed_cycles"] if c["death"]["upper_tick"] == 300)
    assert first["next_activation"]["entity"] == [1, 3]
