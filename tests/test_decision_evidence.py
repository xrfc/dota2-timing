"""Decision evidence safety: side/tick/identity, missingness and leakage."""

import hashlib
import json
from copy import deepcopy

import pytest

from dota_items.data.decision_evidence import DecisionEvidenceStore, build_evidence, position_status


def fixture():
    row = dict(
        player_slot=0,
        hero_id=8,
        visibility="visible",
        life_state=0,
        current_position={"x": 10, "y": 20},
        last_seen=None,
    )
    enemy = dict(
        player_slot=128,
        hero_id=2,
        visibility="hidden",
        life_state=None,
        current_position=None,
        last_seen={"source_tick": 0, "time": 0, "position": {"x": 2, "y": 3}},
    )
    frame = dict(match_id=1, view="radiant", tick=30, time=1, players=[row, enemy])
    state = dict(
        player_id=0,
        tick=30,
        entity_index=12,
        entity_serial=3,
        life_state=0,
        items={"0": "item_bfury", "6": "item_blink"},
        inventory_empty_handle=999,
        inventory_handles={str(s): s + 1 if s in (0, 6) else 999 for s in range(17)},
        inventory_unknown_slots=[],
        inventory_complete=True,
    )
    raw = dict(
        match_id=1,
        players=[dict(player_id=0, hero_id=8, team=2)],
        coach_state_snapshots=[state],
        hero_visibility_events=[
            dict(player_id=0, tick=0, entity_index=12, entity_serial=3, radiant_state="visible")
        ],
    )
    return frame, raw


def test_inventory_is_not_usability_and_enemies_have_no_state():
    f, r = fixture()
    e = build_evidence(f, r, 0)
    d = e["decision_input"]
    assert not e["training_allowed"]
    assert d["inventory"]["slots"][6]["group"] == "backpack"
    assert d["inventory"]["slots"][6]["usable"] is None
    assert d["inventory"]["slots"][1]["status"] == "empty"
    assert d["enemy_inventory"] is None and d["health_mana"] is None
    assert d["positions"][1]["last_seen"]["age_ticks"] == 30


def test_hidden_and_future_perturbation_does_not_change_input_but_visible_does():
    f, r = fixture()
    before = build_evidence(f, r, 0)["decision_input"]
    r["players"][0]["final_items"] = {"0": "item_rapier"}
    r["coach_state_snapshots"] += [
        dict(r["coach_state_snapshots"][0], tick=60, items={"0": "item_rapier"}),
        dict(player_id=5, tick=30, items={"0": "item_rapier"}),
    ]
    r["combat_log"] = [{"tick": 31, "log_type": "DEATH"}]
    r["hero_visibility_events"].append(
        dict(r["hero_visibility_events"][0], tick=60, radiant_state="hidden")
    )
    assert build_evidence(f, r, 0)["decision_input"] == before
    f["players"][0]["current_position"]["x"] = 11
    assert build_evidence(f, r, 0)["decision_input"] != before


@pytest.mark.parametrize("change", ["future", "duplicate", "serial", "hidden", "life"])
def test_unreliable_state_never_supplies_inventory(change):
    f, r = fixture()
    state = r["coach_state_snapshots"][0]
    if change == "future":
        state["tick"] = 31
    elif change == "duplicate":
        r["coach_state_snapshots"].append(deepcopy(state))
    elif change == "serial":
        state["entity_serial"] = 4
    elif change == "hidden":
        r["hero_visibility_events"][0]["radiant_state"] = "hidden"
    else:
        state["life_state"] = 2
    assert build_evidence(f, r, 0)["decision_input"]["inventory"]["status"] == "unknown"


def test_empty_unresolved_and_conflicting_inventory_distinguished():
    f, r = fixture()
    state = r["coach_state_snapshots"][0]
    state["inventory_handles"]["1"] = None
    state["items"]["2"] = "item_blink"  # Name conflicts with empty handle.
    state["inventory_handles"]["3"] = 123  # Occupied but name unresolved.
    slots = build_evidence(f, r, 0)["decision_input"]["inventory"]["slots"]
    assert [slots[i]["status"] for i in (1, 2, 3, 4)] == ["unknown"] * 3 + ["empty"]


@pytest.mark.parametrize("change", ["omni", "enemy", "match", "hero", "future_last", "leak"])
def test_invalid_identity_and_hidden_fields_fail_closed(change):
    f, r = fixture()
    slot = 0
    if change == "omni":
        f["view"] = "omniscient"
    elif change == "enemy":
        slot = 128
    elif change == "match":
        r["match_id"] = 2
    elif change == "hero":
        r["players"][0]["hero_id"] = 2
    elif change == "future_last":
        f["players"][1]["last_seen"]["source_tick"] = 31
    else:
        f["players"][1]["current_position"] = {"x": 100, "y": 200}
    with pytest.raises(ValueError):
        build_evidence(f, r, slot)


@pytest.mark.parametrize("state,expected", [(1, "dying"), (2, "dead"), (None, "state_missing")])
def test_death_is_not_missing_observation(state, expected):
    f, _ = fixture()
    row = f["players"][0] | dict(life_state=state, current_position=None)
    assert position_status(row) == expected


def test_store_pins_raw_bytes_to_manifest_and_rejects_wrong_capture(tmp_path):
    f, raw = fixture()
    raw["coach_capture_version"] = "gem-state-capture/2"
    path = tmp_path / "raw.json"
    content = json.dumps(raw).encode()
    path.write_bytes(content)
    manifest = {
        "inputs_and_code": {str(path): hashlib.sha256(content).hexdigest()},
        "files": {"radiant.jsonl": "view-pinned"},
    }

    class Replay:
        entries = {1: {"manifest_sha256": "manifest-pinned"}}

        def frame(self, *args, **kwargs):
            return f

        def load(self, *args):
            return {"manifest": manifest}

    store = DecisionEvidenceStore(Replay(), tmp_path)
    assert (
        store.build(1, "radiant", 30, 0)["provenance"]["raw_sha256"]
        == hashlib.sha256(content).hexdigest()
    )
    path.write_bytes(content + b" ")
    with pytest.raises(ValueError, match="Raw hash mismatch"):
        store.build(1, "radiant", 30, 0)
    raw["coach_capture_version"] = "unknown"
    content = json.dumps(raw).encode()
    path.write_bytes(content)
    manifest["inputs_and_code"][str(path)] = hashlib.sha256(content).hexdigest()
    with pytest.raises(ValueError, match="Unsupported state capture"):
        store.build(1, "radiant", 30, 0)
