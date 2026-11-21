from dota_items.data.catch_threat import catch_comparison


def test_only_recent_sight_and_main_inventory_contribute():
    frame = {
        "t": 72,
        "markers": [{"side": "self", "pos": [0, 0]}],
        "enemies": [
            {"hero": "a", "distance": 350, "last_seen": 72},
            {"hero": "b", "distance": None, "last_seen": 70, "trail": [[70, 2100, 0]]},
            {"hero": "c", "distance": None, "last_seen": 44, "trail": [[44, 0, 0]]},
        ],
        "equipment": [
            {
                "hero": "a",
                "ally": False,
                "observed": 72,
                "items": {"0": "item_orchid", "7": "item_basher"},
            },
            {"hero": "b", "ally": False, "observed": 71, "items": {"0": "item_sheepstick"}},
        ],
    }
    result = catch_comparison({"history": [frame], "ready_names": ["item_manta"]})
    assert result["pair"] == ["a", "b"]
    assert [c["seconds"] for c in result["candidates"]] == [1, 4]
    assert [c["controls"] for c in result["candidates"]] == [["item_orchid"], []]
    assert result["excluded"] == ["c"] and result["self_response"] == ["item_manta"]
