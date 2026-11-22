import gzip
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def labels(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("outcome_labels")


def test_resource_boundaries_and_death_cost(labels):
    states = {
        t: {"level": 17, "player_id": 2, "cash": 100, "life_state": 0} for t in range(106, 121)
    }
    states[105] = {"cash": 999}
    states[120]["cash"] = 80
    for t in range(118, 121):
        states[t]["life_state"] = 2
    xp = {2: {105: 1, 106: 1000, 120: 1061, 121: 2000}}
    values, reasons = labels.window_labels(100, 1, states, xp)
    assert values == {"gold": -20, "xp": 61, "dead_seconds": 3}
    assert reasons == {}
    states[120]["level"] = 18
    del states[117]
    values, reasons = labels.window_labels(100, 1, states, xp)
    assert values == {"gold": -20, "xp": None, "dead_seconds": None}
    assert set(reasons) == {"xp", "dead_seconds"}
    states[120]["cash"] = None
    assert labels.window_labels(100, 1, states, xp)[0]["gold"] is None


def test_xp_reader_rejects_ambiguous_seconds_and_wrong_match(labels, tmp_path):
    player = {
        "player_slot": 128,
        "economy_log": [
            {"time": 6, "xp_progress": 101},
            {"time": 6, "xp_progress": 105},
            {"time": 20, "xp_progress": 160},
        ],
    }
    path = tmp_path / "sample.gz"
    with gzip.open(path, "wt") as stream:
        json.dump({"match_id": 10, "duration": 30, "players": [player]}, stream)
    assert labels.xp_endpoints(path, 10, {5: {6, 20}}) == {5: {6: None, 20: 160}}
    with pytest.raises(ValueError, match="match"):
        labels.xp_endpoints(path, 11, {5: {6, 20}})


def test_censored_rows_do_not_get_zero_defaults(labels):
    row = {"t": 100, "hero": "h", "death": None, "outcome_eligible": False}
    out = labels.enrich([row], {}, {})[0]
    assert all(out[key] is None for key in labels.TARGETS)
    assert row.keys() == {"t", "hero", "death", "outcome_eligible"}
