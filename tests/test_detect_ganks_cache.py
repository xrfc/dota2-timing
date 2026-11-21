"""The per-match input cache of scripts/detect_ganks.py."""

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "detect_ganks.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("detect_ganks_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(kind, source=None, target=None, name=None):
    payload = {"log_type": kind, "attacker_name": source, "target_name": target}
    return {"time": 10, "payload": {**payload, "inflictor_name": name}}


def test_slim_combat_drops_fields_the_rules_never_read(script):
    full = entry("DAMAGE", "hero_a", "hero_b")
    full["payload"].update(value=40, tick=9, stun_duration=0.0, target_source_name="hero_b")
    (kept,) = script.slim_combat([full], {"hero_a": {}, "hero_b": {}})
    assert kept["time"] == 10 and set(kept["payload"]) == set(script.COMBAT_FIELDS) - {
        "attacker_is_hero",
        "attacker_is_illusion",
        "target_is_illusion",
    }


def test_slim_combat_keeps_what_the_rules_read(script):
    heroes = {"hero_a": {}, "hero_b": {}}
    keep = [
        entry("DAMAGE", "hero_a", "creep"),
        entry("DAMAGE", "creep", "hero_b"),
        entry("DEATH", "creep", "npc_dota_goodguys_tower1_mid"),
        entry("ABILITY", "hero_a", None, "some_ability"),
        entry("ITEM", "hero_a", None, "item_blink"),
        entry("MODIFIER_ADD", "hero_a", "hero_a", script.SMOKE_MODIFIER),
    ]
    drop = [
        entry("DAMAGE", "creep", "creep"),
        entry("MODIFIER_ADD", "hero_a", "hero_b", "modifier_stunned"),
        entry("GOLD", None, "hero_a"),
    ]
    assert script.slim_combat([*keep, *drop], heroes) == keep


def write_match(root, mid, x):
    (root / "state-v3").mkdir(parents=True, exist_ok=True)
    (root / "parsed").mkdir(parents=True, exist_ok=True)
    hero = {"hero": "hero_a", "team": 2, "player_id": 0, "life_state": 0, "pos": [x, 100]}
    with gzip.open(root / "state-v3" / f"{mid}.jsonl.gz", "wt", encoding="utf-8") as stream:
        stream.write("{}\n" + json.dumps({"t": 0, "heroes": [hero], "world": {}}) + "\n")
    parsed = {
        "players": [],
        "context": {"channels": {"hero_visibility_events": [], "combat_log": []}},
    }
    path = root / "parsed" / f"{mid}.normalized.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(parsed, stream)


def test_cache_is_reused_until_a_source_file_changes(script, tmp_path, monkeypatch):
    write_match(tmp_path, 7, 100)
    cache = tmp_path / "gank-inputs-v2"
    first = script.match_inputs(tmp_path, 7, cache)
    assert (cache / "7.pkl").exists() and first == script.read_match(tmp_path, 7)

    calls = []
    real = script.read_match
    monkeypatch.setattr(script, "read_match", lambda *a: calls.append(a) or real(*a))
    assert script.match_inputs(tmp_path, 7, cache) == first and not calls

    write_match(tmp_path, 7, 12345)  # the source changed: size differs, so the key differs
    again = script.match_inputs(tmp_path, 7, cache)
    assert calls and again["tracks"] != first["tracks"]
    assert script.match_inputs(tmp_path, 7, None) == again and len(calls) == 2  # no cache
