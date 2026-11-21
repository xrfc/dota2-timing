from dota_items.data.farm_value import farm_comparison


def test_observed_farm_and_conditional_resources():
    match = {
        "tracks": {"h": {"team": 2, "pos": {100: [0, 0]}}},
        "fronts": {
            100: {
                "radiant_mid": {"count": 1, "front": [0, 200]},
                "dire_mid": {"count": 2, "front": [1, 0]},
            }
        },
        "last": 115,
    }
    camps = [{"x": 0, "y": 100, "id": 2}]
    a, x = farm_comparison(match, "h", 100, [80, 100, 106, 106, 116], [100, 101], camps)
    b, y = farm_comparison(match, "h", 100, [80, 100], [100], camps)
    assert a == b and x != y
    assert a["recent_20s"] == {"lane": 1, "neutral": 1}
    assert a["nearest_allied_wave"] == {"lane": "mid", "distance": 200}
    assert a["camp_options"] == [{"id": 2, "distance": 100}]
    assert x["next_6s"] == {"lane": 2, "neutral": 1, "observed_seconds": 6}
    assert x["next_20s"] == {"lane": 2, "neutral": 1, "observed_seconds": 15}
