import importlib
from pathlib import Path

import pytest


@pytest.fixture
def maps(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("outcome_perspective_map")


def test_hidden_and_future_samples_cannot_change_the_map_or_enemy_equipment(maps):
    positions = {0: (10, 11), 1: (12, 13), 2: (14, 15), 3: (16, 17)}
    tracks = {
        "carry": {"team": 2, "pos": positions.copy()},
        "other": {"team": 3, "pos": positions.copy()},
        "never": {"team": 3, "pos": positions.copy()},
    }
    labels = {k: k for k in tracks}
    states = {
        t: {h: {"life_state": 0, "items": {"0": f"{h}-{t}"}} for h in tracks} for t in range(4)
    }
    seen = {("other", 2): [0, 1, 3], ("carry", 3): [2]}
    wards = [
        dict(type="observer", team=2, x=11, y=13, start=1, end=20),
        dict(type="sentry", team=3, x=14, y=16, start=2, end=10),
    ]

    def at(hero, time, deaths=None):
        return maps.project(tracks, seen, states, deaths or {}, wards, hero, time, labels)

    visible = at("carry", 1)
    assert {o["hero"] for o in visible["markers"] if o["side"] == "enemy"} == {"other"}
    hidden = at("carry", 2)
    assert [m["hero"] for m in hidden["markers"]] == ["carry"]
    enemies = {e["hero"]: e for e in hidden["enemies"]}
    assert enemies["other"]["trail"] == [[0, 10, 11], [1, 12, 13]]
    assert enemies["never"]["last_seen"] is None
    equipment = {e["hero"]: e for e in hidden["equipment"]}
    assert equipment["other"]["items"] == {"0": "other-1"}
    assert equipment["never"]["items"] is None
    assert hidden["wards"] == [dict(type="observer", pos=[11, 13])]
    for h, seconds in (("other", [2, 3]), ("never", [0, 1, 2, 3])):
        for t in seconds:
            tracks[h]["pos"][t] = (987, 654)
            states[t][h]["items"] = {"0": "hidden item"}
    assert at("carry", 2) == hidden

    reverse = at("other", 2)
    assert {m["hero"]: m["side"] for m in reverse["markers"]} == {
        "other": "self",
        "carry": "enemy",
        "never": "ally",
    }
    assert reverse["wards"] == [dict(type="sentry", pos=[14, 16])]
    assert at("carry", 3)["enemies"][1]["trail"] == [[3, 987, 654]]
    # A known death invalidates sightings from the previous life, including after respawn.
    states[2]["other"]["life_state"] = 2
    for t in (2, 3):
        seen["other", 2] = [0, 1]
        e = next(e for e in at("carry", t, {"other": [2]})["enemies"] if e["hero"] == "other")
        assert e["dead"] is (t == 2)
        assert e["last_seen"] is None and e["trail"] == []


def test_reserved_identity_is_refused_before_source_reads(maps, tmp_path):
    mid = next(i for i in range(1, 100) if maps.is_holdout(i))
    with pytest.raises(ValueError, match="保留"):
        maps.generate(tmp_path / str(mid) / "match-report.md", tmp_path / "inputs")


def test_dead_hero_team_still_sees_allies_an_enemy_and_last_sighting(maps):
    tracks = {
        "self": {"team": 2, "pos": {2: (99, 99)}},
        "ally": {"team": 2, "pos": {1: (10, 20)}},
        "visible": {"team": 3, "pos": {1: (30, 40)}},
        "hidden": {"team": 3, "pos": {0: (5, 6), 1: (999, 999)}},
    }
    states = {1: {k: {"life_state": 0, "items": {}} for k in tracks}}
    states[1]["self"]["life_state"] = 2
    result = maps.project(
        tracks,
        {("visible", 2): [1], ("hidden", 2): [0]},
        states,
        {"self": [1]},
        [],
        "self",
        1,
        {k: k for k in tracks},
    )
    assert "unavailable" not in result and result["self_status"] == "已阵亡"
    assert [(m["hero"], m["pos"]) for m in result["markers"]] == [
        ("ally", (10, 20)),
        ("visible", (30, 40)),
    ]
    assert result["enemies"][0]["trail"] == [[0, 5, 6]]
