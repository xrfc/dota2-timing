import importlib
from pathlib import Path

import pytest


@pytest.fixture
def domains(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("outcome_domains")


def test_jungle_and_support_actions_are_limited_to_six_seconds(domains):
    track = {t: [100 * t, 0] for t in range(8)}
    assert domains.jungle_action(track, 0, (0, 0), [7]) == "leave_camp"
    assert domains.jungle_action(track, 0, (0, 0), [6]) == "unknown"
    assert domains.jungle_action(track, 0, (600, 0), [6]) == "continue_jungle"
    assert domains.support_action(track, 0, (1200, 0)) == "approach"
    assert domains.support_action(track, 0, (-600, 0)) == "stay"
    track[3] = [1800, 0]
    assert domains.support_action(track, 0, (1200, 0)) == "unknown"


def test_support_arrival_checks_actual_ally_position_at_later_hit(domains):
    own = {i: [0, 0] for i in range(7, 21)}
    ally = {7: [400, 0], 12: [800, 0]}
    assert domains.arrived(own, ally, 0, [6, 7, 21], {}) == 1
    assert domains.arrived(own, ally, 0, [6, 12], {}) == 0
    assert domains.arrived(own, ally, 0, [19], {}) is None
    assert domains.arrived({}, ally, 0, [7], {7: {"life_state": 2}}) == 0


def test_support_starts_after_role_inference_and_respects_spacing(domains):
    pos = {s: [0, 0] for s in range(895, 1050)}
    tracks = {"h": {"team": 2, "pos": pos}, "a": {"team": 2, "pos": {t: [1000, 0] for t in pos}}}
    damage = {895: {"a"}, 910: {"a"}, 1019: {"a"}}
    assert list(domains.support_anchors(tracks, damage, "h")) == [900, 1020]
