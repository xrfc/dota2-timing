import pytest

from dota_items.data.purchase_observation import observe_purchases


def test_half_open_window_and_duplicate_source_refs():
    result = observe_purchases(
        {
            "purchase_log": [
                {"key": "manta", "time": -1},
                {"key": "manta", "time": 0},
                {"key": "manta", "time": 1799},
                {"key": "manta", "time": 1799},
                {"key": "bfury", "time": 1800},
            ]
        },
        ["manta", "bfury"],
    )
    assert result["items"][0]["log_presence"] == 1
    assert result["items"][0]["event_refs"] == [
        "purchase_log[1]",
        "purchase_log[2]",
        "purchase_log[3]",
    ]
    assert result["items"][1]["log_presence"] == 0
    assert result["has_event_at_or_after_window_end"]
    assert not result["coverage_verified"]
    assert all(
        i["behavior_label"] is None and not i["behavior_label_mask"] for i in result["items"]
    )


@pytest.mark.parametrize("value", [None, {}, "missing"])
def test_missing_log_is_not_zero(value):
    r = observe_purchases({"purchase_log": value}, ["bfury"])
    assert r["items"][0]["log_presence"] is None
    assert not r["items"][0]["log_presence_mask"]


def test_empty_log_is_only_source_absence():
    r = observe_purchases({"purchase_log": []}, ["bfury"])
    assert r["items"][0]["log_presence"] == 0
    assert r["items"][0]["behavior_label"] is None
    assert not r["coverage_verified"]


@pytest.mark.parametrize(
    "event", [None, {}, {"key": "bfury", "time": True}, {"key": "bfury", "time": float("nan")}]
)
def test_invalid_events_mask_source_target(event):
    r = observe_purchases({"purchase_log": [event, {"key": "bfury", "time": 1}]}, ["bfury"])
    assert r["invalid_event_indices"] == [0]
    assert r["items"][0]["log_presence"] is None
    assert r["items"][0]["event_times"] == [1]


def test_final_inventory_and_aggregates_cannot_fill_missing_log():
    r = observe_purchases(
        {"item_0": 145, "purchase": {"bfury": 1}, "purchase_time": {"bfury": 600}}, ["bfury"]
    )
    assert r["items"][0]["log_presence"] is None


def test_duplicate_candidate_rejected():
    with pytest.raises(ValueError):
        observe_purchases({}, ["bfury", "bfury"])
