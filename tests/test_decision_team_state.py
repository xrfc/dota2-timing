"""Option A: allies full state, visible enemies mana only, hidden heroes nothing."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from dota_items.data.decision_team_state import PRODUCER, player_id, team_state
from dota_items.storage import file_hash


def probe_row(tick, pid, hp, mana, cd):
    return {
        "tick": tick,
        "player_id": pid,
        "level": 10,
        "parser_game_time_s": tick / 30,
        "hero": {
            "entity_index": 100 + pid,
            "entity_serial": 1,
            "values": {
                "m_iHealth": hp,
                "m_iMaxHealth": 1000,
                "m_flMana": mana,
                "m_flMaxMana": 500.0,
            },
        },
        "items": [],
        "abilities": [
            {
                "slot": 0,
                "handle": 7,
                "name": "spell",
                "entity": {
                    "entity_index": 9,
                    "entity_serial": 1,
                    "values": {"m_fCooldown": cd, "m_iLevel": 1},
                },
            }
        ],
    }


def fixture():
    capture = {
        "decision_tick": 60,
        "producer": PRODUCER,
        "build": 6965,
        "schema_game_build": 6965,
        "rows": [
            probe_row(30, 0, 800, 200.0, 6.0),
            probe_row(60, 0, 800, 210.0, 5.0),
            probe_row(60, 5, 700, 300.0, 4.0),
            probe_row(60, 6, 600, 100.0, 3.0),
            # A later row must never be read.
            probe_row(90, 0, 1, 499.0, 0.0),
        ],
    }
    positions = [
        {"player_slot": 0, "hero_id": 8, "relation": "ally", "visibility": "visible"},
        {"player_slot": 128, "hero_id": 2, "relation": "enemy", "visibility": "visible"},
        {"player_slot": 129, "hero_id": 3, "relation": "enemy", "visibility": "hidden"},
    ]
    team = [
        {
            "player_slot": 0,
            "hero_id": 8,
            "visibility": "visible",
            "health": {"current": 800, "max": 1000},
        },
        {
            "player_slot": 128,
            "hero_id": 2,
            "visibility": "visible",
            "health": {"current": 700, "max": 1000},
        },
        {"player_slot": 129, "hero_id": 3, "visibility": "hidden", "health": None},
    ]
    return capture, {"tick": 60, "positions": positions}, team


def test_option_a_policy_and_countdown_from_past_only():
    state = team_state(*fixture())
    cards = {c["player_slot"]: c for c in state["cards"]}
    assert set(cards) == {0, 128}
    ally, enemy = cards[0], cards[128]
    assert ally["mana"]["current"] == 210.0
    assert ally["abilities"][0]["cooldown_source_value"] == 5.0
    assert ally["abilities"][0]["past_countdown_consistent"] is True
    assert enemy["mana"]["current"] == 300.0
    assert enemy["abilities"] == enemy["items"] == [] and enemy["tp"] is None
    assert enemy["cooldowns"] == "withheld_enemy_visibility_unverified"
    assert state["training_allowed"] is False


def test_future_rows_do_not_change_output():
    capture, decision, team = fixture()
    before = team_state(capture, decision, team)
    capture["rows"][-1]["hero"]["values"]["m_flMana"] = 0.0
    capture["rows"].append(probe_row(120, 5, 1, 1.0, 0.0))
    assert team_state(capture, decision, team) == before


@pytest.mark.parametrize(
    "change",
    [
        lambda c, d, t: t[1]["health"].update(current=1),
        lambda c, d, t: t[0].update(hero_id=99),
        lambda c, d, t: c.update(producer="other"),
        lambda c, d, t: c.update(build=1),
        lambda c, d, t: c["rows"].append(copy.deepcopy(c["rows"][1])),
        lambda c, d, t: c["rows"][1]["hero"]["values"].update(m_flMana=999.0),
    ],
)
def test_identity_and_source_mismatches_rejected(change):
    parts = fixture()
    change(*parts)
    with pytest.raises(ValueError):
        team_state(*parts)


def test_player_slot_mapping():
    assert [player_id(s) for s in (0, 4, 128, 132)] == [0, 4, 5, 9]
    with pytest.raises(ValueError):
        player_id(5)


def load():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("team", root / "scripts/attach_team_state.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def repo_fixture(tmp_path, target_mana=210.0):
    module = load()
    repo = tmp_path / "repo"
    capture, decision, team = fixture()
    capture["match_id"] = 7
    base = repo / "reports/base"
    card = {
        "case": {"id": "one", "match_id": 7, "tick": 60, "slot": 0},
        "evidence": {"decision_input": decision},
        "enhancement": {
            "comparison_card": {"tick": 60, "team_state": team},
            "live_state_card": {"mana": {"current": target_mana, "max": 500.0}},
        },
    }
    dump(base / "cases.json", {"cards": [card]})
    (base / "one-after.json").write_bytes(b'{"future":1}\n')
    outputs = {p.name: file_hash(p) for p in base.glob("*.json")}
    dump(base / "verification.json", {"source_files": {}, "outputs": outputs})
    match = repo / "reports/probe/7"
    dump(match / "capture.json", capture)
    complete = {"match_id": 7, "training_allowed": False}
    complete["outputs"] = {"capture.json": file_hash(match / "capture.json")}
    dump(match / "complete.json", complete)
    for name in module.IMPLEMENTATION:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("fixture")
    return module, repo, base


def test_new_package_keeps_base_and_binds_probe(tmp_path):
    module, repo, base = repo_fixture(tmp_path)
    before = {p.name: p.read_bytes() for p in base.iterdir()}
    module.attach("reports/new", "reports/base", "reports/probe", repo)
    assert {p.name: p.read_bytes() for p in base.iterdir()} == before
    new = repo / "reports/new"
    assert (new / "one-after.json").read_bytes() == before["one-after.json"]
    package = json.loads((new / "cases.json").read_text())
    state = package["cards"][0]["enhancement"]["team_live_state"]
    assert [c["player_slot"] for c in state["cards"]] == [0, 128]
    verification = json.loads((new / "verification.json").read_text())
    assert all(file_hash(new / n) == h for n, h in verification["outputs"].items())


def test_disagreement_with_repaired_target_mana_rejected(tmp_path):
    module, repo, _ = repo_fixture(tmp_path, target_mana=1.0)
    with pytest.raises(ValueError, match="repaired target"):
        module.attach("reports/new", "reports/base", "reports/probe", repo)
    assert not (repo / "reports/new").exists()


def test_probe_drift_rejected(tmp_path):
    module, repo, _ = repo_fixture(tmp_path)
    (repo / "reports/probe/7/capture.json").write_text("{}")
    with pytest.raises(ValueError, match="drift"):
        module.attach("reports/new", "reports/base", "reports/probe", repo)
