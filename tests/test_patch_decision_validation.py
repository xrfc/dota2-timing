import pytest
from test_patch_decision_view import REF, capture

from dota_items.data.patch_decision_validation import _check_rows, audit_decision_views
from dota_items.data.patch_decision_view import VisionDecisionIndex


def test_full_queries_and_nontrivial_hidden_future_mutations_preserve_known_view():
    doc = capture()
    index = VisionDecisionIndex(doc, exact_patch="7.42", source_ref=REF)
    result = audit_decision_views(doc, index, source_ref=REF, perturbation_time=0.8)
    assert result["counts"]["exact_packet_queries"] == 4
    assert result["counts"]["strict_cutoff_queries"] == 8
    assert result["perturbation"]["future_state_rows_changed"] > 0
    assert all(result["perturbation"]["hidden_state_rows_changed"].values())
    assert result["perturbation"]["future_and_hidden_known_views_unchanged"] is True


def test_independent_audit_catches_a_projector_that_snaps_forward():
    doc = capture()
    original = VisionDecisionIndex(doc, exact_patch="7.42", source_ref=REF)

    class BadIndex:
        def at(self, **kwargs):
            kwargs["game_time"] = max(1.25, kwargs["game_time"])
            kwargs["replay_tick"] = max(60, kwargs["replay_tick"])
            return original.at(**kwargs)

    with pytest.raises(ValueError, match="Exact packet query"):
        audit_decision_views(doc, BadIndex(), source_ref=REF)


def test_independent_check_rejects_waiting_friend_and_unknown_roster_slot():
    doc = capture()
    index = VisionDecisionIndex(doc, exact_patch="7.42", source_ref=REF)
    frame = doc["frames"][0]
    known = index.at(
        game_time=frame["game_time"], replay_tick=frame["tick"], observer_team=2, max_age_seconds=1
    )["known_view"]
    doc["states"][0][7] = True
    with pytest.raises(ValueError, match="spawn evidence"):
        _check_rows(doc, frame, known, 2)
    doc["states"][0][7] = False
    known["friendly_heroes"].append({"player_id": 5, "status": "unknown", "secret": "hidden"})
    with pytest.raises(ValueError, match="roster slots"):
        _check_rows(doc, frame, known, 2)
